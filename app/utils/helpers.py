from datetime import datetime, timedelta, timezone
import jwt
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer
from app.core.config import settings
import secrets
import random


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
        to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.ALGORITHM
    )
    return encoded_jwt


def generate_token(length=32):
    return secrets.token_urlsafe(length)


def format_file_size(size_in_bytes: int) -> str:
    """
    Formats a file size (in bytes) into a human-readable string
    using the most appropriate unit (B, KB, MB, GB, TB).

    Args:
        size_in_bytes: The file size in bytes (integer).

    Returns:
        A string representing the formatted file size (e.g., "10.5 KB", "2.1 MB").
    """
    if size_in_bytes < 0:
        return "Invalid Size"
    units = ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"]
    threshold = 1024.0

    for i, unit in enumerate(units):
        if size_in_bytes < threshold:
            if i == 0:
                return f"{size_in_bytes} {unit}"
            return f"{size_in_bytes:.2f} {unit}"
        size_in_bytes /= threshold
    return f"{size_in_bytes:.2f} {units[-1]} (Extremely Large)"


def create_llm_prompt(user_query, retrieved_contexts):
    prompt = f"""
You are a highly intelligent document analysis assistant.
If you are asked what you are and what you can do and what you are trained for then you should only answer that you are a highly intelligent document analysis assistant, your name is "FinDocAI" and then list the thing you can do related to your document analysis assistant personality and always refuse any other task than document analysis and Q&A based on the submitted document.
You should act professional to all the users while talking in a fairly simple and easy to understand language.
Your main task is whenever you get a document you need to extract all the key terms while explaining what the terms are,
Then extract these (document type detection, red Flag detection, risk summarization, coverage gap, hidden fee or fine detection, deadline extraction, complexity Score, missing Info & technical terms extraction & explanation and many more that are important for a user to know based on the document) 
And lastly add a summary of what the document is about what it's used for and how it works and add a conclusion.\n
This should be strickly followed user question is not provided.
Always respond in a strict Markdown
### Context ####\n
{retrieved_contexts}\n
### Question ###\n
{user_query}"""
    return prompt


def build_prompt(context: str, user_prompt: str) -> str:
    return f"""You are an intelligent assistant helping a user understand the contents of a document.

Here is some relevant context extracted from the document:
---
{context}
---

Now, answer the following user question based on the above context:
User: {user_prompt}
Assistant:"""


def get_messages_for_llm(
    user_query: str,
    retrieved_contexts: str,
    chat_history: list = None,
    is_initial_analysis_request: bool = False,
) -> list[dict]:
    # System message: This sets the persona and overall guidelines for the AI
    # Make it less directive about performing a full analysis immediately.
    system_content = """
You are FinDocAI, a highly intelligent document analysis assistant.
Your core expertise is extracting and analyzing financial, legal, and operational information from documents.
You can identify key terms, detect document types, flag risks, summarize financial aspects, extract deadlines, and provide concise summaries and conclusions.
You should always act professional, use simple language, and strictly adhere to the content of the provided document or context.
**Only answer questions or perform analysis based on the document context. Refuse any other tasks.**
Always respond in strict Markdown format.
"""

    messages = [{"role": "system", "content": system_content}]

    # Add historical messages if provided (for multi-turn conversations)
    if chat_history:
        messages.extend(chat_history)

    # User message: This contains the current query and relevant context
    user_message_content = ""

    if is_initial_analysis_request:
        # If it's the very first request (i.e., document upload), tell the AI to do a full analysis.
        user_message_content += f"""### Document Context ####\n{retrieved_contexts}\n
Please perform a comprehensive analysis of this document. Specifically, extract all key terms and explain them. Then, extract the following:
- Document type detection
- Red Flag detection
- Risk summarization
- Coverage gap analysis
- Hidden fee or fine detection
- Deadline extraction
- Complexity Score
- Missing Info & technical terms extraction & explanation

Finally, add a summary of what the document is about, what it's used for, and how it works, followed by a conclusion.
"""
    else:
        # For subsequent messages, provide context and the user's specific question.
        if retrieved_contexts:
            user_message_content += f"### Context ####\n{retrieved_contexts}\n"

        user_message_content += f"### User Question ###\n{user_query}"

    messages.append(
        {"role": "user", "content": user_message_content.strip()}
    )  # .strip() to clean up whitespace

    return messages


def generate_secret_key() -> str:
    return str(random.randint(100000, 99999999)).zfill(8)