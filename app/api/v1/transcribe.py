from fastapi import APIRouter, Depends, HTTPException, UploadFile, status, File
from app.api.dependency import get_current_user
# from faster_whisper import WhisperModel  # Disabled because not supported on Python 3.13

router = APIRouter(prefix="/v1/helper", tags=["Helper Endpoints"])

# MODEL_SIZE = "tiny"
# model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")


@router.post("/transcribe", dependencies=[Depends(get_current_user)])
async def transcribe_audio(file: UploadFile = File(...)):
    try:
        # Temporarily disabled actual transcription since WhisperModel is unavailable
        # segments, info = model.transcribe(file.file, task="transcribe", language="en")
        # transcription_result = "".join(segment.text for segment in segments)

        # Instead, return a placeholder
        transcription_result = "[Transcription disabled: faster_whisper not installed]"
        return {"text": transcription_result}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
