diagnostic_prompt = """
You are a spine diagnosis assistant. Ask users for spinal symptoms, history, or X-ray/MRI images.
DO NOT generate a diagnosis until you have enough detail.

If diagnosis is complete, return this JSON format:

{
  "cervical": {...},
  "thoracic": {...},
  "lumbar": {...},
  "confidence_score": 0.89,
  "recommendations": [...]
}

Also return this field when applicable:
"irrelevant_image_ids": [list of image message IDs that are not helpful]

Only include that field if you have seen unrelated or duplicate X-ray/MRI images.
"""


from pydantic import BaseModel
from typing import List, Optional

class ChatInput(BaseModel):
    user_id: str
    message: Optional[str]
    images: List[str] = []

class SpineSection(BaseModel):
    alignment_and_curvature: str
    vertebral_bodies: str
    disc_spaces: str
    facet_joints: str
    odontoid_complex: str = ""
    soft_tissues: str
    other_findings: str
    impression: str

class SpineReportSchema(BaseModel):
    cervical: SpineSection
    thoracic: SpineSection
    lumbar: SpineSection
    confidence_score: float
    recommendations: List[str]


from tortoise.models import Model
from tortoise import fields

class User(Model):
    id = fields.IntField(pk=True)
    username = fields.CharField(max_length=255, unique=True)
    state = fields.CharField(max_length=50, default="collecting")

class SpineReport(Model):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="reports")
    cervical = fields.JSONField()
    thoracic = fields.JSONField()
    lumbar = fields.JSONField()
    confidence = fields.FloatField()
    created_at = fields.DatetimeField(auto_now_add=True)

class ChatMessage(Model):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="messages")
    role = fields.CharField(max_length=10)  # "user" or "assistant"
    content = fields.TextField(null=True)
    image_b64 = fields.TextField(null=True)
    is_image_relevant = fields.BooleanField(null=True)
    embedding = fields.JSONField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)


import openai
import os
from prompts import diagnostic_prompt

openai.api_key = os.getenv("OPENAI_API_KEY")

async def embed_text(text: str):
    res = openai.Embedding.create(
        model="text-embedding-3-large",
        input=[text]
    )
    return res["data"][0]["embedding"]

async def ask_gpt_with_context(messages: list):
    response = openai.ChatCompletion.create(
        model="gpt-4-vision-preview",
        messages=[{"role": "system", "content": diagnostic_prompt}] + messages,
        temperature=0.3
    )
    return response.choices[0].message["content"]


from fastapi import FastAPI, HTTPException
from schemas import ChatInput
from db import init_db
from models import User, ChatMessage, SpineReport
from gpt_utils import ask_gpt_with_context, embed_text
import json
import numpy as np
from tortoise.expressions import Q

app = FastAPI()

@app.on_event("startup")
async def startup():
    await init_db()

def cosine_similarity(a, b):
    a = np.array(a)
    b = np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

@app.post("/chat")
async def chat(data: ChatInput):
    user = await User.get_or_none(username=data.user_id)
    if not user:
        user = await User.create(username=data.user_id)

    if user.state == "diagnosed":
        return {"response": "Diagnosis is already complete. Feel free to ask anything else!"}

    # Handle user input
    embedding = await embed_text(data.message or "")
    text_msg = await ChatMessage.create(
        user=user,
        role="user",
        content=data.message,
        embedding=embedding
    )

    image_ids = []
    for img in data.images:
        msg = await ChatMessage.create(user=user, role="user", content="(image)", image_b64=img)
        image_ids.append(msg.id)

    # Retrieve relevant chat history by embedding similarity
    past_msgs = await ChatMessage.filter(user=user, embedding__not_isnull=True)
    sims = [(msg, cosine_similarity(msg.embedding, embedding)) for msg in past_msgs if msg.content]
    relevant_msgs = sorted(sims, key=lambda x: -x[1])[:10]

    chat_history = []

    for msg, _ in relevant_msgs:
        chat_history.append({
            "role": msg.role,
            "content": msg.content
        })

    # Include relevant images (or new ones with unknown relevance)
    image_msgs = await ChatMessage.filter(user=user).filter(Q(is_image_relevant=True) | Q(is_image_relevant=None))
    for img in image_msgs:
        if img.image_b64:
            chat_history.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": "(X-ray/MRI)"},
                    {"type": "image_url", "image_url": {"url": img.image_b64}}
                ]
            })

    response = await ask_gpt_with_context(chat_history)
    await ChatMessage.create(user=user, role="assistant", content=response)

    # Check for diagnosis
    if '"cervical":' in response and '"confidence_score":' in response:
        try:
            report_json = json.loads(response)
            await SpineReport.create(
                user=user,
                cervical=report_json["cervical"],
                thoracic=report_json["thoracic"],
                lumbar=report_json["lumbar"],
                confidence=report_json["confidence_score"]
            )
            user.state = "diagnosed"
            await user.save()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Could not save diagnosis: {e}")

    # Check for irrelevant image feedback
    try:
        parsed = json.loads(response)
        if "irrelevant_image_ids" in parsed:
            await ChatMessage.filter(id__in=parsed["irrelevant_image_ids"]).update(is_image_relevant=False)
    except Exception:
        pass  # if response is not pure JSON, skip image flagging

    return {"response": response}
