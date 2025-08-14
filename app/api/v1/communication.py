from fastapi import APIRouter, Depends
from app.api.dependency import get_current_admin
from app.models.communication import Communication
from app.schemas.communication import CommunicationIn, CommunicationOut


router = APIRouter(prefix="/v1/support", tags=["Feedback & Contact Us"])


@router.post("/create")
async def feedback_create(form: CommunicationIn):
    await Communication.create(**form.model_dump(exclude_unset=True))
    return {"message": "Submitted Sucessfully"}


@router.get("/all", dependencies=[Depends(get_current_admin)], response_model=list[CommunicationOut])
async def feedback_all(offset: int = 0, limit: int = 10, is_contact_us:bool=False):
    return await Communication.filter(is_contact_us=is_contact_us).limit(limit).offset(offset)
