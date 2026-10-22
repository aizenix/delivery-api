import io
from typing import Annotated

from fastapi import APIRouter, Query, UploadFile
from sqlalchemy import select

from app.api.deps import AdminUser, SessionDep
from app.errors import Unprocessable
from app.models import Category, Product
from app.schemas.catalog import CategoryOut, ImportReport, ProductOut
from app.services.catalog import import_catalog

router = APIRouter(tags=["catalog"])


@router.get("/categories")
async def list_categories(session: SessionDep) -> list[CategoryOut]:
    categories = await session.scalars(select(Category).order_by(Category.name))
    return [CategoryOut.model_validate(c) for c in categories]


@router.get("/products")
async def list_products(
    session: SessionDep,
    category_id: int | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ProductOut]:
    stmt = select(Product).where(Product.is_available)
    if category_id is not None:
        stmt = stmt.where(Product.category_id == category_id)
    if q:
        stmt = stmt.where(Product.name.icontains(q, autoescape=True))
    products = await session.scalars(stmt.order_by(Product.name).limit(limit).offset(offset))
    return [ProductOut.model_validate(p) for p in products]


@router.post("/catalog/import")
async def import_products(file: UploadFile, session: SessionDep, _: AdminUser) -> ImportReport:
    try:
        # utf-8-sig strips the BOM that Excel puts in front of exported CSVs
        content = (await file.read()).decode("utf-8-sig")
    except UnicodeDecodeError:
        raise Unprocessable("file must be a UTF-8 encoded CSV") from None
    return await import_catalog(session, io.StringIO(content, newline=""))
