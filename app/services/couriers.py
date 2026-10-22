from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.errors import Conflict, NotFound
from app.models import Order, OrderStatus, Role, User
from app.services.orders import change_status
from app.services.zones import make_point

# a courier who hasn't sent a location for this long is treated as offline
LOCATION_FRESHNESS = timedelta(minutes=30)


async def update_location(session: AsyncSession, courier: User, lat: float, lng: float) -> None:
    courier.location = make_point(lat, lng)
    courier.location_updated_at = datetime.now(UTC)
    await session.commit()


async def available_orders(
    session: AsyncSession, courier: User, limit: int = 20
) -> list[tuple[Order, float | None]]:
    stmt = select(Order).where(Order.status == OrderStatus.paid, Order.courier_id.is_(None))
    if courier.location is None:
        orders = await session.scalars(stmt.order_by(Order.paid_at).limit(limit))
        return [(order, None) for order in orders]

    distance = func.ST_DistanceSphere(Order.delivery_point, courier.location).label("distance")
    rows = await session.execute(stmt.add_columns(distance).order_by(distance).limit(limit))
    return [(order, meters) for order, meters in rows]


async def accept_order(session: AsyncSession, courier: User, order_id: int) -> Order:
    # SKIP LOCKED: when another courier is accepting this order right now we don't wait
    # for their transaction, the row is simply not found and this courier gets a 409
    order = await session.scalar(
        select(Order)
        .where(
            Order.id == order_id,
            Order.status == OrderStatus.paid,
            Order.courier_id.is_(None),
        )
        .with_for_update(skip_locked=True)
    )
    if order is None:
        raise Conflict("order is no longer available")

    order.courier_id = courier.id
    change_status(order, OrderStatus.assigned)
    await session.commit()
    return order


async def active_orders(session: AsyncSession, courier: User) -> list[Order]:
    orders = await session.scalars(
        select(Order)
        .where(
            Order.courier_id == courier.id,
            Order.status.in_([OrderStatus.assigned, OrderStatus.picked_up]),
        )
        .order_by(Order.assigned_at)
    )
    return list(orders)


async def set_status(
    session: AsyncSession, courier: User, order_id: int, status: OrderStatus
) -> Order:
    order = await session.scalar(
        select(Order).where(Order.id == order_id, Order.courier_id == courier.id).with_for_update()
    )
    if order is None:
        raise NotFound("order not found")
    change_status(order, status)
    await session.commit()
    return order


async def couriers_near(session: AsyncSession, order: Order) -> list[User]:
    since = datetime.now(UTC) - LOCATION_FRESHNESS
    distance = func.ST_DistanceSphere(User.location, order.delivery_point)
    stmt = select(User).where(
        User.role == Role.courier,
        User.is_active,
        User.telegram_chat_id.is_not(None),
        User.location_updated_at >= since,
        distance <= settings.courier_notify_radius_m,
    )
    return list(await session.scalars(stmt))
