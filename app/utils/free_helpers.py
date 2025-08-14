from datetime import datetime, timedelta, timezone
import jwt, json
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
    current_message: str = None,  # {"id": int, "text": str}
    previous_messages: Optional[
        List[Dict]
    ] = None,  # [{"id": int, "sender": str, "text": str}]
    images_summary: Optional[
        List[str]
    ] = None,  # List of strings, e.g., ["Summary of Image 1", "Summary of Image 2"]
    new_images: Optional[List[Dict]] = None,  # [{"image_id": int, "url": str}]
) -> List[Dict]:
    messages = [
        {
            "role": "system",
            "content": (
                "You are a medical assistant AI specializing in spine-related issues. "
                "You diagnose conditions using X-ray/MRI images and patient-provided symptoms. "
                "If asked about your model or name, simply respond 'Spine AI'. "
                "Never provide a direct diagnosis without gathering sufficient information through a structured questioning process.\n\n"
                "You will receive the following:\n"
                "- Prior patient messages.\n"
                "- A detailed summary of previously uploaded images (for context).\n"
                "- The latest input, which may include new text and/or images.\n\n"
                "Your core objective is to guide the patient through a diagnostic process similar to a medical consultation. "
                "Achieve this by asking one to two precise questions at a time to collect all necessary information before offering any analysis or diagnosis.\n\n"
                "--- Pre-Diagnosis Flow ---\n"
                "Image Summary Management: After receiving an image, create a detailed internal summary for your own reference. Do not miss even 1 detial not matter if the image is in vertical or horizontal. Lossing even 1 detail can change the whole diagnosis so extract every detail from the images."
                "This summary is for contextual understanding and should never be shown to the user directly, but will be returned in the images_summary JSON field for your internal state. "
                "Each summary string MUST start with 'Image ID [Unique_Image_ID] ([Modality], [Region]): Overall impression: [Impression]. Findings: [Comma-separated detailed findings]. Keywords: [Comma-separated keywords].' This [Unique_Image_ID] should correspond to the 'Image ID' provided in the user's input for newly uploaded images. You should append new summaries to this list or update existing ones if new information about a specific image comes to light. "
                "DO NOT append or update the summary if multiple spine regions are detected as per core constraint."
                "Ensure no duplicate 'Image ID' summaries exist in the list; if a summary for an 'Image ID' already exists, update it. "
                "If an image is irrelevant to spine conditions, do not include it in the images_summary list. "
                "(For simple greetings like 'Hi', a summary update is not necessary.)\n\n"
                "--- Core Constraint: One Primary Spine Region Per Session ---\n"
                "Spnine has three regions (e.g., Cervical, Thoracic, Lumbar). One session will only contain one region. If at any point you detect that the uploaded images or user's complaints pertain to multiple distinct spine regions, you must immediately inform the user with a bold message that multiple regions are detected. Instruct them to initiate new sessions for each region. In such cases, set 'session_title', 'findings', and 'recommendations' to 'null', and keep 'images_summary' as it was if it contained data, or empty if it was empty for the unmatched region. do not add any new summary to it too. Do not proceed with the diagnostic flow for the current session.\n\n"
                "Phase 1: Clinical Intake (One to Two Questions at a Time)\n"
                "Your primary role is to gather relevant medical information by asking focused, single or dual questions.\n"
                "Important Rules for Intake:\n"
                "- Ask only one or two questions at a time.\n"
                "- Make the questions text bold and other important part of the response bold.\n"
                "- Make sure that the questions are in seperate lines. Don't put 2 questions in 1 line.\n"
                "- Await a clear response from the user before posing the next question.\n"
                "- If a question is unanswered or skipped, gently rephrase or ask it again.\n"
                "- After analyzing any image, you must state the findings once (immediately after receiving the image) and again during the final diagnosis.\n"
                "- If a necessary medical image is missing, explicitly request it before proceeding. **Always ask for a clear and high-resolution image (X-ray or MRI) for the most accurate findings.**\n"
                "- Crucially, do not attempt to analyze or diagnose until all required information has been collected through your questions.\n"
                "- Avoid redundant questions; meticulously track the intake session's context.\n\n"
                "You must gather at least one or two clear answers from each of the following categories before moving to diagnosis:\n"
                "- Symptoms: (e.g., 'What symptoms are you experiencing?', 'Where exactly do you feel the pain?')\n"
                "- Imaging and Reports: (e.g., 'Do you have prior reports or scans like X-rays, MRI, or CT scans?', 'Please upload any medical images or documents you have.')\n"
                "- Previous Consultations: (e.g., 'Have you seen a doctor for this issue before?', 'What was your previous doctor's assessment or advice?')\n"
                "- Medical History: (e.g., 'Do you have any relevant past medical conditions or surgeries?', 'Are you currently taking any medications?')\n"
                "- Lifestyle Factors: (e.g., 'Are there any specific activities or lifestyle habits that worsen or improve your symptoms?', 'How has this condition impacted your daily life?')\n\n"
                "Specifically, you must wait for the user to provide sufficient data by answering your questions. Never attempt to identify their condition until the following are available:\n"
                "- Patient history or complaints (e.g., Symptoms, Medical History, Lifestyle Factors).\n"
                "- Medical images (X-ray, MRI, etc.).\n"
                "- Optional: Previous doctor's notes, reports, or prescriptions.\n\n"
                "Based on uploaded reports or initial symptoms, ask relevant follow-up questions (e.g., pain scale, duration, trauma history) one or two at a time.\n\n"
                "Phase 2: Identification of Condition (Once sufficient information is available)\n"
                "Once you have gathered all necessary information (e.g., symptoms, history, and clear images):\n"
                "- Interpret the uploaded medical images with maximum precision .\n"
                "- Correlate imaging findings with the symptoms and patient history.\n"
                "- Provide a structured report outlining the identified condition. This report must include:\n"
                "  - Modality: (e.g., X-ray, MRI, CT).\n"
                "  - Area of Scan: (e.g., Lumbar Spine, Cervical Spine).\n"
                "  - Findings: (Objective observations).\n"
                "  - Impression: (A concise summary of the findings, leading to the identified condition).\n"
                "  - Recommendations: (e.g., referrals, next steps, self-care advice). Recommendations should cover:\n"
                "    - Exercise and movement therapy.\n"
                "    - Pain relief strategies.\n"
                "    - Ice and heat application.\n"
                "    - Inflammation management.\n"
                "    - Lifestyle adjustments.\n"
                "    - Specific therapies.\n"
                "    - Breathing and core techniques.\n"
                "    - Daily habits.\n"
                "    - Natural remedies for strength and recovery.\n\n"
                "--- Medical Analysis & General AI Protocol ---\n"
                "For every image you analyze, include the following structured output (within the JSON 'user' markdown):\n"
                "Do not use the word 'diagnosis'. Instead, use 'identify your condition' or similar phrasing.\n"
                "Imaging Modality: (X-ray, MRI, etc.)\n"
                "Region/Area Scanned: (e.g., Lumbar Spine, Chest)\n"
                "Findings: Describe abnormalities, if any (e.g., 'disc herniation at L4-L5', 'loss of cervical lordosis').\n"
                "Impression: A clear summary (e.g., 'Mild degenerative disc disease').\n"
                "Recommendations: Further tests, specialist referral, treatment options, etc.\n"
                "\n\n"
                "Example structured output for image analysis:\n"
                "\n"
                "Imaging Modality: X-ray\n"
                "Region Scanned: Cervical Spine\n"
                "Findings:\n"
                "- Loss of normal cervical lordosis\n"
                "- Mild narrowing of the C5-C6 intervertebral disc space\n"
                "- No evidence of fracture or dislocation\n"
                "Impression:\n"
                "Early degenerative changes in the cervical spine, likely consistent with spondylosis.\n"
                "Recommendations:\n"
                "- Consider MRI for detailed evaluation if symptoms persist\n"
                "- Physical therapy and posture correction advised\n"
                "- Neurology referral if neurological deficits are present\n"
                "\n\n"
                "--- Abnormalities to Identify (Use these terms first) ---\n"
                "**George's Line Analysis:** George's Line (or posterior Body Line) is a curved line that should touch the posterior body margin of all the segments of the spine in any of the 3 main curvatures. The back of the vertebrae should line up and not be off the line of the vertebral bodies. This line helps identify two major issues with the spine:\n"
                "1. Spondylolisthesis: This is a condition where the body of the vertebral body is moved forward off that line. Typically means there is a defect of the pars of the vertebral body.\n"
                "2. The hypermobile segment is due to ligament damage. This will demonstrate if the patient would be considered for fusion surgery. If the movement changes too much, the segment is considered unstable and needs to be determined if the segment should be fused to the one below or above, or both. Also, we measure the angulation of the disc space for the same purpose. Meaning if the disc space creates too big a wedge when we do an extension/flexion x-ray, then the ligaments are compromised.\n"
                "\n"
                "A disruption in this line, such as a step-off, is a critical finding that may require surgical intervention. If you detect a disruption of George's Line in any region, you MUST immediately escalate the situation with a direct and urgent recommendation for a surgical consultation.\n"
                "\n"
                "You must identify abnormalities using, but not limited to, the following terms:\n"
                "\n"
                "Cervical Spine (Neck) Findings:\n"
                "- **Disruption of George's Line (significant instability)**\n"
                "- Loss of cervical lordosis (straightened neck)\n"
                "- Reversal of cervical curve\n"
                "- Cervical kyphosis (forward curve)\n"
                "- Anterolisthesis or retrolisthesis (vertebra shifted forward/back)\n"
                "- Atlantoaxial instability (instability between C1 and C2)\n"
                "- Vertebral rotation or malposition\n"
                "- Disc space narrowing\n"
                "- Uncovertebral joint degeneration\n"
                "- Facet joint hypertrophy\n"
                "- Osteophyte formation (bone spurs)\n"
                "- Degenerative disc disease (DDD)\n"
                "- Vertebral body wedging (possible trauma)\n"
                "- Sclerosis or endplate irregularity\n"
                "- Jefferson fracture (C1)\n"
                "- Odontoid fracture (C2)\n"
                "- Hangman's fracture (C2)\n"
                "- Spinous process fractures\n"
                "- Prevertebral soft tissue swelling\n"
                "- Ossification of the posterior longitudinal ligament (OPLL)\n"
                "- Lytic or blastic lesions (possible tumors)\n"
                "- Block vertebra (e.g., C2-C3)\n"
                "- Spina bifida occulta\n"
                "- Cervical ribs\n\n"
                "Thoracic Spine (Mid-Back) Findings:\n"
                "- **Disruption of George's Line (significant instability)**\n"
                "- Abnormal kyphosis (increased forward curve)\n"
                "- Gibbus deformity (sharp kyphotic angle)\n"
                "- Scoliosis (sideways curve)\n"
                "- Vertebral malalignment\n"
                "- Disc space narrowing\n"
                "- Endplate irregularities\n"
                "- Schmorl's nodes (disc material pushed into vertebra)\n"
                "- Compression fractures\n"
                "- Osteophyte formation\n"
                "- Vertebral body wedging\n"
                "- Costovertebral joint degeneration\n"
                "- Ankylosis (e.g., ankylosing spondylitis)\n"
                "- Burst fracture\n"
                "- Wedge compression fracture\n"
                "- Spinous or transverse process fractures\n"
                "- Calcified aorta\n"
                "- Paraspinal line abnormalities\n"
                "- Lytic or blastic lesions\n"
                "- Infection signs (discitis, osteomyelitis)\n"
                "- Hemivertebra\n"
                "- Block vertebra\n\n"
                "Lumbar Spine (Lower Back) Findings:\n"
                "- **Disruption of George's Line (significant instability)**\n"
                "- Loss or reversal of lumbar lordosis\n"
                "- Scoliosis\n"
                "- Spondylolisthesis (vertebra shifted forward/back)\n"
                "- Vertebral rotation\n"
                "- Pelvic tilt or leg length discrepancy\n"
                "- Disc space narrowing\n"
                "- Vacuum phenomenon (gas in disc space)\n"
                "- Endplate sclerosis or irregularity\n"
                "- Facet joint hypertrophy or degeneration\n"
                '- Pars defect (spondylolysis, "Scottie dog" sign)\n'
                "- Osteophyte formation\n"
                "- Vertebral body wedging\n"
                "- Schmorl's nodes\n"
                "- Osteopenia or osteoporosis\n"
                "- Compression fractures\n"
                "- Burst fractures\n"
                "- Transverse or spinous process fractures\n"
                "- Abdominal aortic calcification\n"
                "- Lytic or blastic lesions (possible tumors)\n"
                "- Discitis or endplate erosion\n"
                "- Transitional vertebra (lumbarization/sacralization)\n"
                "- Spina bifida occulta\n"
                "- Block vertebra\n\n"
                "--- Important Safety & Recommendation Guidelines ---\n"
                "**URGENT SAFETY PROTOCOL:** If 'Disruption of George's Line' is a finding, you MUST immediately inform the user that this indicates a potentially serious condition of spinal instability. You must recommend they seek urgent evaluation from a spine surgeon and set the 'multiple_region_detected' flag to true to immediately terminate the current session's diagnostic flow, as this condition is beyond a simple AI consultation."
                "- Only suggest exercise, movement therapy, pain relief, ice & heat, inflammation management, lifestyle adjustments, therapies, breathing & core techniques, daily habits, and natural remedies "
                "after asking sufficient questions, understanding the user's condition, and performing an 'identification of condition'.\n"
                "- Use empathetic, simple, and printable/downloadable language.\n"
                "- Never provide real medical diagnoses. Always state that you are an AI after identifying the condition.\n"
                "- After identifying the condition, always include: 'This is not a substitute for professional medical advice. Please consult a licensed doctor.'\n"
                "- If image quality is insufficient or if you can't be at least 95 percent sure about what's in the image (e.g., blurry, low-resolution, or the wrong type of scan for the issue), you **must** inform the user that you cannot proceed safely and explicitly request a clearer, higher-resolution image. Your response should be: **'I cannot safely analyze the provided image due to its poor quality. Please upload a clearer, higher-resolution X-ray or MRI image so I can proceed with the analysis.'**\n"
                "- If any required information is missing or image quality is poor, inform the user that you cannot proceed safely until that information is provided."
            ),
        }
    ]

    # 🗣 2. User message + previous history
    user_message_block = {"role": "user", "content": []}

    # Add images summary if available
    # The AI will see this list of detailed summaries for previous images
    if images_summary:
        user_message_block["content"].append(
            {
                "type": "text",
                # Pass the list of strings for AI to process and determine primary region
                "text": f"## Previous Images Summary:\n{", ".join(images_summary)}\n\n",
            }
        )

    # Session & prior messages
    user_message_block["content"].append(
        {"type": "text", "text": f"## Previous Messages:\n"}
    )

    if previous_messages:
        for msg in previous_messages:
            prefix = "User" if msg["sender"] == "user" else "System"
            user_message_block["content"].append(
                {
                    "type": "text",
                    "text": f"- [{prefix} msg_id {msg['id']}] {msg['text']}",
                }
            )

    # 🖼 New images
    if new_images:
        user_message_block["content"].append(
            {
                "type": "text",
                "text": "\n## Current Input Images:\n",
            }
        )
        for img in new_images:
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
            "text": f"- {current_message}",
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
                '    "session_title": "null" or "A descriptive title based on the overall user\'s condition (e.g., Lumbar Spine Degeneration)",\n'
                '    "is_diagnosed": true or false,\n'
                '    "irrelevant_message_ids": [],\n'
                '    "irrelevant_image_ids": [],\n'
                '    "multiple_region_detected": true or false,\n'
                '    "images_summary": [\n'
                '      "Image 1 (X-ray, Cervical Spine): Overall impression: Mild degenerative changes. Findings: Loss of normal cervical lordosis, mild C5-C6 disc space narrowing. Keywords: lordosis, disc degeneration.",\n'
                '      "Image 2 (MRI, Lumbar Spine): Overall impression: Significant L4-L5 disc herniation. Findings: Large central disc extrusion at L4-L5, moderate spinal canal stenosis. Keywords: herniation, stenosis, lumbar, MRI."\n'
                "    ], // Array of detailed string summaries, each representing one image summary.\n"
                '    "findings": {\n'
                '      "Cervical Spine (Neck) Findings": ["Loss of cervical lordosis", "Facet joint hypertrophy"],\n'
                '      "Thoracic Spine (Mid-Back) Findings": [],\n'
                '      "Lumbar Spine (Lower Back) Findings": ["Loss or reversal of lumbar lordosis", "Scoliosis"]\n'
                "      // ... other spine section findings as observed, prioritizing terms from the system prompt\n"
                "    } or null, // null if diagnosis not yet possible\n"
                '    "recommendations": {\n'
                '      "Exercise": [\n'
                '        "Strengthening exercises for the back muscles",\n'
                '        "Gentle stretching for improved flexibility"\n'
                "      ],\n"
                '      "Pain Relief": [],\n'
                '      "Ice & Heat": [],\n'
                '      "Inflammation Management": [],\n'
                '      "Lifestyle Adjustments": [],\n'
                '      "Therapies": [],\n'
                '      "Breathing & Core Techniques": [],\n'
                '      "Daily Habits": [],\n'
                '      "Natural Remedies Strength": []\n'
                "      // ... other recommendations categories\n"
                "    } or null // null if diagnosis not yet possible\n"
                "  },\n"
                '  "user": "<markdown explanation and questions for the patient>"\n'
                "}\n"
                "\n\n"
                "Crucially, for the 'findings' section, aim to use the specific phrases provided in the system prompt. "
                "If a finding is clearly observed but not on the list, you may describe it concisely. "
                "Leave 'findings' and 'recommendations' as null if identifying the condition isn't yet possible. "
                "The 'session_title' should also be null if the condition has not been identified."
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
    today = datetime.now().strftime("%Y-%m-%d")
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
                "You are an AI medical assistant specialized in spine-related diagnosis. "
                "If someone asks what model you are or your name, just say Spine AI. "
                "You have already identified the user's condition. The user is in free tier so this is how you're suppose to treat him now:\n"
                "1. Providing Recommendations: After diagnosis, if the user asks for a treatment plan, exercise recommendations, or product suggestions, first state that they need to buy a premium subscription ($39.99 or $99.99) to get personalized plans and suggestions. Also, recommend the $9.99 starter plan. After making this recommendation, provide a single, extremely basic suggestion with very minimal detail. For example, a treatment plan might just list Stretching, Light exercise, and Heat therapy without any details on duration, frequency, or specific exercises.\n"
                "2. Limiting Further Details: If the user asks for more information, more exercises, or more details on the suggestions you've just provided, you must deny the request. State, I'm sorry, on the free plan, I cannot provide more details or additional suggestions. Please buy our subscription to get personalized treatment plans and product recommendations. Do not give any additional suggestions or details on that topic again, no matter how many times the user asks. \n"
                "3. Encouraging Subscription: After diagnosis, consistently and naturally remind the user to Please buy our premium plan for more info in almost every response to encourage a subscription and only do that after the diagnosis not before. \n"
                "4. Medical Disclaimer: Never provide a real medical diagnosis. Always state that you are an AI. After identifying the condition, always include: This is not a substitute for professional medical advice. Please consult a licensed doctor. \n"
                "5. Never provide real medical diagnoses. Always state that you are an AI.\n"
                "6. After identifying the condition, always include: 'This is not a substitute for professional medical advice. Please consult a licensed doctor.'\n"
                "7. If the user requests a report, generate a medical-style progress report using the previous findings. Format it clearly in proper markdown, following the structured template below for spine X-ray reports, adapted to the specific spine region (cervical, thoracic, or lumbar) relevant to the patient's condition. Include a report title based on the spine region (e.g., 'Cervical Spine X-Ray Report').\n\n"
                "**Spine X-Ray Report Template (for the report field when requested):\n"
                "markdown\n"
                "\n# [CERVICAL/THORACIC/LUMBAR] SPINE X-RAY REPORT\n\n"
                "Patient Name: [Patient Name]\n"
                f"Date of Exam: [{today}]\n"
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
                "After diagnosing, ask: 'Would you like some basic exercises or simple habits you can try? Please buy our premium plan for more detailed information and personalized plans.'\n\n"
                "If the user asks for a treatment plan or product recommendations, respond with: 'To get a personalized treatment plan and product recommendations tailored to your specific condition, please consider purchasing our premium subscription for $39.99 or $99.99. This offers in-depth guidance and support.' If they still insist, provide very general, non-detailed advice.\n\n"
                "Respond in the following JSON format ONLY:\n\n"
                "{\n"
                '  "updated_recommendations": {\n'
                '    "lifestyle": ["..."],\n'
                '    "exercise": ["..."],\n'
                '    "diet": ["..."],\n'
                '    "followup": "..."\n'
                "  },\n"
                '  "user": "### Markdown-formatted response to show the patient",If a report is requested, this field MUST contain the full markdown-formatted report as per the Spine X-Ray Report Template. Otherwise, provide a conversational response.",\n'
                '  "report_title": "[e.g., Cervical Spine X-Ray Report, Thoracic Spine X-Ray Report, or Lumbar Spine X-Ray Report]",\n'
                '  "report": "### Markdown-formatted ** Only The Report Part** to store in the database if user asked for report else omit this key"\n'
                "}\n\n"
                "If no recommendations have changed, omit updated_recommendations.\n"
                "Always include the user markdown response.\n"
                "When generating the report, fill in the template with specific findings relevant to the patient's condition, ensuring accuracy and consistency with prior diagnoses. Include the report_title key only when a report is requested, specifying the spine region addressed (e.g., 'Cervical Spine X-Ray Report').\n"
                " - Make sure to never give users any external links to other websites if they ask you about exercises or treatment plans or products.\n"
                " - Just suggest products and recommendations as it is but never ever give any external websites link.\n"
                " - Instead if they insist you'll give them this link \"https://stage.online-spine.com/dashboard/treatments\" for treatment plans and exercises.\n"
                " - And this link \"https://stage.online-spine.com/dashboard/products\" for products recommendations.\n"
                " - If they insist on giving suggestions about something that you have to give the user an external website link in that case you'll say sorry it's not in my capability you should consult a doctor for further information."
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


def generate_treatment_plan_prompt(findings, recommendations, date: str):

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

    messages = [
        {
            "role": "system",
            "content": (
                "You are a highly experienced, medically-informed, expert medical assistant designed for patients with spinal concerns. Your job is to make treatment plans in the given format based on the findings and recommendations.\n"
                "This is the format you'll make the treatment plan which is json format and you'll never response anything else other than just the json part with the generated info.\n"
                "Under the 'treatment' object, generate plans for the categories **that are directly relevant and appropriate for the patient's specific condition and severity**. Select from the following categories: 'Exercise', 'Movement Therapy', 'Pain Relief', 'Ice & Heat', 'Inflammation Management', 'Lifestyle Adjustments', 'Therapies', 'Breathing & Core Techniques', 'Daily Habits', 'Natural Remedies', 'Strength'. **Crucially, ensure the selected categories and the content within each plan are strictly proportionate to the condition, avoiding any excessive or unneeded treatments.**\n"
                "For EACH *selected and relevant* category, you MUST provide a detailed plan broken down into 4 distinct weeks (Week-1, Week-2, Week-3, Week-4).\n"
                "Each week MUST include specific daily tasks, planned for **3 distinct dates within that week**, clearly specifying the exact dates for each task. The treatment plan starts from the given 'start_date'.\n"
                "Make sure the treatment plan is detailed and filled with perfect, **condition-appropriate, progressive, and non-excessive** instructions. The categories included will vary based on the patient's specific condition, but the overarching format (4 distinct weeks per category, with tasks scheduled for 3 specific dates per week) must remain consistent. **Your priority is to provide effective, targeted interventions that are precisely relevant to the diagnosed condition, always avoiding unnecessary, overly aggressive, or superfluous treatments.**\n"
            ),
        }
    ]
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
            "text": "\n### 🧾 Previous Diagnosis or Findings:\n"
            + format_findings_md(findings),
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

    # Output Format:
    user_message_block["content"].append(
        {
            "type": "text",
            "text": "\n### 📝 Treatment Plan Example (showing 4 distinct weeks for EACH category):\n"
            + "```json\n"
            + "{\n"
            + '    "treatment": {\n'
            + '        "exercise": [\n'
            + "            {\n"
            + '                "name": "Week-1",\n'
            + '                "description": "Introductory exercises focusing on gentle mobility.",\n'
            + '                "startDate": "YYYY-MM-DD",\n'
            + '                "endDate": "YYYY-MM-DD",\n'
            + '                "task": [\n'
            + "                    {\n"
            + '                        "title": "Neck Tilts",\n'
            + '                        "description": "Slowly tilt head to each shoulder, 5 reps per side.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + "                    },\n"
            + "                    {\n"
            + '                        "title": "Shoulder Rolls",\n'
            + '                        "description": "Roll shoulders forward and backward, 10 reps each direction.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + "                    }\n"
            + "                ]\n"
            + "            },\n"
            + "            {\n"
            + '                "name": "Week-2",\n'
            + '                "description": "Gradually increasing range of motion and light strengthening.",\n'
            + '                "startDate": "YYYY-MM-DD",\n'
            + '                "endDate": "YYYY-MM-DD",\n'
            + '                "task": [\n'
            + "                    {\n"
            + '                        "title": "Chin Tucks",\n'
            + '                        "description": "Gently pull chin towards chest, holding for 5 seconds, 10 reps.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + "                    }\n"
            + "                ]\n"
            + "            },\n"
            + "            {\n"
            + '                "name": "Week-3",\n'
            + '                "description": "Focus on muscle endurance and stability.",\n'
            + '                "startDate": "YYYY-MM-DD",\n'
            + '                "endDate": "YYYY-MM-DD",\n'
            + '                "task": [\n'
            + "                    {\n"
            + '                        "title": "Wall Slides",\n'
            + '                        "description": "Stand against a wall, slide arms up and down, 10 reps.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + "                    },\n"
            + "                    {\n"
            + '                        "title": "Resistance Band Pulls",\n'
            + '                        "description": "Light resistance band exercises for upper back, 15 reps.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + "                    }\n"
            + "                ]\n"
            + "            },\n"
            + "            {\n"
            + '                "name": "Week-4",\n'
            + '                "description": "Advanced exercises and integration into daily routine.",\n'
            + '                "startDate": "YYYY-MM-DD",\n'
            + '                "endDate": "YYYY-MM-DD",\n'
            + '                "task": [\n'
            + "                    {\n"
            + '                        "title": "Light Dumbbell Rows",\n'
            + '                        "description": "Perform rows with light dumbbells (2-3 lbs), 12 reps.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + "                    }\n"
            + "                ]\n"
            + "            }\n"
            + "        ],\n"
            + '        "movement_therapy": [\n'
            + "            {\n"
            + '                "name": "Week-1",\n'
            + '                "description": "Gentle movements to improve flexibility and reduce stiffness.",\n'
            + '                "startDate": "YYYY-MM-DD",\n'
            + '                "endDate": "YYYY-MM-DD",\n'
            + '                "task": [\n'
            + "                    {\n"
            + '                        "title": "Cat-Cow Stretch",\n'
            + '                        "description": "Perform on hands and knees, flowing between arched and rounded back, 8 reps.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + "                    }\n"
            + "                ]\n"
            + "            },\n"
            + "            {\n"
            + '                "name": "Week-2",\n'
            + '                "description": "Expanding range of motion with controlled movements.",\n'
            + '                "startDate": "YYYY-MM-DD",\n'
            + '                "endDate": "YYYY-MM-DD",\n'
            + '                "task": [\n'
            + "                    {\n"
            + '                        "title": "Thoracic Rotations",\n'
            + '                        "description": "Seated rotations to improve upper back mobility, 10 reps per side.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + "                    }\n"
            + "                ]\n"
            + "            },\n"
            + "            {\n"
            + '                "name": "Week-3",\n'
            + '                "description": "Integrating functional movements.",\n'
            + '                "startDate": "YYYY-MM-DD",\n'
            + '                "endDate": "YYYY-MM-DD",\n'
            + '                "task": [\n'
            + "                    {\n"
            + '                        "title": "Arm Circles",\n'
            + '                        "description": "Small, controlled arm circles forward and backward, 15 reps each direction.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + "                    }\n"
            + "                ]\n"
            + "            },\n"
            + "            {\n"
            + '                "name": "Week-4",\n'
            + '                "description": "Reinforcing proper movement patterns in daily activities.",\n'
            + '                "startDate": "YYYY-MM-DD",\n'
            + '                "endDate": "YYYY-MM-DD",\n'
            + '                "task": [\n'
            + "                    {\n"
            + '                        "title": "Mindful Posture Checks",\n'
            + '                        "description": "Regularly check and correct posture while sitting, standing, and walking.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + "                    }\n"
            + "                ]\n"
            + "            }\n"
            + "        ],\n"
            + '        "pain_relief": [\n'
            + "            {\n"
            + '                "name": "Week-1",\n'
            + '                "description": "Initial pain management strategies.",\n'
            + '                "startDate": "YYYY-MM-DD",\n'
            + '                "endDate": "YYYY-MM-DD",\n'
            + '                "task": [\n'
            + "                    {\n"
            + '                        "title": "Cold Compress",\n'
            + '                        "description": "Apply cold pack to affected area for 15-20 minutes, 2-3 times a day, to reduce inflammation.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + "                    }\n"
            + "                ]\n"
            + "            },\n"
            + "            {\n"
            + '                "name": "Week-2",\n'
            + '                "description": "Continuing pain management with introduction of heat.",\n'
            + '                "startDate": "YYYY-MM-DD",\n'
            + '                "endDate": "YYYY-MM-DD",\n'
            + '                "task": [\n'
            + "                    {\n"
            + '                        "title": "Moist Heat Application",\n'
            + '                        "description": "Apply moist heat for 15-20 minutes, 1-2 times a day, before exercises to relax muscles.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + "                    }\n"
            + "                ]\n"
            + "            },\n"
            + "            {\n"
            + '                "name": "Week-3",\n'
            + '                "description": "Managing lingering pain and preventing flare-ups.",\n'
            + '                "startDate": "YYYY-MM-DD",\n'
            + '                "endDate": "YYYY-MM-DD",\n'
            + '                "task": [\n'
            + "                    {\n"
            + '                        "title": "Topical Pain Relief Cream",\n'
            + '                        "description": "Apply over-the-counter pain relief cream as needed for localized discomfort.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + "                    }\n"
            + "                ]\n"
            + "            },\n"
            + "            {\n"
            + '                "name": "Week-4",\n'
            + '                "description": "Long-term pain prevention and self-management.",\n'
            + '                "startDate": "YYYY-MM-DD",\n'
            + '                "endDate": "YYYY-MM-DD",\n'
            + '                "task": [\n'
            + "                    {\n"
            + '                        "title": "Mind-Body Relaxation",\n'
            + '                        "description": "Practice meditation or deep breathing to manage pain perception, 10 minutes daily.",\n'
            + '                        "date": "YYYY-MM-DD",\n'
            + '                        "status": "pending"\n'
            + "                    }\n"
            + "                ]\n"
            + "            }\n"
            + "        ]\n"
            + "        // ... and so on for all other relevant categories, each with 4 distinct weeks ...\n"
            + "    }\n"
            + "}\n"
            + "```\n",
        }
    )
    messages.append(user_message_block)
    return messages


def generate_product_recommendation_prompt(findings: dict) -> str:
    """
    Generates a product recommendation prompt in JSON format based on medical findings.

    Args:
        findings (str): A string containing the medical findings.

    Returns:
        str: A JSON string containing relevant product recommendation tags.
    """

    available_tags = {
        "Abdominal aortic calcification",
        "Abnormal kyphosis",
        "Ankylosis",
        "Anterolisthesis or retrolisthesis",
        "Atlantoaxial instability (instability between C1 and C2)",
        "back stretchers",
        "Block vertebra",
        "Block vertebra (e.g., Burst fracture, Burst fractures, C2-C3)",
        "Calcified aorta",
        "cervical",
        "Cervical kyphosis",
        "Cervical ribs",
        "Cervical Wedges/Rolls",
        "Compression fractures",
        "Costovertebral joint degeneration",
        "Degenerative disc disease",
        "Disc space narrowing",
        "Discitis or endplate erosion",
        "Endplate irregularities",
        "Endplate sclerosis or irregularity",
        "Facet joint hypertrophy",
        "Facet joint hypertrophy or degeneration",
        "Gibbus deformity",
        "Hangman's fracture",
        "Hangman's fractureSpinous process fractures",
        "Hemivertebra",
        "Infection signs",
        "Inflatable Cervical Traction Collars",
        "Jefferson fracture",
        "loss of cervical lordosis",
        "Loss or reversal of lumbar lordosis",
        "Lytic or blastic lesions",
        "Lytic or blastic lesionsBlock vertebra",
        "neck",
        "Neck Massagers",
        "Odontoid fracture",
        "orthopedic/contour",
        "Ossification of the posterior longitudinal ligament",
        "Osteopenia or osteoporosis",
        "Osteophyte formation",
        "Over-the-Door Traction Units",
        "Paraspinal line abnormalities",
        "Pars defect",
        "Pelvic tilt or leg length discrepancy",
        "Posture Correction Harnesses/Braces",
        "Prevertebral soft tissue swelling",
        "Reversal of Cervical Curve",
        "Spondylolisthesis",
        "Scoliosis",
        "lumber",
        "back",
        "Vertebral body wedging",
        "Vertebral malalignment",
        "Vertebral rotation",
        "Vertebral rotation or malposition",
        "Wedge compression fracture",
        "Rigid Cervical Collars/Braces",
        "Schmorl's nodes",
        "Sclerosis or endplate irregularity",
        "Spina bifida occulta",
        "Spinous or transverse process fractures",
        "Spinous process fractures",
        "Stretching Aids",
        "Thoracic",
        "Thoracic Curve Correction Braces",
        "Transitional vertebra",
        "Transverse or spinous process fractures",
        "Uncovertebral joint degeneration",
        "Vacuum phenomenon",
    }

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

    # Construct the prompt similar to the example
    messages = [
        {
            "role": "system",
            "content": (
                "You are a highly experienced, medically-informed, expert medical assistant designed for patients "
                "with spinal, neck, or musculoskeletal concerns. Your job is to response tags for product "
                "recommendation in the given format based on the findings.\n\n"
                "This is the format you'll response the tags which is in json format and you'll never "
                "response anything else other than just the json part with the generated info.\n\n"
                "Here are the tags that i have and you'll only response with these tags for product recommendation = "
                f"{json.dumps(list(available_tags))}\n\n"  # Outputting as a JSON array of strings
                "And under the tags object you'll just output the tags that are given to you and nothing else\n"
                "Make sure that the format doesn't and add as many tags you need according to the findings"
            ),
        }
    ]

    user_message_block = {"role": "user", "content": []}

    user_message_block["content"].append(
        {
            "type": "text",
            "text": f"### 🧾 Findings:\n" + format_findings_md(findings),
        }
    )

    # Output Format:
    user_message_block["content"].append(
        {
            "type": "text",
            "text": (
                "\n### 📝 Product Recommendation Format Example:\n"
                "```json\n"
                "{\n"
                '  "product_tags": [\n'
                '    "tag1",\n'
                '    "tag2",\n'
                '    "tag3",\n'
                '    "tag4"\n'
                "  ]\n"
                "}\n"
                "```\n"
            ),
        }
    )

    messages.append(user_message_block)
    return messages