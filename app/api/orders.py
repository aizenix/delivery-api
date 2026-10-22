from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, SessionDep
from app.schemas.orders import OrderCreate, OrderOut
from app.services import orders

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", status_code=201)
async def create_order(data: OrderCreate, user: CurrentUser, session: SessionDep) -> OrderOut:
    order = await orders.create_order(session, user, data)
    return OrderOut.model_validate(order)


@router.get("")
async def list_orders(
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[OrderOut]:
    result = await orders.list_customer_orders(session, user, limit, offset)
    return [OrderOut.model_validate(o) for o in result]


@router.get("/{order_id}")
async def get_order(order_id: int, user: CurrentUser, session: SessionDep) -> OrderOut:
    order = await orders.get_customer_order(session, user, order_id)
    return OrderOut.model_validate(order)


@router.post("/{order_id}/cancel")
async def cancel_order(order_id: int, user: CurrentUser, session: SessionDep) -> OrderOut:
    order = await orders.cancel_order(session, user, order_id)
    return OrderOut.model_validate(order)
