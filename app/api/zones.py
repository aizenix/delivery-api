from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import AdminUser, SessionDep
from app.errors import Unprocessable
from app.models import DeliveryZone
from app.schemas.zones import ZoneCreate, ZoneOut, ZoneWithArea
from app.services.zones import create_zone, find_zone

router = APIRouter(prefix="/zones", tags=["zones"])


@router.get("")
async def list_zones(session: SessionDep) -> list[ZoneWithArea]:
    zones = await session.scalars(
        select(DeliveryZone).where(DeliveryZone.is_active).order_by(DeliveryZone.id)
    )
    return [ZoneWithArea.model_validate(z) for z in zones]


@router.get("/check", responses={422: {"description": "Address is outside delivery zones"}})
async def check_zone(
    session: SessionDep,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lng: Annotated[float, Query(ge=-180, le=180)],
) -> ZoneOut:
    zone = await find_zone(session, lat, lng)
    if zone is None:
        raise Unprocessable("address is outside delivery zones")
    return ZoneOut.model_validate(zone)


@router.post("", status_code=201)
async def add_zone(data: ZoneCreate, session: SessionDep, _: AdminUser) -> ZoneWithArea:
    zone = await create_zone(session, data)
    return ZoneWithArea.model_validate(zone)
