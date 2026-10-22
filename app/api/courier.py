from fastapi import APIRouter, Response

from app.api.deps import CourierUser, SessionDep
from app.schemas.couriers import AvailableOrderOut, CourierStatusUpdate, LocationIn
from app.schemas.orders import OrderOut
from app.services import couriers

router = APIRouter(prefix="/courier", tags=["courier"])


@router.put("/location", status_code=204)
async def update_location(data: LocationIn, courier: CourierUser, session: SessionDep) -> Response:
    await couriers.update_location(session, courier, data.lat, data.lng)
    return Response(status_code=204)


@router.get("/orders/available")
async def available_orders(courier: CourierUser, session: SessionDep) -> list[AvailableOrderOut]:
    result = []
    for order, distance in await couriers.available_orders(session, courier):
        item = AvailableOrderOut.model_validate(order)
        item.distance_m = round(distance) if distance is not None else None
        result.append(item)
    return result


@router.get("/orders")
async def my_orders(courier: CourierUser, session: SessionDep) -> list[OrderOut]:
    return [OrderOut.model_validate(o) for o in await couriers.active_orders(session, courier)]


@router.post("/orders/{order_id}/accept")
async def accept_order(order_id: int, courier: CourierUser, session: SessionDep) -> OrderOut:
    order = await couriers.accept_order(session, courier, order_id)
    return OrderOut.model_validate(order)


@router.post("/orders/{order_id}/status")
async def update_status(
    order_id: int, data: CourierStatusUpdate, courier: CourierUser, session: SessionDep
) -> OrderOut:
    order = await couriers.set_status(session, courier, order_id, data.status)
    return OrderOut.model_validate(order)
