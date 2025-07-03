from fastapi import APIRouter, Depends
from app.api.dependency import get_current_user, get_current_admin
from app.models.user import User
from app.models.feedback import FeedBack
from app.schemas.feedback import FeedBackIn, FeedBackOut, ContactUsIn, ContactUsOut

router = APIRouter(prefix="/v1/feedback", tags=["Feedback & Contact Us"])


@router.post("/create")
async def feedback_create(form: FeedBackIn, user: User = Depends(get_current_user)):
    await FeedBack.create(
        full_name=user.full_name,
        email=user.email,
        **form.model_dump(exclude_unset=True),
    )
    return {"message": "Feedback Sent Sucessfully"}


@router.get(
    "/all", dependencies=[Depends(get_current_admin)], response_model=list[FeedBackOut]
)
async def feedback_all(offset: int = 0, limit: int = 10):
    return await FeedBack.filter(is_contact_us=False).limit(limit).offset(offset)


@router.post("/contact-us/create")
async def contact_us_create(form: ContactUsIn):
    await FeedBack.create(is_contact_us=True, **form.model_dump(exclude_unset=True))
    return {"message": "Feedback Sent Sucessfully"}


@router.get(
    "/contact-us/all",
    dependencies=[Depends(get_current_admin)],
    response_model=list[ContactUsOut],
)
async def contact_us_all(offset: int = 0, limit: int = 10):
    return await FeedBack.filter(is_contact_us=True).limit(limit).offset(offset)
