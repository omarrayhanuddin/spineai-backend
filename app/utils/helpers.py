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


from typing import List, Dict


def build_spine_diagnosis_prompt(
    session_id: str,
    previous_messages: List[Dict],   # [{"id": int, "sender": "user/ai", "text": str}]
    previous_images: List[Dict],     # [{"image_id": int, "url": str}]
    current_message: str,            # new symptom input
) -> List[Dict]:
    """
    Constructs the OpenAI-compatible messages list for vision-based spine diagnosis.

    Returns:
        List[Dict]: messages[] array for openai.ChatCompletion.create(...)
    """

    # 🧠 1. System prompt
    messages = [{
        "role": "system",
        "content": (
            "You are a medical assistant AI that diagnoses spine-related issues using X-ray/MRI images and patient symptoms.\n"
            "You will receive:\n"
            "- A unique session ID\n"
            "- Prior patient messages and images\n"
            "- The latest input (text + images)\n\n"
            "Your tasks:\n"
            "1. Analyze images and symptom messages.\n"
            "2. If unclear or insufficient, ask for clarification.\n"
            "3. Return a strict JSON with:\n"
            "   - `backend`: includes diagnosis data for internal use\n"
            "   - `user`: a markdown explanation for the patient\n"
            "   (see format below)\n\n"
            "If diagnosis is not possible, leave `findings` and `recommendations` as null, and explain what’s missing in the `user` section."
        )
    }]

    # 🗣️ 2. User message + previous history
    user_message_block = {
        "role": "user",
        "content": []
    }

    # 📄 Session & prior messages
    user_message_block["content"].append({
        "type": "text",
        "text": f"Session ID: {session_id}\n\n## Previous Messages:\n"
    })

    for msg in previous_messages:
        prefix = "User" if msg["sender"] == "user" else "system"
        user_message_block["content"].append({
            "type": "text",
            "text": f"- [{prefix} msg_id {msg['id']}] {msg['text']}"
        })

    # 🖼️ Previous images
    if previous_images:
        user_message_block["content"].append({
            "type": "text",
            "text": "\n## Previous and Current Input Images (Last ones are probably current images):\n"
        })
        for img in previous_images:
            user_message_block["content"].append({
                "type": "text",
                "text": f"Image ID: {img['image_id']}"
            })
            user_message_block["content"].append({
                "type": "image_url",
                "image_url": {"url": img["url"]}
            })

    # ✍️ Current input
    user_message_block["content"].append({
        "type": "text",
        "text": "\n## Current Input Message:"
    })
    user_message_block["content"].append({
        "type": "text",
        "text": f"- [{prefix} msg_id {current_message['id']}] {current_message['text']}"
    })

    # for img in current_images:
    #     user_message_block["content"].append({
    #         "type": "text",
    #         "text": f"Image ID: {img['image_id']}"
    #     })
    #     user_message_block["content"].append({
    #         "type": "image_url",
    #         "image_url": {"url": img["url"]}
    #     })

    # 📤 Response instruction
    user_message_block["content"].append({
        "type": "text",
        "text": (
            "\n## Output Format\n"
            "Respond ONLY in this JSON format:\n\n"
            "{\n"
            "  \"backend\": {\n"
            "    \"is_diagnosed\": true or false,\n"
            "    \"irrelevant_message_ids\": [ ... ],\n"
            "    \"irrelevant_image_ids\": [ ... ],\n"
            "    \"findings\": { ... },\n"
            "    \"recommendations\": { ... }\n"
            "  },\n"
            "  \"user\": \"<markdown explanation for the patient>\"\n"
            "}\n\n"
            "Leave `findings` and `recommendations` as `null` if diagnosis isn't yet possible."
        )
    })

    # 🧩 Add full user message block to messages list
    messages.append(user_message_block)
    return messages


from typing import List, Dict, Optional


def build_post_diagnosis_prompt(
    session_id: str,
    user: Dict,  # {"name": "Omar"}
    findings: Dict,
    recommendations: Dict,
    previous_messages: List[Dict],  # [{"sender": "user"/"ai", "text": str}]
    current_message: Dict           # {"id": int, "text": str}
) -> List[Dict]:
    """
    Constructs OpenAI-compatible messages[] for post-diagnosis AI use.

    Returns:
        List[Dict]: messages for openai.ChatCompletion.create(...)
    """

    def format_findings_md(findings: Dict) -> str:
        parts = []
        for key, value in findings.items():
            title = key.replace("_", " ").title()
            if isinstance(value, dict):
                parts.append(f"### 🦴 {title}")
                for sub_key, sub_value in value.items():
                    parts.append(f"- **{sub_key.replace('_', ' ').title()}**: {sub_value}")
            elif isinstance(value, list):
                parts.append(f"### 📌 {title}")
                parts.extend([f"- {v}" for v in value])
            elif isinstance(value, str):
                parts.append(f"### 📌 {title}\n- {value}")
        return "\n".join(parts) or "No diagnosis data available."

    def format_recommendations_md(recommendations: Dict) -> str:
        if not recommendations:
            return "No previous recommendations available."
        out = []
        for key, values in recommendations.items():
            title = key.replace("_", " ").title()
            if isinstance(values, list):
                formatted = "\n".join([f"  - {v}" for v in values]) if values else "  - None provided"
            elif isinstance(values, str):
                formatted = f"  - {values}" if values.strip() else "  - None provided"
            else:
                formatted = "  - Unknown format"
            out.append(f"- **{title}**:\n{formatted}")
        return "\n".join(out)

    # 🧠 1. System message
    messages = [{
        "role": "system",
        "content": (
            "You are an AI medical assistant specialized in spine-related diagnosis and long-term patient care.\n\n"
            "The patient has already been diagnosed. Your responsibilities now include:\n"
            "1. Reviewing the patient's previous diagnosis and recommendations.\n"
            "2. Answering their follow-up questions and concerns clearly and professionally.\n"
            "3. If appropriate, updating the previous recommendations based on:\n"
            "   - Progress or lack of progress\n"
            "   - New symptoms reported\n"
            "   - Behavioral changes mentioned\n"
            "4. If the user requests a **report**, generate a medical-style progress report using the previous findings and updated recommendations. Format it clearly in proper markdown\n\n"
            "Never attempt to re-diagnose symptoms or images.\n\n"
            "Respond in the following JSON format ONLY:\n\n"
            "{\n"
            "  \"updated_recommendations\": {\n"
            "    \"lifestyle\": [\"...\"],\n"
            "    \"exercise\": [\"...\"],\n"
            "    \"diet\": [\"...\"],\n"
            "    \"followup\": \"...\"\n"
            "  },\n"
            "  \"user\": \"### Markdown-formatted response to show the patient\"\n"
            "}\n\n"
            "If no recommendations have changed, omit `updated_recommendations`.\n"
            "Always include the `user` markdown response except when asked for reponse directl"
        )
    }]

    # 🗣️ 2. User context message
    user_message_block = {
        "role": "user",
        "content": []
    }

    # 📄 Patient info
    user_message_block["content"].append({
        "type": "text",
        "text": f"Patient: {user.get('name', 'Patient')}\nSession ID: {session_id}"
    })

    # 📊 Findings
    user_message_block["content"].append({
        "type": "text",
        "text": "\n### 🧾 Previous Diagnosis:\n" + format_findings_md(findings)
    })

    # ✅ Recommendations
    user_message_block["content"].append({
        "type": "text",
        "text": "\n### ✅ Previous Recommendations:\n" + format_recommendations_md(recommendations)
    })

    # 💬 Previous related memory messages
    if previous_messages:
        user_message_block["content"].append({
            "type": "text",
            "text": "\n### 🧠 Related Messages from Past Conversation:"
        })
        for msg in previous_messages:
            prefix = "User" if msg["sender"] == "user" else "system"
            user_message_block["content"].append({
                "type": "text",
                "text": f"- [{prefix}] {msg['text']}"
            })

    # ✍️ Current patient input
    user_message_block["content"].append({
        "type": "text",
        "text": "\n### 💬 Patient's New Message:"
    })
    user_message_block["content"].append({
        "type": "text",
        "text": f"- [User {current_message}]"

    })

    # Add to full message list
    messages.append(user_message_block)
    return messages




def generate_secret_key() -> str:
    return str(random.randint(100000, 99999999)).zfill(8)