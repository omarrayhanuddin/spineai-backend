import asyncio
from typing import AsyncGenerator, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import StreamingResponse
from app.api.dependency import (
    get_current_user,
    get_mistral_client,
    get_httpx_client,
    get_openai_client,
    check_subscription_active,
)
from app.services.ocr_service import AzureOCRService
from app.utils.helpers import get_messages_for_llm
from app.models.user import User
from app.models.chat import ChatSession, Message, ChatDocument, DocumentChunk, Usage
from app.models.payment import Plan
from app.schemas.chat import (
    ChatSessionOut,
    MessageOut,
    ChatMessageIn,
    ChatDocumentOut,
    RenameSession,
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from tortoise_vector.expression import CosineSimilarity
from tortoise import Tortoise
from tortoise.transactions import in_transaction
from tiktoken import get_encoding
from app.core.config import settings
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024
AVERAGE_PAGES_PER_HOUR = 30
BATCH_TOKEN_LIMIT = 8000
CHUNK_BATCH_SIZE = 32

router = APIRouter(prefix="/v1/chat", tags=["Chat Endpoints"])


@router.get("/dashboard", response_model=dict)
async def chat_dashboard(user: User = Depends(get_current_user)):
    try:
        conn = Tortoise.get_connection("default")
        plan = await Plan.get_or_none(stripe_price_id=user.current_plan)
        # Lifetime total
        total_sql = """
            SELECT SUM(usage_count) AS total
            FROM usages
            WHERE user_id = $1
            AND is_message = FALSE;
        """
        total_result = await conn.execute_query_dict(total_sql, [user.id])
        total_pages = (
            total_result[0]["total"]
            if total_result and total_result[0]["total"] is not None
            else 0
        )

        # Current month
        now_utc = datetime.now(timezone.utc)
        start_of_month = now_utc.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        monthly_sql = """
            SELECT SUM(usage_count) AS total
            FROM usages
            WHERE user_id = $1
            AND is_message = FALSE
            AND created_at >= $2;
        """
        monthly_result = await conn.execute_query_dict(
            monthly_sql, [user.id, start_of_month]
        )
        monthly_pages = (
            monthly_result[0]["total"]
            if monthly_result and monthly_result[0]["total"] is not None
            else 0
        )

        # Hour saved calculations
        total_hours = (
            round(total_pages / AVERAGE_PAGES_PER_HOUR, 2) if total_pages > 0 else 0
        )
        monthly_hours = (
            round(monthly_pages / AVERAGE_PAGES_PER_HOUR, 2) if monthly_pages > 0 else 0
        )
        monthly_plan_usage_left = plan.page_limit - monthly_pages

        return {
            "total_document_page_analyzed": total_pages,
            "total_hour_saved": total_hours,
            "monthly_document_page_analyzed": monthly_pages,
            "monthly_hour_saved": monthly_hours,
            "monthly_plan_usage_left": (
                monthly_plan_usage_left if monthly_plan_usage_left >= 0 else 0
            ),
        }

    except Exception as e:
        logger.error(f"Error fetching user analysis summary: {e}")
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve user analysis summary due to an internal error.",
        )


def count_tokens(text: str, model: str = "text-embedding-3-large") -> int:
    encoding = get_encoding("cl100k_base")
    return len(encoding.encode(text))


async def process_batch(batch: List[str], openai_client, document):
    resp = await openai_client.embeddings.create(
        model="text-embedding-3-large",
        input=batch,
        dimensions=settings.OPENAI_VECTOR_SIZE,
    )
    for chunk_text, item in zip(batch, resp.data):
        await DocumentChunk.create(
            document=document, content=chunk_text, embedding=item.embedding
        )


async def batch_embed_chunks(chunks: List[str], openai_client, document):
    batch = []
    current_tokens = 0
    for chunk in chunks:
        token_count = count_tokens(chunk)
        if (
            current_tokens + token_count > BATCH_TOKEN_LIMIT
            or len(batch) >= CHUNK_BATCH_SIZE
        ):
            await process_batch(batch, openai_client, document)
            batch = []
            current_tokens = 0
        batch.append(chunk)
        current_tokens += token_count
    if batch:
        await process_batch(batch, openai_client, document)


@router.post("/create", response_model=ChatSessionOut)
async def create_chat(
    files: List[UploadFile] = File(...),
    user: User = Depends(check_subscription_active),
    client=Depends(get_httpx_client),
    openai_client=Depends(get_openai_client),
):
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one file must be uploaded.",
        )

    # Validate total file size and check for emptiness
    total_size = 0
    for file in files:
        first_chunk = await file.read(1024)
        if not first_chunk:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{file.filename}' is empty.",
            )
        await file.seek(0)
        total_size += file.size or len(await file.read())
        await file.seek(0)

    if total_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_PAYLOAD_TOO_LARGE,
            detail=f"Total size of uploaded files ({total_size / (1024 * 1024):.2f} MB) exceeds the limit of {MAX_FILE_SIZE_BYTES / (1024 * 1024):.0f} MB.",
        )

    # Check subscription limits
    exceeded, plan_limit, plan_name = await user.monthly_page_limit_exceeded()
    if exceeded:
        raise HTTPException(
            status_code=400,
            detail=f"You have exceeded your monthly page limit of {plan_limit} pages for the '{plan_name}' plan. Please upgrade your plan or wait until next month to continue.",
        )

    # Read all files and extract text concurrently
    azur_ocr = AzureOCRService(client=client)
    file_data = []
    total_page_count = 0

    async def process_file(file: UploadFile):
        file_bytes = await file.read()
        lines, page_count = await azur_ocr.extract_text(file_bytes)
        if not lines:
            raise HTTPException(
                400, f"Unable to extract text from file '{file.filename}'"
            )
        return {
            "filename": file.filename,
            "size": file.size or len(file_bytes),
            "lines": lines,
            "page_count": page_count,
            "full_text": "\n".join(lines),
        }

    tasks = [process_file(file) for file in files]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            raise HTTPException(400, f"Error processing file: {str(result)}")
        file_data.append(result)
        total_page_count += result["page_count"]

    # Combine all extracted text into one
    full_text = "\n".join(data["full_text"] for data in file_data)
    if not full_text.strip():
        raise HTTPException(400, "No text extracted from any file")

    # Prepare metadata for combined document
    session_title = (
        file_data[0]["filename"] if len(file_data) == 1 else "Multiple Documents"
    )

    combined_size = sum(d["size"] for d in file_data)

    # Create ChatSession, Usage, and single ChatDocument
    async with in_transaction():
        session = await ChatSession.create(user=user, title=session_title)
        await Usage.create(
            user=user, usage_count=total_page_count, source=session_title
        )
        document = await ChatDocument.create(
            chat=session,
            full_text=full_text,
            document_url="not_applicable_or_set_later",
            name=session_title,
            size=combined_size,
            extracted_page_count=total_page_count,
        )

    # Split text and embed chunks
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)
    chunks = splitter.split_text(full_text)
    await batch_embed_chunks(chunks, openai_client, document)

    return session


@router.get("/all-documents", response_model=list[ChatDocumentOut])
async def all_document(
    offset: int = 0, limit: int = 10, user: User = Depends(get_current_user)
):
    return (
        await ChatDocument.filter(chat__user__id=user.id)
        .select_related("chat")
        .distinct()
        .offset(offset)
        .limit(limit)
    )


@router.get("/all", response_model=list[ChatSessionOut])
async def all_chat(
    offset: int = 0, limit: int = 500, user: User = Depends(get_current_user)
):
    return (
        await user.chat_sessions.all()
        .order_by("-created_at")
        .offset(offset)
        .limit(limit)
    )


@router.get("/{session_id}/all", response_model=list[MessageOut])
async def chat_message(
    session_id: str,
    offset: int = 0,
    limit: int = 200,
    initial: bool = False,
    user: User = Depends(get_current_user),
):
    chat_session = await ChatSession.get_or_none(id=session_id, user=user)
    if not chat_session:
        raise HTTPException(400, "Invalid Chat ID")
    if initial:
        return (
            await chat_session.messages.filter(initial=initial)
            .offset(offset)
            .limit(limit)
        )
    return await chat_session.messages.all().order_by("id").offset(offset).limit(limit)


@router.post("/{session_id}/send")
async def chat(
    session_id: str,
    form: ChatMessageIn,
    user: User = Depends(check_subscription_active),
    mistral=Depends(get_mistral_client),
    openai=Depends(get_openai_client),
):
    if not await ChatSession.filter(id=session_id, user=user).exists():
        raise HTTPException(401, "Unauthorized Access")
    doc = await ChatDocument.filter(chat_id=session_id).first()
    if doc is None:
        raise HTTPException(401, "Uploaded Document Not Found")
    exceeded, limit_value, plan_name = await user.monthly_message_limit_exceeded()
    if exceeded:
        if "free" in plan_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"You have exceeded your daily message limit of {limit_value} messages for the '{plan_name}' plan. Please upgrade your plan or wait until tomorrow to send more messages.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You have exceeded your monthly message limit of {limit_value} messages for the '{plan_name}' plan. Please upgrade your plan or wait until next month to send more messages.",
        )
    user_plan = await Plan.get(stripe_price_id=user.current_plan)

    context = ""
    prompt = form.prompt
    initial = False
    await Usage.create(user=user, usage_count=1, source=doc.name, is_message=True)
    try:
        if not await Message.filter(session_id=session_id).exists():
            context = doc.full_text
            prompt = None
            initial = True
        else:
            embedding_resp = await openai.embeddings.create(
                model="text-embedding-3-large",
                input=form.prompt,
                dimensions=settings.OPENAI_VECTOR_SIZE,
            )
            query_embedding = embedding_resp.data[0].embedding
            similar_chunks = (
                await DocumentChunk.filter(document_id=doc.id)
                .annotate(
                    distance=CosineSimilarity(
                        "embedding", query_embedding, settings.OPENAI_VECTOR_SIZE
                    )
                )
                .order_by("distance")
                .limit(7)
            )
            context = "\n".join(chunk.content for chunk in similar_chunks)
        final_prompt = get_messages_for_llm(
            prompt, context, is_initial_analysis_request=initial
        )
        await Message.create(
            sender="user",
            session_id=session_id,
            content=form.prompt,
            initial=initial,
        )

        async def stream_response() -> AsyncGenerator[str, None]:
            full_response = ""

            response = await mistral.chat.stream_async(
                model=user_plan.model.strip(),
                messages=final_prompt,
                # max_tokens=1000,
                temperature=0.45,
                # top_p=1,
            )

            async for chunk in response:
                delta = chunk.data.choices[0].delta.content
                if delta:
                    full_response += delta
                    yield delta

            await Message.create(
                sender="assistant",
                session_id=session_id,
                content=full_response,
                initial=initial,
            )

        return StreamingResponse(stream_response(), media_type="text/plain")

    except Exception as e:
        return {"error": str(e)}


@router.delete("/{session_id}/delete")
async def session_delete(session_id: str, user: User = Depends(get_current_user)):
    await user.chat_sessions.filter(id=session_id).delete()
    return {"message": "Deleted Successfully"}


@router.put("/{session_id}/update")
async def session_update(
    session_id: str, form: RenameSession, user: User = Depends(get_current_user)
):
    session = await user.chat_sessions.filter(id=session_id).first()
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sesson Not Found")
    session.title = form.title
    await session.save()
    return {"message": "Updated Successfully"}