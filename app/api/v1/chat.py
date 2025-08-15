import base64, os, json, logging, asyncio
from openai import AsyncClient
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status, Form
from app.api.dependency import (
    get_current_user,
    get_openai_client,
    check_subscription_active,
)
from app.utils.helpers import get_month_range
from app.tasks.chat import create_treatment_per_session
from app.models.user import User
from app.models.payment import Plan
from app.models.chat import (
    ChatSession,
    ChatMessage,
    ChatImage,
    GeneratedReport,
    UserUploadedFile,
    Usage,
)
from app.schemas.chat import (
    ChatSessionOut,
    MessageOut,
    RenameSession,
    ImageOut,
    GeneratedReportOut,
    UserUploadedFileOut,
)
from app.services.file_processing_sernice import FileProcessingService
from tortoise_vector.expression import CosineSimilarity
from tortoise.transactions import atomic
from app.core.config import settings
from datetime import datetime, timezone

# Import the helper files
from app.utils import helpers as premium_helpers
from app.utils import free_helpers

from app.tasks.product import async_db_get_ai_recommendation
from app.models.product import Product

logger = logging.getLogger(__name__)


MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024
AVERAGE_PAGES_PER_HOUR = 30
BATCH_TOKEN_LIMIT = 8000
CHUNK_BATCH_SIZE = 32

router = APIRouter(prefix="/v1/chat", tags=["Chat Endpoints"])


@router.get("/dashboard", response_model=dict)
async def user_dashboard(user: User = Depends(get_current_user)):
    plan = None
    if user.current_plan not in (None, ""):
        plan = await Plan.get_or_none(stripe_price_id=user.current_plan)
    else:
        plan = await Plan.get_or_none(name="0.00")
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )
    start_current_month, start_next_month = get_month_range()
    total_message, total_images, total_files = await asyncio.gather(
        Usage.filter(
            created_at__gte=start_current_month,
            created_at__lt=start_next_month,
            user=user,
            usage_type="message",
        ).count(),
        Usage.filter(
            created_at__gte=start_current_month,
            created_at__lt=start_next_month,
            user=user,
            usage_type__in=["jpg", "jpeg", "png"],
        ).count(),
        Usage.filter(
            created_at__gte=start_current_month,
            created_at__lt=start_next_month,
            user=user,
        )
        .exclude(usage_type__in=["jpg", "jpeg", "png"])
        .count(),
    )
    message_left = plan.message_limit - total_message
    if message_left < 0:
        message_left = 0
    image_left = plan.image_limit - total_images
    if image_left < 0:
        image_left = 0
    file_left = plan.file_limit - total_files
    if file_left < 0:
        file_left = 0
       
    return {
        "total_sessions": await user.chat_sessions.all().count(),
        "total_files": await UserUploadedFile.filter(user=user).count(),
        "total_reports": await GeneratedReport.filter(user=user).count(),
        "current_plan_message_limit": plan.message_limit,
        "current_plan_image_limit": plan.image_limit,
        "current_plan_file_limit": plan.file_limit,
        "message_left": message_left,
        "image_left": image_left,
        "file_left": file_left,
        "image_credit": user.image_credit,
    }


@router.get("/session/{session_id}/all", response_model=list[MessageOut])
async def chat_message(
    session_id: str,
    offset: int = 0,
    limit: int = 200,
    user: User = Depends(get_current_user),
):

    messages = (
        ChatMessage.filter(session_id=session_id, session__user=user)
        .prefetch_related("chat_images")
        .offset(offset)
        .limit(limit)
        .order_by("created_at")
    )
    return await MessageOut.from_queryset(messages)


@router.delete("/session/{session_id}/delete")
async def session_delete(session_id: str, user: User = Depends(get_current_user)):
    await user.chat_sessions.filter(id=session_id).delete()
    return {"message": "Deleted Successfully"}


@router.put("/session/{session_id}/update")
async def session_update(
    session_id: str, form: RenameSession, user: User = Depends(get_current_user)
):
    session = await user.chat_sessions.filter(id=session_id).first()
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sesson Not Found")
    session.title = form.title
    await session.save()
    return {"message": "Updated Successfully"}


@router.post("/session/create", dependencies=[Depends(check_subscription_active)])
async def session_create(user: User = Depends(get_current_user)):
    await user.check_plan_limit()
    return await ChatSession.create(user=user)


async def embed_text(text: str, openai_client: AsyncClient):
    if text is None or text == "":
        return None
    res = await openai_client.embeddings.create(
        model="text-embedding-3-large",
        input=text,
        dimensions=settings.EMBEDDING_DIMENSIONS,
    )
    return res.data[0].embedding


async def convert_image_to_base64(file: UploadFile) -> str:
    """Convert uploaded image to base64 string with data URI prefix."""
    content = await file.read()
    base64_encoded_image = base64.b64encode(content).decode("utf-8")
    mime_type = file.content_type
    if not mime_type:
        file_extension = os.path.splitext(file.filename)[1].lower()
        if file_extension == ".jpg" or file_extension == ".jpeg":
            mime_type = "image/jpeg"
        elif file_extension == ".png":
            mime_type = "image/png"
        elif file_extension == ".gif":
            mime_type = "image/gif"

    if not mime_type:
        mime_type = "application/octet-stream"
    return f"data:{mime_type};base64,{base64_encoded_image}", file.filename


async def makeProductRecommendationText(session):
    print(session, "printing session")
    products = (
        await Product.filter(tags__name__in=session.suggested_product_tags)
        .order_by("name")
        .distinct()
        .offset(0)
        .limit(3)
        .values_list("name", "shopify_url")
    )
    print(products, "printing products")
    if not products:
        return ""
    product_str_list = [f"* [{name}]({url})" for name, url in products]
    productMessage = f"""#### Products Recommendations based on your condition:\n{'\n'.join(product_str_list)}"""
    return productMessage


import time


@atomic
@router.post(
    "/session/{session_id}/send", dependencies=[Depends(check_subscription_active)]
)
async def send_session_v2(
    session_id: str,
    message: str = Form(None),
    files: list[UploadFile] = None,
    s3_urls: list[str] = None,
    user: User = Depends(get_current_user),
    openai_client: AsyncClient = Depends(get_openai_client),
):
    # Determine which helpers module to use based on the user's plan
    if user.current_plan is None:
        helpers = free_helpers
    else:
        helpers = premium_helpers

    total_usage = []
    if not message and not files:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No message or files provided")
    await user.check_plan_limit(files)

    session = await ChatSession.get_or_none(id=session_id, user=user)
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unauthorized Access")

    umsg_st = time.time()
    # Save user message and embed
    embedded_message = (
        await embed_text(message, openai_client=openai_client) if message else None
    )
    chat_message = await ChatMessage.create(
        content=message,
        session_id=session_id,
        sender="user",
        embedding=embedded_message,
        is_relevant=False if session.is_diagnosed and files is None else True,
    )
    if message:
        total_usage.append(
            Usage(user=user, usage_count=1, source=session.id, usage_type="message")
        )
    if session.is_diagnosed and files is None:
        print("Entered Is diagnosed")
        print(await makeProductRecommendationText(session))
        similar_messages = (
            await ChatMessage.filter(session_id=session_id)
            .exclude(id=chat_message.id)
            .annotate(
                distance=CosineSimilarity(
                    "embedding", embedded_message, settings.OPENAI_VECTOR_SIZE
                )
            )
            .order_by("distance")
            .limit(10)
        )
        similar_messages_ids = [msg.id for msg in similar_messages]
        last_few_messages = (
            await ChatMessage.filter(session_id=session_id)
            .exclude(id__in=similar_messages_ids)
            .order_by("-created_at")
            .limit(5)
        )
        context_messages = [
            {"sender": msg.sender, "text": msg.content} for msg in last_few_messages
        ]
        context_messages = context_messages + [
            {"sender": msg.sender, "text": msg.content} for msg in similar_messages
        ]
        messages = helpers.build_post_diagnosis_prompt(
            user={"name": user.full_name},
            session_id=session_id,
            findings=session.findings or {},
            recommendations=session.recommendations or {},
            current_message=message,
            previous_messages=context_messages,
        )
        response = await openai_client.chat.completions.create(
            model="gpt-4.1",
            messages=messages,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        await Usage.bulk_create(total_usage)

        try:
            result = response.choices[0].message.content
            ai_response = json.loads(result)
        except Exception as e:
            raise HTTPException(500, f"AI response error: {e}")

        user_markdown = ai_response.get("user", "")
        updated_recs = ai_response.get("updated_recommendations", {})
        report = ai_response.get("report", {})
        report_title = ai_response.get("report_title", {})
        if updated_recs:
            await ChatSession.filter(id=session_id).update(recommendations=updated_recs)

        ai_message = await ChatMessage.create(
            session_id=session_id,
            sender="system",
            content=user_markdown,
            embedding=await embed_text(user_markdown, openai_client=openai_client),
            is_relevant=False,
        )
        data_response = {"message": user_markdown, "message_id": ai_message.id}
        if report:
            generated_report = await GeneratedReport.create(
                session=session,
                user=user,
                content=report,
                message_id=ai_message.id,
                title=report_title,
            )
            data_response["report_id"] = generated_report.id
        return data_response
    if session.is_diagnosed and files is not None:
        session.is_diagnosed = False
        await session.save()
    print("Entered Is not diagnosed")
    print("Message Embeddin Time", time.time() - umsg_st)
    file_st = time.time()
    processed_files = []
    if files:
        if len(files) != len(s3_urls):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Number of files and S3 URLs must match",
            )
        user_uploaded_files = [
            UserUploadedFile(
                user=user,
                file_name=file.filename,
                file_type=file.filename.split(".")[-1].lower(),
                file_size=file.size,
                file_url=s3_url,
                message=chat_message,
            )
            for file, s3_url in zip(files, s3_urls)
        ]
        for file in files:
            print("Processing file:", file.filename)
            print("Usage Type:", file.filename.split(".")[-1].lower())
        total_usage += [
            Usage(
                user=user,
                usage_count=1,
                source=session.id,
                usage_type=file.filename.split(".")[-1].lower(),
            )
            for file in files
        ]
        await UserUploadedFile.bulk_create(user_uploaded_files)
        await Usage.bulk_create(total_usage)

        processed_files = await FileProcessingService.process_files(
            files=files, s3_urls=s3_urls
        )
        file_data = [
            ChatImage(
                message_id=chat_message.id,
                img_base64=file["base64_data"],
                filename=file["filename"],
                file_type=file["file_type"],
                s3_url=file["s3_url"],
                meta_data=file["metadata"],
            )
            for file in processed_files
        ]
        await ChatImage.bulk_create(file_data)
    print("Image Proccessing Time", time.time() - file_st)

    build_pmt_st = time.time()

    prev_messages = (
        await ChatMessage.filter(session_id=session_id, is_relevant=True)
        .exclude(id=chat_message.id)
        .order_by("id")
    )

    prev_message_data = [
        {"id": msg.id, "sender": msg.sender, "text": msg.content}
        for msg in prev_messages
    ]
    current_message_data = (
        {
            "id": chat_message.id,
            "sender": chat_message.sender,
            "text": chat_message.content,
        }
        if chat_message.content
        else None
    )
    current_image_data = [{"url": file["base64_data"]} for file in processed_files]

    print("Image Summary", session.image_summary)
    messages = helpers.build_spine_diagnosis_prompt(
        previous_messages=prev_message_data,
        new_images=current_image_data,
        current_message=current_message_data,
        images_summary=session.image_summary or {},
    )

    print("Build Prompt Time", time.time() - build_pmt_st)
    openai_st = time.time()
    response = await openai_client.chat.completions.create(
        model="gpt-4.1",
        messages=messages,
        temperature=0.2,
        response_format={"type": "json_object"},
    )

    try:
        result = response.choices[0].message.content
        ai_response = json.loads(result)
    except Exception as e:
        raise HTTPException(500, f"AI response error: {e}")
    print("AI Response", ai_response)
    print("OpenAI Time", time.time() - openai_st)
    final_response_st = time.time()
    backend = ai_response.get("backend", {})
    user_markdown = ai_response.get("user", "")
    if backend.get("is_diagnosed"):
        print("Entered Diagnosed")
        await ChatMessage.filter(session_id=session_id).update(is_relevant=False)
        await ChatSession.filter(id=session_id).update(
            findings=backend.get("findings"),
            recommendations=backend.get("recommendations"),
            is_diagnosed=True,
            recommendations_notified_at=datetime.now(timezone.utc),
            title=backend.get("session_title"),
        )
        await session.treatment_plans.all().delete()
        create_treatment_per_session.delay(session_id)
        # get_ai_tags_per_session.delay(session_id)
        await async_db_get_ai_recommendation(session_id)
        await session.refresh_from_db()
    else:
        await ChatSession.filter(id=session_id).update(is_diagnosed=False)
    if backend.get("images_summary") and not backend.get("multiple_region_detected"):
        await ChatSession.filter(id=session_id).update(
            image_summary=backend.get("images_summary")
        )
    msg_ids = backend.get("irrelevant_message_ids", [])

    if msg_ids:
        await ChatMessage.filter(id__in=msg_ids).update(is_relevant=False)

    ai_chat = await ChatMessage.create(
        session_id=session_id,
        sender="system",
        content=user_markdown,
        embedding=await embed_text(user_markdown, openai_client=openai_client),
        is_relevant=False if session.is_diagnosed else True,
    )
    data_response = {
        "message": user_markdown,
        "message_id": ai_chat.id,
        "is_diagnosed": backend.get("is_diagnosed", False),
    }
    if backend.get("is_diagnosed"):
        ProductRecommendationMessage = await makeProductRecommendationText(session)
        ai_chat.content = ai_chat.content + "\n" + ProductRecommendationMessage
        await ai_chat.save()
        data_response["message"] = (
            data_response["message"] + "\n" + ProductRecommendationMessage
        )
    if session.title:
        data_response["session_title"] = session.title
    if backend.get("prompt_new_session"):
        data_response["new_session_prompt"] = backend.get("prompt_new_session")
    print("Final Response Time", time.time() - final_response_st)
    return data_response


@router.get("/session/all", response_model=list[ChatSessionOut])
async def get_all_session(
    offset: int = 0, limit: int = 500, user: User = Depends(get_current_user)
):

    return (
        await user.chat_sessions.all()
        .order_by("-created_at")
        .offset(offset)
        .limit(limit)
    )


@router.get("/images/all", response_model=list[ImageOut])
async def get_all_images(
    offset: int = 0, limit: int = 500, user: User = Depends(get_current_user)
):
    return (
        await ChatImage.filter(message__session__user=user)
        .limit(limit)
        .offset(offset)
        .order_by("-created_at")
    )


@router.get("/report/all", response_model=list[GeneratedReportOut])
async def get_all_reports(
    offset: int = 0, limit: int = 500, user: User = Depends(get_current_user)
):
    return (
        await GeneratedReport.filter(user=user)
        .limit(limit)
        .offset(offset)
        .order_by("-created_at")
    )


@router.get("/report/{report_id}")
async def get_report(report_id: str, user: User = Depends(get_current_user)):
    report = await GeneratedReport.get_or_none(id=report_id, user=user)
    if not report:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report Not Found")
    return report


@router.get("/upload/all", response_model=list[UserUploadedFileOut])
async def get_all_uploaded_files(
    offset: int = 0,
    limit: int = 500,
    file_type: str = None,
    user: User = Depends(get_current_user),
):
    uploaded_files = UserUploadedFile.filter(user=user)
    if file_type:
        if file_type == "image":
            uploaded_files = UserUploadedFile.filter(
                user=user, file_type__in=["jpg", "jpeg", "png"]
            )
        elif file_type == "pdf":
            uploaded_files = UserUploadedFile.filter(user=user, file_type__in=["pdf"])
        elif file_type == "dcm":
            uploaded_files = UserUploadedFile.filter(
                user=user, file_type__in=["dcm", "dicom"]
            )
    return await uploaded_files.limit(limit).offset(offset).order_by("-created_at")
