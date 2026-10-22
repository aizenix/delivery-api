from pydantic import BaseModel, ConfigDict


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    category_id: int | None
    price: int


class RowError(BaseModel):
    line: int
    error: str


class ImportReport(BaseModel):
    created: int = 0
    updated: int = 0
    errors: list[RowError] = []
