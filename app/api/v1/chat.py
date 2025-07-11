import base64, os, json, logging, asyncio
from openai import AsyncClient
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status, Form
from app.api.dependency import (
    get_current_user,
    get_openai_client,
    check_subscription_active,
)
from app.models.user import User
from app.models.chat import ChatSession, ChatMessage, ChatImage, GeneratedReport
from app.models.payment import Plan
from app.schemas.chat import (
    ChatSessionOut,
    MessageOut,
    RenameSession,
    ChatInput,
    ImageOut,
    GeneratedReportOut,
)
from app.utils.helpers import build_spine_diagnosis_prompt, build_post_diagnosis_prompt
from tortoise_vector.expression import CosineSimilarity
from tortoise.transactions import atomic
from app.core.config import settings
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024
AVERAGE_PAGES_PER_HOUR = 30
BATCH_TOKEN_LIMIT = 8000
CHUNK_BATCH_SIZE = 32

router = APIRouter(prefix="/v1/chat", tags=["Chat Endpoints"])


@router.get("/dashboard", response_model=dict)
async def user_dashboard(user: User = Depends(get_current_user)):
    return {
        "total_sessions": await user.chat_sessions.all().count(),
        "total_images": await ChatImage.filter(message__session__user=user).count(),
    }


# def count_tokens(text: str, model: str = "text-embedding-3-large") -> int:
#     encoding = get_encoding("cl100k_base")
#     return len(encoding.encode(text))


# async def process_batch(batch: List[str], openai_client, document):
#     resp = await openai_client.embeddings.create(
#         model="text-embedding-3-large",
#         input=batch,
#         dimensions=settings.OPENAI_VECTOR_SIZE,
#     )
#     for chunk_text, item in zip(batch, resp.data):
#         ...


# async def batch_embed_chunks(chunks: List[str], openai_client, document):
#     batch = []
#     current_tokens = 0
#     for chunk in chunks:
#         token_count = count_tokens(chunk)
#         if (
#             current_tokens + token_count > BATCH_TOKEN_LIMIT
#             or len(batch) >= CHUNK_BATCH_SIZE
#         ):
#             await process_batch(batch, openai_client, document)
#             batch = []
#             current_tokens = 0
#         batch.append(chunk)
#         current_tokens += token_count
#     if batch:
#         await process_batch(batch, openai_client, document)


# @router.post("/create", response_model=ChatSessionOut)
# async def create_chat(
#     files: List[UploadFile] = File(...),
#     user: User = Depends(check_subscription_active),
#     client=Depends(get_httpx_client),
#     openai_client=Depends(get_openai_client),
# ):
#     if not files:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="At least one file must be uploaded.",
#         )

#     # Validate total file size and check for emptiness
#     total_size = 0
#     for file in files:
#         first_chunk = await file.read(1024)
#         if not first_chunk:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail=f"File '{file.filename}' is empty.",
#             )
#         await file.seek(0)
#         total_size += file.size or len(await file.read())
#         await file.seek(0)

#     if total_size > MAX_FILE_SIZE_BYTES:
#         raise HTTPException(
#             status_code=status.HTTP_413_PAYLOAD_TOO_LARGE,
#             detail=f"Total size of uploaded files ({total_size / (1024 * 1024):.2f} MB) exceeds the limit of {MAX_FILE_SIZE_BYTES / (1024 * 1024):.0f} MB.",
#         )

#     # Check subscription limits
#     exceeded, plan_limit, plan_name = await user.monthly_page_limit_exceeded()
#     if exceeded:
#         raise HTTPException(
#             status_code=400,
#             detail=f"You have exceeded your monthly page limit of {plan_limit} pages for the '{plan_name}' plan. Please upgrade your plan or wait until next month to continue.",
#         )

#     # Read all files and extract text concurrently
#     azur_ocr = AzureOCRService(client=client)
#     file_data = []
#     total_page_count = 0

#     async def process_file(file: UploadFile):
#         file_bytes = await file.read()
#         lines, page_count = await azur_ocr.extract_text(file_bytes)
#         if not lines:
#             raise HTTPException(
#                 400, f"Unable to extract text from file '{file.filename}'"
#             )
#         return {
#             "filename": file.filename,
#             "size": file.size or len(file_bytes),
#             "lines": lines,
#             "page_count": page_count,
#             "full_text": "\n".join(lines),
#         }

#     tasks = [process_file(file) for file in files]
#     results = await asyncio.gather(*tasks, return_exceptions=True)
#     for result in results:
#         if isinstance(result, Exception):
#             raise HTTPException(400, f"Error processing file: {str(result)}")
#         file_data.append(result)
#         total_page_count += result["page_count"]

#     # Combine all extracted text into one
#     full_text = "\n".join(data["full_text"] for data in file_data)
#     if not full_text.strip():
#         raise HTTPException(400, "No text extracted from any file")

#     # Prepare metadata for combined document
#     session_title = (
#         file_data[0]["filename"] if len(file_data) == 1 else "Multiple Documents"
#     )

#     combined_size = sum(d["size"] for d in file_data)

#     # Create ChatSession, Usage, and single ChatDocument
#     async with in_transaction():
#         session = await ChatSession.create(user=user, title=session_title)
#         await Usage.create(
#             user=user, usage_count=total_page_count, source=session_title
#         )
#         document = await ChatMessage.create(
#             chat=session,
#             full_text=full_text,
#             document_url="not_applicable_or_set_later",
#             name=session_title,
#             size=combined_size,
#             extracted_page_count=total_page_count,
#         )

#     # Split text and embed chunks
#     splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)
#     chunks = splitter.split_text(full_text)
#     await batch_embed_chunks(chunks, openai_client, document)

#     return session


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


@atomic
@router.post(
    "/session/{session_id}/send", dependencies=[Depends(check_subscription_active)]
)
async def send_session(
    session_id: str,
    message: str = Form(None),
    files: list[UploadFile] = None,
    s3_urls: list[str] = None,
    user: User = Depends(get_current_user),
    openai_client: AsyncClient = Depends(get_openai_client),
):
    if not message and not files:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No message or files provided")
    session = await ChatSession.get_or_none(id=session_id, user=user)
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unauthorized Access")

    # Save user message and embed
    embedded_message = (
        await embed_text(message, openai_client=openai_client) if message else None
    )
    chat_message = await ChatMessage.create(
        content=message,
        session_id=session_id,
        sender="user",
        embedding=embedded_message,
    )
    if session.is_diagnosed:
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
        messages = build_post_diagnosis_prompt(
            user={"name": user.full_name},
            session_id=session_id,
            findings=session.findings or {},
            recommendations=session.recommendations or {},
            current_message=message,
            previous_messages=context_messages,
        )
        response = await openai_client.chat.completions.create(
            model="gpt-4.1-2025-04-14",
            messages=messages,
            temperature=0.2,
            response_format={"type": "json_object"},
        )

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
    if files:
        if len(files) != len(s3_urls):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Number of files and S3 URLs must match",
            )
        tasks = [convert_image_to_base64(item) for item in files]
        base64_images = await asyncio.gather(*tasks)
        image_data = [
            ChatImage(
                message_id=chat_message.id,
                img_base64=base64_image[0],
                filename=base64_image[1],
                s3_url=s3_url,
            )
            for base64_image, s3_url in zip(base64_images, s3_urls)
        ]
        await ChatImage.bulk_create(image_data)

    prev_messages = await ChatMessage.filter(
        session_id=session_id, is_relevant=True
    ).order_by("id")
    prev_images = await ChatImage.filter(
        message__session_id=session_id, is_relevant=True
    ).order_by("id")

    prev_message_data = [
        {"id": msg.id, "sender": msg.sender, "text": msg.content}
        for msg in prev_messages
    ]
    prev_image_data = [
        {"image_id": img.id, "url": img.img_base64} for img in prev_images
    ]

    messages = build_spine_diagnosis_prompt(
        session_id=session_id,
        previous_messages=prev_message_data,
        previous_images=prev_image_data,
        current_message=prev_message_data.pop(),
    )
    response = await openai_client.chat.completions.create(
        model="gpt-4.1-2025-04-14",
        messages=messages,
        temperature=0.2,
        response_format={"type": "json_object"},
    )

    try:
        result = response.choices[0].message.content
        ai_response = json.loads(result)
    except Exception as e:
        raise HTTPException(500, f"AI response error: {e}")

    backend = ai_response.get("backend", {})
    user_markdown = ai_response.get("user", "")
    if backend.get("is_diagnosed"):
        await ChatSession.filter(id=session_id).update(
            findings=backend.get("findings"),
            recommendations=backend.get("recommendations"),
            is_diagnosed=True,
            recommendations_notified_at=datetime.now(timezone.utc),
            title=backend.get("session_title"),
        )
        await session.refresh_from_db()

    msg_ids = backend.get("irrelevant_message_ids", [])
    img_ids = backend.get("irrelevant_image_ids", [])

    if msg_ids:
        await ChatMessage.filter(id__in=msg_ids).update(is_relevant=False)
    if img_ids:
        await ChatImage.filter(id__in=img_ids).update(is_relevant=False)

    ai_chat = await ChatMessage.create(
        session_id=session_id,
        sender="system",
        content=user_markdown,
        embedding=await embed_text(user_markdown, openai_client=openai_client),
    )
    data_response = {
        "message": user_markdown,
        "message_id": ai_chat.id,
        "is_diagnosed": backend.get("is_diagnosed", False),
    }
    if session.title:
        data_response["session_title"] = session.title

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
