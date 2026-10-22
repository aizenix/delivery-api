from typing import Literal

from pydantic import BaseModel, Field

from app.models import OrderStatus
from app.schemas.orders import OrderOut


class LocationIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class CourierStatusUpdate(BaseModel):
    status: Literal[OrderStatus.picked_up, OrderStatus.delivered]


class AvailableOrderOut(OrderOut):
    distance_m: int | None = None
