from geoalchemy2 import Geometry, WKBElement
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DeliveryZone(Base):
    __tablename__ = "delivery_zones"
    __table_args__ = (Index("ix_delivery_zones_area", "area", postgresql_using="gist"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    area: Mapped[WKBElement] = mapped_column(Geometry("POLYGON", srid=4326, spatial_index=False))
    delivery_fee: Mapped[int]
    min_order_amount: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)

    @property
    def geojson(self) -> dict:
        return mapping(to_shape(self.area))

    def __str__(self) -> str:
        return self.name
