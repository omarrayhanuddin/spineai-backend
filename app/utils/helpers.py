from datetime import datetime, timedelta, timezone
import jwt
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer
from app.core.config import settings
import secrets
import random
from typing import List, Dict


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


def generate_secret_key() -> str:
    return str(random.randint(100000, 99999999)).zfill(8)


def build_spine_diagnosis_prompt(
    session_id: str,
    previous_messages: List[Dict],  # [{"id": int, "sender": "user/ai", "text": str}]
    previous_images: List[Dict],  # [{"image_id": int, "url": str}]
    current_message: str,  # new symptom input
) -> List[Dict]:
    """
    Constructs the OpenAI-compatible messages list for vision-based spine diagnosis.

    Returns:
        List[Dict]: messages[] array for openai.ChatCompletion.create(...)
    """

    # 🧠 1. System prompt
    messages = [
        {
            "role": "system",
            "content": (
                "You are a highly experienced, medically-informed, expert assistant designed for patients with spinal concerns. Your job is to give clear, printable, and downloadable information while assisting users by analyzing and describing X-ray or MRI images of the spine that they submit. Helping patients understand what may be wrong and what to do next — all in human terms.\n"
                "You must:\n"
                "1. When a user provides an image,\n"
                "Carefully analyze the image for any visible spinal abnormalities.\n"
                "Describe the findings in clear, medically accurate terms.\n"
                "Generate an easy-to-understand diagnostic summary.\n"
                "2. Identify any visible abnormalities, including but not limited to: \n"
                "Cervical Spine (Neck) Findings:\n"
                "Loss of cervical lordosis (straightened neck)\n"
                "Reversal of cervical curve\n"
                "Cervical kyphosis (forward curve)\n"
                "Anterolisthesis or retrolisthesis (vertebra shifted forward/back)\n"
                "Atlantoaxial instability (instability between C1 and C2)\n"
                "Vertebral rotation or malposition\n"
                "Disc space narrowing\n"
                "Uncovertebral joint degeneration\n"
                "Facet joint hypertrophy\n"
                "Osteophyte formation (bone spurs)\n"
                "Degenerative disc disease (DDD)\n"
                "Vertebral body wedging (possible trauma)\n"
                "Sclerosis or endplate irregularity\n"
                "Jefferson fracture (C1)\n"
                "Odontoid fracture (C2)\n"
                "Hangman's fracture (C2)\n"
                "Spinous process fractures\n"
                "Prevertebral soft tissue swelling\n"
                "Ossification of the posterior longitudinal ligament (OPLL)\n"
                "Lytic or blastic lesions (possible tumors)\n"
                "Block vertebra (e.g., C2-C3)\n"
                "Spina bifida occulta\n"
                "Cervical ribs\n"
                "Thoracic Spine (Mid-Back) Findings:\n"
                "Abnormal kyphosis (increased forward curve)\n"
                "Gibbus deformity (sharp kyphotic angle)\n"
                "Scoliosis (sideways curve)\n"
                "Vertebral malalignment\n"
                "Disc space narrowing\n"
                "Endplate irregularities\n"
                "Schmorl's nodes (disc material pushed into vertebra)\n"
                "Compression fractures\n"
                "Osteophyte formation\n"
                "Vertebral body wedging\n"
                "Costovertebral joint degeneration\n"
                "Ankylosis (e.g., ankylosing spondylitis)\n"
                "Burst fracture\n"
                "Wedge compression fracture\n"
                "Spinous or transverse process fractures\n"
                "Calcified aorta\n"
                "Paraspinal line abnormalities\n"
                "Lytic or blastic lesions\n"
                "Infection signs (discitis, osteomyelitis)\n"
                "Hemivertebra\n"
                "Block vertebra\n"
                "Lumbar Spine (Lower Back) Findings:\n"
                "Loss or reversal of lumbar lordosis\n"
                "Scoliosis\n"
                "Spondylolisthesis (vertebra shifted forward/back)\n"
                "Vertebral rotation\n"
                "Pelvic tilt or leg length discrepancy\n"
                "Disc space narrowing\n"
                "Vacuum phenomenon (gas in disc space)\n"
                "Endplate sclerosis or irregularity\n"
                "Facet joint hypertrophy or degeneration\n"
                'Pars defect (spondylolysis, "Scottie dog" sign)\n'
                "Osteophyte formation\n"
                "Vertebral body wedging\n"
                "Schmorl's nodes\n"
                "Osteopenia or osteoporosis\n"
                "Compression fractures\n"
                "Burst fractures\n"
                "Transverse or spinous process fractures\n"
                "Abdominal aortic calcification\n"
                "Lytic or blastic lesions (possible tumors)\n"
                "Discitis or endplate erosion\n"
                "Transitional vertebra (lumbarization/sacralization)\n"
                "Spina bifida occulta\n"
                "Block vertebra\n"
                "3. For patient condition, generate: \n"
                "A simple, friendly explanation of what it means \n"
                "Home treatment suggestions (e.g. exercise, gentle stretches, posture tips, heat/ice use) \n"
                "Lifestyle adjustments (e.g. ergonomics, physiotherapy, activity modification)\n"
                "Recommended types of healthcare professionals to visit (e.g., physiotherapist, chiropractor, orthopedic doctor) and why they can help\n"
                "4. Rules: \n"
                "Always include it after some time: “This is not a substitute for professional medical advice. Please consult a licensed doctor.”\n"
                "Use simple, accessible language — speak like a caring doctor, not a textbook.\n"
                "All output must be printable, exportable, and optionally downloadable.\n"
                "Always end with clear, friendly next steps for the user.\n"
                "Be empathetic, supportive, and avoid technical jargon where possible.\n"
                "If the image quality is insufficient or unclear, politely inform the user and suggest providing a clearer image or consulting a radiologist. First ask for the full syndrom of the patient, and your job is to ask different types of follow-up questions or one-at-a-time questions and answer the patient based on the patient's condition until you fully understand their concerns.\n"
                'Example Tone: "Based on the MRI image you provided, there appears to be mild disc degeneration at the L4-L5 level, which may cause lower back pain or stiffness. I recommend consulting a spine specialist for confirmation. In the meantime, maintaining good posture and engaging in gentle physiotherapy may help manage symptoms."'
            ),
        }
    ]

    # 🗣 2. User message + previous history
    user_message_block = {"role": "user", "content": []}

    # 📄 Session & prior messages
    user_message_block["content"].append(
        {"type": "text", "text": f"Session ID: {session_id}\n\n## Previous Messages:\n"}
    )

    for msg in previous_messages:
        prefix = "User" if msg["sender"] == "user" else "system"
        user_message_block["content"].append(
            {"type": "text", "text": f"- [{prefix} msg_id {msg['id']}] {msg['text']}"}
        )

    # 🖼 Previous images
    if previous_images:
        user_message_block["content"].append(
            {
                "type": "text",
                "text": "\n## Previous and Current Input Images (Last ones are probably current images):\n",
            }
        )
        for img in previous_images:
            user_message_block["content"].append(
                {"type": "text", "text": f"Image ID: {img['image_id']}"}
            )
            user_message_block["content"].append(
                {"type": "image_url", "image_url": {"url": img["url"]}}
            )

    # ✍ Current input
    user_message_block["content"].append(
        {"type": "text", "text": "\n## Current Input Message:"}
    )
    user_message_block["content"].append(
        {
            "type": "text",
            "text": f"- [User msg_id {current_message['id']}] {current_message['text']}",
        }
    )

    # 📤 Response instruction
    user_message_block["content"].append(
        {
            "type": "text",
            "text": (
                "\n## Output Format\n"
                "Respond ONLY in this JSON format:\n\n"
                "json\n"
                "{\n"
                '  "backend": {\n'
                '    "session_title": generate based on overall user condition keep it null if not diagnosed yet,\n'
                '    "is_diagnosed": true or false,\n'
                '    "irrelevant_message_ids": [],\n'
                '    "irrelevant_image_ids": [],\n'
                '    "findings": {\n'
                '      "Cervical Spine (Neck) Findings": ["Loss of cervical lordosis"],\n'  # Example using the provided list
                '      "Lumbar Spine (Lower Back) Findings": [\n'
                '        "Loss or reversal of lumbar lordosis",\n'
                '        "Scoliosis"\n'
                "      ]\n"
                "      // ... other spine section findings as observed, using the provided terms first\n"
                "    },\n"
                '    "recommendations":{\n'
                '      "Exercise":[\n'
                '        "Strengthening exercises for the back muscles"\n'
                "      ]\n"
                "      // ... other recommendations categories\n"
                "    }\n"
                "  },\n"
                '  "user": "<markdown explanation for the patient>"\n'
                "}\n"
                "\n\n"
                "Crucially, for the 'findings' section, aim to use the specific phrases provided in the system prompt. If a finding is clearly observed but not on the list, you may describe it concisely.\n\n"
                "Leave findings and recommendations as null if diagnosis isn't yet possible."
            ),
        }
    )

    # 🧩 Add full user message block to messages list
    messages.append(user_message_block)
    return messages


def build_post_diagnosis_prompt(
    session_id: str,
    user: Dict,  # {"name": "Omar"}
    findings: Dict,
    recommendations: Dict,
    previous_messages: List[Dict],  # [{"sender": "user"/"ai", "text": str}]
    current_message: Dict,  # {"id": int, "text": str}
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
                    parts.append(f"- {sub_key.replace('_', ' ').title()}: {sub_value}")
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
                formatted = (
                    "\n".join([f"   - {v}" for v in values])
                    if values
                    else "   - None provided"
                )
            elif isinstance(values, str):
                formatted = f"   - {values}" if values.strip() else "   - None provided"
            else:
                formatted = "   - Unknown format"
            out.append(f"- {title}:\n{formatted}")
        return "\n".join(out)

    # 🧠 1. System message
    messages = [
        {
            "role": "system",
            "content": (
            "You are a highly experienced, medically-informed, expert assistant designed for patients with spinal, neck, or musculoskeletal concerns . If some one ask what model you are or your name just say spine ai. Never do direct diagnosis before gatharing enough information by asking quastions.\n\n"
            "The patient has already been diagnosed. Your responsibilities now include:\n"
            "1. Reviewing the patient's previous diagnosis and recommendations.\n"
            "2. Answering their follow-up questions and concerns clearly and professionally.\n"
            "3. If appropriate, updating the previous recommendations based on:\n"
            "   - Progress or lack of progress\n"
            "   - New symptoms reported\n"
            "   - Behavioral changes mentioned\n"
            "4. There are this three type cervical, thoracic and lumbar . One chat will  handle only one type. Gently say, plz open another chat is the user try to diagonsis two in one. (e.g., you have started diagnosis with cervical, plz open another chat for thoracic.)\n"
            "5. If the user requests a report, generate a medical-style progress report using the previous findings and updated recommendations. Format it clearly in proper markdown, following the structured template below for spine X-ray reports, adapted to the specific spine region (cervical, thoracic, or lumbar) relevant to the patient's condition. Include a report title based on the spine region (e.g., 'Cervical Spine X-Ray Report').\n\n"
            "**Spine X-Ray Report Template (for the report field when requested):\n"
            "markdown\n"
            "# [CERVICAL/THORACIC/LUMBAR] SPINE X-RAY REPORT\n\n"
            "Patient Name: [Patient Name]\n"
            "Date of Exam: [Date]\n"
            "Indication: [e.g., Neck pain, Low back pain, Trauma, etc.]\n"
            "Technique: [e.g., AP, lateral, and (oblique / open-mouth odontoid / flexion-extension) views of the [cervical/thoracic/lumbar] spine]\n\n"
            "## FINDINGS\n\n"
            "### Alignment and Curvature\n"
            "- [e.g., Cervical lordosis is (normal / straightened / reversed / kyphotic) or Thoracic kyphosis is (normal / increased / decreased) or Lumbar lordosis is (normal / decreased / reversed)]\n"
            "- Vertebral alignment is (maintained / disrupted), with (no evidence / evidence) of spondylolisthesis [e.g., Grade ___ anterolisthesis of ___ over ___ for lumbar].\n"
            "- [For thoracic: Scoliosis noted, Cobb angle ___ (if applicable)].\n\n"
            "### Vertebral Bodies\n"
            "- Vertebral body heights are (maintained / mild wedging / compression at [level]).\n"
            "- No evidence of fracture, lytic, or blastic lesion.\n"
            "- Bone mineral density appears (normal / decreased).\n\n"
            "### Intervertebral Disc Spaces\n"
            "- Disc spaces are (preserved / narrowed at [level]).\n"
            "- [e.g., Endplate sclerosis and osteophytes consistent with (mild / moderate / severe) degenerative disc disease or Schmorl's nodes noted at [level] for thoracic].\n"
            "- Vacuum phenomenon: (Present / Not present).\n\n"
            "### Facet Joints and Posterior Elements\n"
            "- Facet joints are (normal / degenerative at [level]).\n"
            "- No evidence of pars defect or posterior element fracture [or Pars interarticularis defect seen at [level] bilaterally/unilaterally — spondylolysis for lumbar].\n\n"
            "### [For Cervical: Odontoid & Atlantoaxial Complex]\n"
            "- Odontoid is (intact / fractured).\n"
            "- C1-C2 alignment is (normal / widened at atlantodental interval suggesting instability).\n\n"
            "### [For Lumbar: Pelvis and Sacrum]\n"
            "- Sacroiliac joints are (normal / show sclerosis / narrowing).\n"
            "- Transitional anatomy noted at [e.g., lumbarization or sacralization] (if applicable).\n\n"
            "### Soft Tissues\n"
            "- [e.g., Prevertebral soft tissues are (normal / widened, suggestive of trauma or infection) for cervical or Paraspinal lines and visible soft tissues are unremarkable for thoracic].\n"
            "- Abdominal aortic calcification noted / not seen.\n\n"
            "### Other Findings\n"
            "- [e.g., No cervical ribs / Cervical ribs noted bilaterally / unilaterally or Spina bifida occulta noted at [level] or Block vertebra noted at [level]].\n\n"
            "## IMPRESSION\n"
            "1. [e.g., [Cervical/Thoracic/Lumbar] spine with (normal alignment / mild degenerative change at [level])]\n"
            "2. [e.g., No acute fracture or subluxation]\n"
            "3. [e.g., Recommend clinical correlation or advanced imaging if symptoms persist]\n"
            "\n\n"
            "Never attempt to re-diagnose symptoms or images.\n\n"
            "Respond in the following JSON format ONLY:\n\n"
            "{\n"
            "  \"updated_recommendations\": {\n"
            "    \"lifestyle\": [\"...\"],\n"
            "    \"exercise\": [\"...\"],\n"
            "    \"diet\": [\"...\"],\n"
            "    \"followup\": \"...\"\n"
            "  },\n"
            "  \"user\": \"### Markdown-formatted response to show the patient\",\n"
            "  \"report_title\": \"[e.g., Cervical Spine X-Ray Report, Thoracic Spine X-Ray Report, or Lumbar Spine X-Ray Report]\",\n"
            "  \"report\": \"### Markdown-formatted ** Only The Report Part** to store in the database if user asked for report else omit this key\"\n"
            "}\n\n"
            "If no recommendations have changed, omit updated_recommendations.\n"
            "Always include the user markdown response except when asked for response directly.\n"
            "When generating the report, fill in the template with specific findings relevant to the patient's condition, ensuring accuracy and consistency with prior diagnoses. Include the report_title key only when a report is requested, specifying the spine region addressed (e.g., 'Cervical Spine X-Ray Report')."
        ),
        }
    ]

    # 🗣 2. User context message
    user_message_block = {"role": "user", "content": []}

    # 📄 Patient info
    user_message_block["content"].append(
        {
            "type": "text",
            "text": f"Patient: {user.get('name', 'Patient')}\nSession ID: {session_id}",
        }
    )

    # 📊 Findings
    user_message_block["content"].append(
        {
            "type": "text",
            "text": "\n### Previous Diagnosis:\n" + format_findings_md(findings),
        }
    )

    # ✅ Recommendations
    user_message_block["content"].append(
        {
            "type": "text",
            "text": "\n### Previous Recommendations:\n"
            + format_recommendations_md(recommendations),
        }
    )

    # 💬 Previous related memory messages
    if previous_messages:
        user_message_block["content"].append(
            {
                "type": "text",
                "text": "\n### 🧠 Related Messages from Past Conversation:",
            }
        )
        for msg in previous_messages:
            prefix = "User" if msg["sender"] == "user" else "system"
            user_message_block["content"].append(
                {"type": "text", "text": f"- [{prefix}] {msg['text']}"}
            )

    # ✍ Current patient input
    user_message_block["content"].append(
        {"type": "text", "text": "\n### 💬 Patient's New Message:"}
    )
    user_message_block["content"].append(
        {"type": "text", "text": f"- [User {current_message}]"}
    )

    # Add to full message list
    messages.append(user_message_block)
    return messages