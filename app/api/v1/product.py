from fastapi import APIRouter, Depends, HTTPException, status
from app.api.dependency import get_current_admin
from app.models.product import Product, Tag
from app.schemas.product import ProductCreate, ProductOut, TagIn, TagOut
from app.models.chat import ChatSession

router = APIRouter(prefix="/v1/product", tags=["Product Endpoints"])


@router.post(
    "/create", response_model=ProductOut, status_code=status.HTTP_201_CREATED
)
async def create_product(product: ProductCreate, user=Depends(get_current_admin)):
    form_data = product.model_dump(exclude_unset=True)
    tags = form_data.pop("tags", None)
    prod =  await Product.create(**form_data)
    if tags:
        await prod.tags.add(* await Tag.filter(id__in=tags))
    await prod.refresh_from_db()
    return prod


@router.get("/all", response_model=list[ProductOut])
async def get_all_products(limit: int = 100, offset: int = 0, session_id:str = None):
    if session_id:
        session = await ChatSession.get_or_none(id=session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
            )
        tags = session.suggested_product_tags
        return await Product.filter(tags__name__in=tags).offset(offset).limit(limit).order_by("name").distinct()
    return await Product.all().offset(offset).limit(limit)


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: int):
    product = await Product.get_or_none(id=product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )
    return product


@router.put(
    "/{product_id}",
    response_model=ProductOut,
    dependencies=[Depends(get_current_admin)],
)
async def update_product(product_id: int, product: ProductCreate):
    existing_product = await Product.get_or_none(id=product_id)
    if not existing_product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )
    form_data = product.model_dump(exclude_unset=True)
    tags = form_data.pop("tags", None)
    await existing_product.update_from_dict(form_data).save()
    if tags is not None:
        await existing_product.tags.clear()
        await existing_product.tags.add(*await Tag.filter(id__in=tags))
    await existing_product.refresh_from_db()
    return existing_product


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_current_admin)],
)
async def delete_product(product_id: int):
    product = await Product.get_or_none(id=product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )
    await product.delete()
    return {"detail": "Product deleted successfully"}


@router.get("/tags/all", response_model=list[TagOut])
async def get_all_tags(limit: int = 100, offset: int = 0):
    tags = await Tag.all().offset(offset).limit(limit)
    return tags


@router.post("/tags/create", response_model=TagOut, status_code=status.HTTP_201_CREATED)
async def create_tag(tag: TagIn, user=Depends(get_current_admin)):
    tag_instance = await Tag.create(**tag.model_dump())
    return tag_instance


@router.put("/tags/{tag_id}", response_model=TagOut)
async def update_tag(tag_id: int, tag: TagIn):
    existing_tag = await Tag.get_or_none(id=tag_id)
    if not existing_tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found"
        )
    await existing_tag.update_from_dict(tag.model_dump()).save()
    await existing_tag.refresh_from_db()
    return existing_tag


@router.delete("/tags/{tag_id}")
async def delete_tag(tag_id: int):
    tag = await Tag.get_or_none(id=tag_id)
    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found"
        )
    await tag.delete()
    return {"detail": "Tag deleted successfully"}
