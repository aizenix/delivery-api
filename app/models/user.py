import enum
from datetime import datetime

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import BigInteger, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Role(enum.StrEnum):
    customer = "customer"
    courier = "courier"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str | None] = mapped_column(String(100))
    role: Mapped[Role] = mapped_column(
        Enum(Role, native_enum=False, length=20), default=Role.customer
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    # last known courier position, used to sort available orders by distance
    location: Mapped[WKBElement | None] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False)
    )
    location_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __str__(self) -> str:
        return self.phone
