from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import OrderStatus


class OrderItemIn(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=100)


class OrderCreate(BaseModel):
    items: list[OrderItemIn] = Field(min_length=1, max_length=50)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    address: str = Field(min_length=3, max_length=255)
    comment: str | None = Field(default=None, max_length=500)


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int | None
    name: str
    price: int
    quantity: int


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: OrderStatus
    zone_id: int
    courier_id: int | None
    address: str
    comment: str | None
    lat: float
    lng: float
    items: list[OrderItemOut]
    items_total: int
    delivery_fee: int
    total: int
    created_at: datetime
    paid_at: datetime | None
    assigned_at: datetime | None
    picked_up_at: datetime | None
    delivered_at: datetime | None
    cancelled_at: datetime | None
