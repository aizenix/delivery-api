import enum
from datetime import datetime

from geoalchemy2 import Geometry, WKBElement
from geoalchemy2.shape import to_shape
from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class OrderStatus(enum.StrEnum):
    created = "created"
    paid = "paid"
    assigned = "assigned"
    picked_up = "picked_up"
    delivered = "delivered"
    cancelled = "cancelled"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    courier_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    zone_id: Mapped[int] = mapped_column(ForeignKey("delivery_zones.id"))
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, native_enum=False, length=20), default=OrderStatus.created, index=True
    )
    address: Mapped[str] = mapped_column(String(255))
    comment: Mapped[str | None] = mapped_column(String(500))
    delivery_point: Mapped[WKBElement] = mapped_column(
        Geometry("POINT", srid=4326, spatial_index=False)
    )
    items_total: Mapped[int]
    delivery_fee: Mapped[int]
    total: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def lat(self) -> float:
        return to_shape(self.delivery_point).y

    @property
    def lng(self) -> float:
        return to_shape(self.delivery_point).x

    def __str__(self) -> str:
        return f"#{self.id}"


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"))
    # name and price are copied so old orders don't change when the catalog does
    name: Mapped[str] = mapped_column(String(255))
    price: Mapped[int]
    quantity: Mapped[int]

    order: Mapped[Order] = relationship(back_populates="items")
