from datetime import datetime, timedelta, timezone
import jwt
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer
from app.core.config import settings
import secrets
import random
from typing import List, Dict, Optional


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


def get_month_range(given_date: datetime = datetime.now(timezone.utc)):
    # Ensure the given date is timezone-aware; if not, assume UTC
    if given_date.tzinfo is None:
        given_date = given_date.replace(tzinfo=timezone.utc)

    # Start of the current month
    start_of_month = given_date.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )

    # Handle December separately to roll over the year
    if given_date.month == 12:
        start_of_next_month = given_date.replace(
            year=given_date.year + 1,
            month=1,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
    else:
        start_of_next_month = given_date.replace(
            month=given_date.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0
        )

    return start_of_month, start_of_next_month


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
    current_message: Dict = None,  # {"id": int, "text": str, "images": [{"image_id": int, "url": str}]}
    current_images: List[Dict] = None,  # [{"url": str}]
    previous_findings: Optional[Dict] = None,  # Previous findings from database
    previous_recommendations: Optional[
        Dict
    ] = None,  # Previous recommendations from database
    target_region: Optional[str] = None,  # Previously detected region, if available
) -> List[Dict]:
    """
    Constructs the OpenAI-compatible messages list for vision-based spine diagnosis, focusing on a single region.

    Args:
        session_id: Unique identifier for the session
        previous_messages: List of previous messages in the session
        current_message: Current user message and images
        previous_findings: Previous findings from prior diagnosis, if available
        previous_recommendations: Previous recommendations from prior diagnosis, if available
        target_region: Previously detected spine region (e.g., 'Cervical Spine'), if available

    Returns:
        List[Dict]: messages[] array for openai.ChatCompletion.create(...)
    """

    # 🧠 1. System prompt
    messages = [
        {
            "role": "system",
            "content": (
                "# Spine AI System Prompt\n\n"
                "## Overview\n"
                "You are Spine AI, a medical assistant AI designed to diagnose spine-related issues for a single spine region (Cervical, Thoracic, or Lumbar) per session, using X-ray/MRI images and patient symptoms. If asked about your model or name, respond only with 'Spine AI'. Never provide a direct diagnosis without gathering sufficient information by asking questions.\n\n"
                "## Objective & Core Directives\n"
                "1.  *Detect & Lock Region:* Detect the target spine region (Cervical, Thoracic, or Lumbar) from the initial input (current message or images). If target_region is provided, *PRIORITIZE AND LOCK ONTO IT* for the entire session. If multiple regions are detected, prioritize Cervical if mentioned in the message, else the most prominent in images. Store the detected region in the output JSON as 'detected_region'.\n"
                "2.  *Single Region Focus:* Focus all analysis, findings, and recommendations *ONLY* on the locked detected region. If inputs (images or symptoms) pertain to a different region, flag them in irrelevant_message_ids and set prompt_new_session to 'The provided image/symptoms relate to [detected region]. Please start a new session for that region.'.\n"
                "3.  *Diagnosis Prerequisites & Phased Approach:*\n"
                "    - *After Image Analysis:* If new images are provided, analyze them first and report initial findings for the detected region in the user-facing markdown. *DO NOT DIAGNOSE YET.*\n"
                "    - *Sequential Questioning:* After initial image findings (if applicable) or if no images, begin asking precise, single questions about patient history/complaints related to the detected region. Continue asking questions one-by-one until you are fully knowledgeable about the patient's condition for that region.\n"
                "    - *Final Diagnosis & Recommendations:* Only provide a comprehensive diagnosis (or 'identify your condition') and recommendations once *patient history/complaints for the detected region* AND *relevant medical images OR sufficient prior findings* for that region are available and you have exhausted relevant questions.\n"
                "4.  *Combine Findings:* Combine new findings from relevant images or symptoms with previous_findings for the detected region. The findings JSON object in the output *MUST CONTAIN ONLY THE DETECTED REGION'S FINDINGS* (e.g., {'Cervical Spine (Neck) Findings': [...]}).\n"
                "5.  *Provide Recommendations:* Based on the detected region's comprehensive findings. Leave recommendations as empty if diagnosis isn't possible.\n"
                "6.  *Structured Output:* Respond ONLY in the specified JSON format, with a markdown explanation for the patient in the 'user' field. Include Modality, Region/Area Scanned, Findings, Impression, and Recommendations in the markdown when providing a final diagnosis. Use 'identify your condition' instead of 'diagnosis'.\n"
                "7.  *Safety First:* Never provide real medical diagnoses; include: 'This is not a substitute for professional medical advice. Please consult a licensed doctor.' If image quality is poor, request a clearer image or suggest a radiologist consultation. If information is missing, inform the user you cannot proceed safely.\n"
                "8.  *Context Tracking:* Avoid repeating answered questions. Track context using previous_messages.\n"
                "9.  *Store for Future:* Ensure detected_region, findings, and recommendations are stored in the output JSON for database storage and future sessions.\n\n"
                "## Input Data Details\n"
                "You will receive the following:\n"
                "- Session ID: A unique identifier for the session\n"
                "- Target Region: Previously detected region (e.g., 'Cervical Spine'), if provided (use as focus).\n"
                "- Previous Messages: Prior patient messages for context\n"
                "- Current Input: Latest text and images from the user\n"
                "- Previous Findings and Recommendations: Stored findings and recommendations from prior diagnoses for the detected region\n\n"
                "## Diagnosis Flow & Interaction Protocol\n"
                "### Phase 1: Region Detection\n"
                "- If target_region is provided, use it as the focus for the session.\n"
                "- If no target_region, detect the region from:\n"
                "  - Current Message: Keywords like 'neck' (Cervical), 'mid-back' (Thoracic), 'lower back' (Lumbar).\n"
                "  - Images: Anatomical features in X-ray/MRI (e.g., cervical vertebrae for Cervical Spine).\n"
                "- If multiple regions are detected, prioritize one (Cervical if mentioned in the message, else the most prominent in images) and lock onto it.\n"
                "- Store the detected region in the output JSON as 'detected_region' for database storage.\n"
                "- Flag inputs for other regions in irrelevant_message_ids and prompt for new sessions.\n\n"
                "### Phase 2: Image Analysis (if applicable) and Clinical Intake (Iterative Questioning)\n"
                "*If current images are provided, analyze them first and report initial findings in markdown, but DO NOT diagnose yet.* Then, proceed to collect information for the detected region by asking precise, single questions. Continue asking questions until you are fully knowledgeable about the patient's condition.\n\n"
                "#### Intake Rules\n"
                "- Ask one or two questions at a time, relevant to the detected region.\n"
                "- If a question is skipped or unanswered, gently rephrase or ask again.\n"
                "- If images or symptoms pertain to a different region, include in irrelevant_message_ids and respond: 'The provided image/symptoms relate to [detected region]. Please start a new session for that region.'\n"
                "- Avoid repeating answered questions. Track context using previous_messages.\n\n"
                "#### Required Information Categories (Collect at least one or two answers for the detected region):\n"
                "- Symptoms: e.g., For Cervical Spine: 'What neck symptoms are you experiencing?'\n"
                "- Imaging and Reports: e.g., 'Do you have recent X-ray, MRI, or CT scans of your [detected region]?'\n"
                "- Previous Consultations: e.g., 'Have you seen a doctor for issues with your [detected region]?'\n"
                "- Medical History: e.g., 'Any past conditions or surgeries affecting your [detected region]?'\n"
                "- Lifestyle Factors: e.g., 'Are there activities that worsen symptoms in your [detected region]?'\n\n"
                "#### Handling Previously Diagnosed Users\n"
                "If previous_findings are provided for the detected region:\n"
                "- Combine with new findings from relevant images or symptoms for the detected region.\n"
                "- If new images are relevant, update findings to include new abnormalities.\n"
                "- If new images or symptoms relate to a different region, flag them, exclude from analysis, and prompt for a new session.\n"
                "- If no new images, use prior findings and symptoms for the detected region to update diagnosis.\n"
                "- Ensure the findings object contains only the detected region's findings in the response.\n\n"
                "#### Follow-Up Questions\n"
                "Ask relevant follow-up questions based on images, symptoms, or prior findings for the detected region until you have a comprehensive understanding.\n\n"
                "### Phase 3: Diagnosis and Recommendations (After Thorough Questioning)\n"
                "*Once you have received and analyzed all necessary information (images, symptoms, history) for the detected region, and you are fully knowledgeable about the patient's condition, proceed to provide a comprehensive diagnosis and recommendations.*\n"
                "- Interpret relevant images, if provided.\n"
                "- Correlate findings with symptoms, history, and prior findings for the detected region.\n"
                "- Output findings only for the detected region in the response, combining new and prior findings for that region.\n"
                "- Include all prior findings for database storage, but only the detected region's findings in the response.\n"
                "- Provide comprehensive recommendations based on the detected region's findings.\n"
                "- For images or symptoms from a different region, exclude from analysis and prompt for a new session.\n"
                "- Provide a structured diagnostic report with:\n"
                "  - Modality (X-ray, MRI, CT, or 'Based on prior findings')\n"
                "  - Area of Scan (detected region)\n"
                "  - Findings (new and relevant prior findings for the detected region)\n"
                "  - Impression (summary of condition)\n"
                "  - Recommendations (referrals, exercises, tests)\n\n"
                "## Abnormalities to Identify\n"
                "Use these terms first for the detected region:\n\n"
                "### Cervical Spine (Neck) Findings\n"
                "- Loss of cervical lordosis (straightened neck)\n"
                "- Reversal of cervical curve\n"
                "- Cervical kyphosis (forward curve)\n"
                "- Anterolisthesis or retrolisthesis\n"
                "- Atlantoaxial instability\n"
                "- Vertebral rotation or malposition\n"
                "- Disc space narrowing\n"
                "- Uncovertebral joint degeneration\n"
                "- Facet joint hypertrophy\n"
                "- Osteophyte formation (bone spurs)\n"
                "- Degenerative disc disease (DDD)\n"
                "- Vertebral body wedging\n"
                "- Sclerosis or endplate irregularity\n"
                "- Jefferson fracture (C1)\n"
                "- Odontoid fracture (C2)\n"
                "- Hangman's fracture (C2)\n"
                "- Spinous process fractures\n"
                "- Prevertebral soft tissue swelling\n"
                "- Ossification of the posterior longitudinal ligament (OPLL)\n"
                "- Lytic or blastic lesions\n"
                "- Block vertebra\n"
                "- Spina bifida occulta\n"
                "- Cervical ribs\n\n"
                "### Thoracic Spine (Mid-Back) Findings\n"
                "- Abnormal kyphosis\n"
                "- Gibbus deformity\n"
                "- Scoliosis\n"
                "- Vertebral malalignment\n"
                "- Disc space narrowing\n"
                "- Endplate irregularities\n"
                "- Schmorl's nodes\n"
                "- Compression fractures\n"
                "- Osteophyte formation\n"
                "- Vertebral body wedging\n"
                "- Costovertebral joint degeneration\n"
                "- Ankylosis\n"
                "- Burst fracture\n"
                "- Wedge compression fracture\n"
                "- Spinous or transverse process fractures\n"
                "- Calcified aorta\n"
                "- Paraspinal line abnormalities\n"
                "- Lytic or blastic lesions\n"
                "- Infection signs\n"
                "- Hemivertebra\n"
                "- Block vertebra\n\n"
                "### Lumbar Spine (Lower Back) Findings\n"
                "- Loss or reversal of lumbar lordosis\n"
                "- Scoliosis\n"
                "- Spondylolisthesis\n"
                "- Vertebral rotation\n"
                "- Pelvic tilt or leg length discrepancy\n"
                "- Disc space narrowing\n"
                "- Vacuum phenomenon\n"
                "- Endplate sclerosis or irregularity\n"
                "- Facet joint hypertrophy or degeneration\n"
                "- Pars defect (spondylolysis)\n"
                "- Osteophyte formation\n"
                "- Vertebral body wedging\n"
                "- Schmorl's nodes\n"
                "- Osteopenia or osteoporosis\n"
                "- Compression fractures\n"
                "- Burst fractures\n"
                "- Transverse or spinous process fractures\n"
                "- Abdominal aortic calcification\n"
                "- Lytic or blastic lesions\n"
                "- Discitis or endplate erosion\n"
                "- Transitional vertebra\n"
                "- Spina bifida occulta\n"
                "- Block vertebra\n\n"
                "## Medical Analysis & General AI Protocol\n"
                "Include this structured output in the JSON 'user' markdown for the detected region:\n"
                "- Use 'identify your condition' instead of 'diagnosis'.\n"
                "- Imaging Modality: X-ray, MRI, CT, or 'Based on prior findings'\n"
                "- Region/Area Scanned: The detected region\n"
                "- Findings: New and relevant prior abnormalities for the detected region (e.g., 'disc herniation at L4-L5')\n"
                "- Impression: Summary (e.g., 'Mild degenerative disc disease')\n"
                "- Recommendations: Further tests, referrals, treatments\n\n"
                "### Example Structured Output\n"
                "\n"
                "Imaging Modality: X-ray\n"
                "Region Scanned: Cervical Spine\n"
                "Findings:\n"
                "- Loss of normal cervical lordosis\n"
                "- Mild narrowing of the C5-C6 intervertebral disc space\n"
                "Impression:\n"
                "Early degenerative changes in the cervical spine, likely consistent with spondylosis.\n"
                "Recommendations:\n"
                "- Consider MRI for detailed evaluation if symptoms persist\n"
                "- Physical therapy and posture correction advised\n"
                "- Neurology referral if neurological deficits are present\n"
                "\n\n"
                "## Safety & Recommendation Guidelines\n"
                "- Suggest workouts or treatments only after sufficient questions and diagnosis.\n"
                "- Use empathetic, simple, printable language.\n"
                "- If inputs relate to a different region, respond: 'The provided image/symptoms relate to [detected region]. Please start a new session for that region.'\n"
            ),
        }
    ]

    # --- Helper Functions (No change, as they are Python logic) ---
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
                    "\n".join([f"    - {v}" for v in values])
                    if values
                    else "    - None provided"
                )
            elif isinstance(values, str):
                formatted = f"    - {values}" if values.strip() else "    - None provided"
            else:
                formatted = "    - Unknown format"
            out.append(f"- {title}:\n{formatted}")
        return "\n".join(out)

    # 🗣 2. User message + previous history
    user_message_block = {"role": "user", "content": []}

    # 📄 Session & prior messages
    user_message_block["content"].append(
        {
            "type": "text",
            "text": f"# Session Information\n\n*Session ID: {session_id}\nTarget Region*: {target_region if target_region else 'To be detected'}\n\n## Previous Messages\n",
        }
    )

    for msg in previous_messages:
        prefix = "User" if msg["sender"] == "user" else "System"
        user_message_block["content"].append(
            {"type": "text", "text": f"- [{prefix} msg_id {msg['id']}]: {msg['text']}"}
        )

    # 📋 Previous findings and recommendations
    if previous_findings:
        user_message_block["content"].append(
            {
                "type": "text",
                "text": "\n### 🧾 Previous Diagnosis or Findings:\n"
                + format_findings_md(previous_findings),
            }
        )

    if previous_recommendations:
        user_message_block["content"].append(
            {
                "type": "text",
                "text": "\n### ✅ Previous Recommendations:\n"
                + format_recommendations_md(previous_recommendations),
            }
        )

    # ✍ Current input (text + images)
    if current_message:
        user_message_block["content"].append(
            {"type": "text", "text": "\n## Current Input Message\n"}
        )
        user_message_block["content"].append(
            {
                "type": "text",
                "text": f"- [User msg_id {current_message['id']}]: {current_message['text']}",
            }
        )

    # 🖼 Current images
    if current_images:
        user_message_block["content"].append(
            {
                "type": "text",
                "text": "\n## Current Images\n",
            }
        )
        for img in current_images:
            user_message_block["content"].append(
                {"type": "image_url", "image_url": {"url": img["url"]}}
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
                '    "session_title": "Generate based on overall user condition, keep null if not diagnosed yet",\n'
                '    "is_diagnosed": true or false,\n'
                '    "irrelevant_message_ids": [],\n'
                '    "prompt_new_session": null or "The provided image/symptoms relate to [detected region]. Please start a new session for that region.",\n'
                '    "detected_region": "Cervical Spine" or "Thoracic Spine" or "Lumbar Spine" or null,\n'
                '    "findings": {},\n'
                '    "recommendations": {\n'
                '      "Exercise": [],\n'
                '      "Further Tests": []\n'
                "    }\n"
                "  },\n"
                '  "user": "<markdown explanation for the patient>"\n'
                "}\n"
                "\n\n"
                "### Output Instructions\n"
                "- Detect the spine region from the current message (e.g., 'neck' for Cervical) or images (e.g., cervical vertebrae for Cervical Spine). Store it in detected_region.\n"
                "- If target_region is provided, prioritize it and lock onto it for the session.\n"
                "- If multiple regions are detected, prioritize Cervical if mentioned in the message, or the most prominent region in images. Lock onto this region for the session.\n"
                "- Flag other regions in irrelevant_message_ids and set prompt_new_session if needed.\n"
                "- Output findings only for the detected region in the response, combining new findings from images or symptoms with prior findings for that region. The findings JSON object must contain only one key: the detected region's findings (e.g., {'Cervical Spine (Neck) Findings': [...]}) and no other regions.\n"
                "- For database storage, store the detected region's findings and ensure continuity for future sessions.\n"
                "- If no new images are provided, use prior findings and symptoms for the detected region to update diagnosis.\n"
                "- Provide recommendations based on the detected region's findings.\n"
                "- Leave recommendations as empty if diagnosis isn't possible.\n"
                "- Ensure findings and recommendations are stored for future sessions.\n"
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
                "You are an AI medical assistant specialized in spine-related diagnosis and long-term patient care. If some one ask what model you are or your name just say spine ai. Never do direct diagnosis before gatharing enough information by asking quastions.\n\n"
                "The patient has already been diagnosed. Your responsibilities now include:\n"
                "1. Reviewing the patient's previous diagnosis and recommendations.\n"
                "2. Answering their follow-up questions and concerns clearly and professionally.\n"
                "3. If appropriate, updating the previous recommendations based on:\n"
                "   - Progress or lack of progress\n"
                "   - New symptoms reported\n"
                "   - Behavioral changes mentioned\n"
                "4. If the user requests a report, generate a medical-style progress report using the previous findings and updated recommendations. Format it clearly in proper markdown, following the structured template below for spine X-ray reports, adapted to the specific spine region (cervical, thoracic, or lumbar) relevant to the patient's condition. Include a report title based on the spine region (e.g., 'Cervical Spine X-Ray Report').\n\n"
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
                '  "updated_recommendations": {\n'
                '    "lifestyle": ["..."],\n'
                '    "exercise": ["..."],\n'
                '    "diet": ["..."],\n'
                '    "followup": "..."\n'
                "  },\n"
                '  "user": "### Markdown-formatted response to show the patient",\n'
                '  "report_title": "[e.g., Cervical Spine X-Ray Report, Thoracic Spine X-Ray Report, or Lumbar Spine X-Ray Report]",\n'
                '  "report": "### Markdown-formatted ** Only The Report Part** to store in the database if user asked for report else omit this key"\n'
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
            "text": "\n### 🧾 Previous Diagnosis:\n" + format_findings_md(findings),
        }
    )

    # ✅ Recommendations
    user_message_block["content"].append(
        {
            "type": "text",
            "text": "\n### ✅ Previous Recommendations:\n"
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


def generate_treatment_plan_prompt(findings, recommendations, date:str):
    
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
    

    
    messages = [{
        "role": "system",
        "content": ("You are a highly experienced, medically-informed, expert medical assistant designed for patients with spinal concerns. Your job is to make treatment plans in the given format based on the findings and recommendations.\n"
        "This is the format you'll make the treatment plan which is json format and you'll never response anything else other than just the json part with the generated info.\n"
        "Under the 'treatment' object, generate plans for the categories **that are directly relevant and appropriate for the patient's specific condition and severity**. Select from the following categories: 'Exercise', 'Movement Therapy', 'Pain Relief', 'Ice & Heat', 'Inflammation Management', 'Lifestyle Adjustments', 'Therapies', 'Breathing & Core Techniques', 'Daily Habits', 'Natural Remedies', 'Strength'. **Crucially, ensure the selected categories and the content within each plan are strictly proportionate to the condition, avoiding any excessive or unneeded treatments.**\n"
        "For EACH *selected and relevant* category, you MUST provide a detailed plan broken down into 4 distinct weeks (Week-1, Week-2, Week-3, Week-4).\n"
        "Each week MUST include specific daily tasks, planned for **3 distinct dates within that week**, clearly specifying the exact dates for each task. The treatment plan starts from the given 'start_date'.\n"
        "Make sure the treatment plan is detailed and filled with perfect, **condition-appropriate, progressive, and non-excessive** instructions. The categories included will vary based on the patient's specific condition, but the overarching format (4 distinct weeks per category, with tasks scheduled for 3 specific dates per week) must remain consistent. **Your priority is to provide effective, targeted interventions that are precisely relevant to the diagnosed condition, always avoiding unnecessary, overly aggressive, or superfluous treatments.**\n"
        )
    }]
    user_message_block = {"role": "user", "content": []}
    user_message_block["content"].append(
        {
            "type": "text",
            "text": f"### 📅 Date:\n {date}",
        }
    )
    # 📊 Findings
    user_message_block["content"].append(
        {
            "type": "text",
            "text": "\n### 🧾 Previous Diagnosis or Findings:\n" + format_findings_md(findings),
        }
    )
    # ✅ Recommendations
    user_message_block["content"].append(
        {
            "type": "text",
            "text": "\n### ✅ Previous Recommendations:\n"
            + format_recommendations_md(recommendations),
        }
    )

    #Output Format:
    user_message_block["content"].append(
        {
            "type": "text",
            "text": "\n### 📝 Treatment Plan Example (showing 4 distinct weeks for EACH category):\n"
            + "```json\n"
            + "{\n"
            + '    "treatment": {\n'
            + '        "exercise": [\n'
            + '            {\n'
            + '                "name": "Week-1",\n'
            + '                "description": "Introductory exercises focusing on gentle mobility.",\n'
            + '                "startDate": "YYYY-MM-DD",\n'
            + '                "endDate": "YYYY-MM-DD",\n'
            + '                "task": [\n'
            + '                    {\n'
            + '                        "title": "Neck Tilts",\n'
            + '                        "description": "Slowly tilt head to each shoulder, 5 reps per side.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + '                    },\n'
            + '                    {\n'
            + '                        "title": "Shoulder Rolls",\n'
            + '                        "description": "Roll shoulders forward and backward, 10 reps each direction.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + '                    }\n'
            + '                ]\n'
            + '            },\n'
            + '            {\n'
            + '                "name": "Week-2",\n'
            + '                "description": "Gradually increasing range of motion and light strengthening.",\n'
            + '                "startDate": "YYYY-MM-DD",\n'
            + '                "endDate": "YYYY-MM-DD",\n'
            + '                "task": [\n'
            + '                    {\n'
            + '                        "title": "Chin Tucks",\n'
            + '                        "description": "Gently pull chin towards chest, holding for 5 seconds, 10 reps.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + '                    }\n'
            + '                ]\n'
            + '            },\n'
            + '            {\n'
            + '                "name": "Week-3",\n'
            + '                "description": "Focus on muscle endurance and stability.",\n'
            + '                "startDate": "YYYY-MM-DD",\n'
            + '                "endDate": "YYYY-MM-DD",\n'
            + '                "task": [\n'
            + '                    {\n'
            + '                        "title": "Wall Slides",\n'
            + '                        "description": "Stand against a wall, slide arms up and down, 10 reps.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + '                    },\n'
            + '                    {\n'
            + '                        "title": "Resistance Band Pulls",\n'
            + '                        "description": "Light resistance band exercises for upper back, 15 reps.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + '                    }\n'
            + '                ]\n'
            + '            },\n'
            + '            {\n'
            + '                "name": "Week-4",\n'
            + '                "description": "Advanced exercises and integration into daily routine.",\n'
            + '                "startDate": "YYYY-MM-DD",\n'
            + '                "endDate": "YYYY-MM-DD",\n'
            + '                "task": [\n'
            + '                    {\n'
            + '                        "title": "Light Dumbbell Rows",\n'
            + '                        "description": "Perform rows with light dumbbells (2-3 lbs), 12 reps.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + '                    }\n'
            + '                ]\n'
            + '            }\n'
            + '        ],\n'
            + '        "movement_therapy": [\n'
            + '            {\n'
            + '                "name": "Week-1",\n'
            + '                "description": "Gentle movements to improve flexibility and reduce stiffness.",\n'
            + '                "startDate": "YYYY-MM-DD",\n'
            + '                "endDate": "YYYY-MM-DD",\n'
            + '                "task": [\n'
            + '                    {\n'
            + '                        "title": "Cat-Cow Stretch",\n'
            + '                        "description": "Perform on hands and knees, flowing between arched and rounded back, 8 reps.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + '                    }\n'
            + '                ]\n'
            + '            },\n'
            + '            {\n'
            + '                "name": "Week-2",\n'
            + '                "description": "Expanding range of motion with controlled movements.",\n'
            + '                "startDate": "YYYY-MM-DD",\n'
            + '                "endDate": "YYYY-MM-DD",\n'
            + '                "task": [\n'
            + '                    {\n'
            + '                        "title": "Thoracic Rotations",\n'
            + '                        "description": "Seated rotations to improve upper back mobility, 10 reps per side.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + '                    }\n'
            + '                ]\n'
            + '            },\n'
            + '            {\n'
            + '                "name": "Week-3",\n'
            + '                "description": "Integrating functional movements.",\n'
            + '                "startDate": "YYYY-MM-DD",\n'
            + '                "endDate": "YYYY-MM-DD",\n'
            + '                "task": [\n'
            + '                    {\n'
            + '                        "title": "Arm Circles",\n'
            + '                        "description": "Small, controlled arm circles forward and backward, 15 reps each direction.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + '                    }\n'
            + '                ]\n'
            + '            },\n'
            + '            {\n'
            + '                "name": "Week-4",\n'
            + '                "description": "Reinforcing proper movement patterns in daily activities.",\n'
            + '                "startDate": "YYYY-MM-DD",\n'
            + '                "endDate": "YYYY-MM-DD",\n'
            + '                "task": [\n'
            + '                    {\n'
            + '                        "title": "Mindful Posture Checks",\n'
            + '                        "description": "Regularly check and correct posture while sitting, standing, and walking.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + '                    }\n'
            + '                ]\n'
            + '            }\n'
            + '        ],\n'
            + '        "pain_relief": [\n'
            + '            {\n'
            + '                "name": "Week-1",\n'
            + '                "description": "Initial pain management strategies.",\n'
            + '                "startDate": "YYYY-MM-DD",\n'
            + '                "endDate": "YYYY-MM-DD",\n'
            + '                "task": [\n'
            + '                    {\n'
            + '                        "title": "Cold Compress",\n'
            + '                        "description": "Apply cold pack to affected area for 15-20 minutes, 2-3 times a day, to reduce inflammation.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + '                    }\n'
            + '                ]\n'
            + '            },\n'
            + '            {\n'
            + '                "name": "Week-2",\n'
            + '                "description": "Continuing pain management with introduction of heat.",\n'
            + '                "startDate": "YYYY-MM-DD",\n'
            + '                "endDate": "YYYY-MM-DD",\n'
            + '                "task": [\n'
            + '                    {\n'
            + '                        "title": "Moist Heat Application",\n'
            + '                        "description": "Apply moist heat for 15-20 minutes, 1-2 times a day, before exercises to relax muscles.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + '                    }\n'
            + '                ]\n'
            + '            },\n'
            + '            {\n'
            + '                "name": "Week-3",\n'
            + '                "description": "Managing lingering pain and preventing flare-ups.",\n'
            + '                "startDate": "YYYY-MM-DD",\n'
            + '                "endDate": "YYYY-MM-DD",\n'
            + '                "task": [\n'
            + '                    {\n'
            + '                        "title": "Topical Pain Relief Cream",\n'
            + '                        "description": "Apply over-the-counter pain relief cream as needed for localized discomfort.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + '                    }\n'
            + '                ]\n'
            + '            },\n'
            + '            {\n'
            + '                "name": "Week-4",\n'
            + '                "description": "Long-term pain prevention and self-management.",\n'
            + '                "startDate": "YYYY-MM-DD",\n'
            + '                "endDate": "YYYY-MM-DD",\n'
            + '                "task": [\n'
            + '                    {\n'
            + '                        "title": "Mind-Body Relaxation",\n'
            + '                        "description": "Practice meditation or deep breathing to manage pain perception, 10 minutes daily.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + '                    }\n'
            + '                ]\n'
            + '            }\n'
            + '        ]\n'
            + '        // ... and so on for all other relevant categories, each with 4 distinct weeks ...\n'
            + '    }\n'
            + '}\n'
            + "```\n",
        })
    messages.append(user_message_block)
    return messages
