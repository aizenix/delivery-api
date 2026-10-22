from geoalchemy2 import WKTElement
from geoalchemy2.shape import from_shape
from shapely.geometry import shape
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import Unprocessable
from app.models import DeliveryZone
from app.schemas.zones import ZoneCreate


def make_point(lat: float, lng: float) -> WKTElement:
    # WKT is x/y, so longitude goes first
    return WKTElement(f"POINT({lng} {lat})", srid=4326)


async def find_zone(session: AsyncSession, lat: float, lng: float) -> DeliveryZone | None:
    # ST_Covers rather than ST_Contains: a point exactly on the border still counts.
    # Where zones overlap the customer gets the cheaper one.
    stmt = (
        select(DeliveryZone)
        .where(DeliveryZone.is_active, func.ST_Covers(DeliveryZone.area, make_point(lat, lng)))
        .order_by(DeliveryZone.delivery_fee)
        .limit(1)
    )
    return await session.scalar(stmt)


async def create_zone(session: AsyncSession, data: ZoneCreate) -> DeliveryZone:
    polygon = shape(data.area.model_dump())
    if not polygon.is_valid:
        raise Unprocessable("polygon is not valid, check for self-intersections")

    zone = DeliveryZone(
        name=data.name,
        area=from_shape(polygon, srid=4326),
        delivery_fee=data.delivery_fee,
        min_order_amount=data.min_order_amount,
    )
    session.add(zone)
    await session.commit()
    return zone
