from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import Conflict, NotFound, Unprocessable
from app.models import Order, OrderItem, OrderStatus, Product, Role, User
from app.schemas.orders import OrderCreate
from app.services.zones import find_zone, make_point

TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.created: frozenset({OrderStatus.paid, OrderStatus.cancelled}),
    OrderStatus.paid: frozenset({OrderStatus.assigned, OrderStatus.cancelled}),
    OrderStatus.assigned: frozenset({OrderStatus.picked_up, OrderStatus.cancelled}),
    OrderStatus.picked_up: frozenset({OrderStatus.delivered}),
    OrderStatus.delivered: frozenset(),
    OrderStatus.cancelled: frozenset(),
}


class InvalidTransition(Conflict):
    def __init__(self, current: OrderStatus, new: OrderStatus):
        super().__init__(f"order cannot go from {current} to {new}")


def change_status(order: Order, new: OrderStatus) -> None:
    """Every status change goes through here."""
    if new not in TRANSITIONS[order.status]:
        raise InvalidTransition(order.status, new)
    order.status = new
    setattr(order, f"{new}_at", datetime.now(UTC))


async def create_order(session: AsyncSession, customer: User, data: OrderCreate) -> Order:
    zone = await find_zone(session, data.lat, data.lng)
    if zone is None:
        raise Unprocessable("address is outside delivery zones")

    quantities: dict[int, int] = {}
    for item in data.items:
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity

    products = (
        await session.scalars(
            select(Product).where(Product.id.in_(list(quantities)), Product.is_available)
        )
    ).all()
    missing = quantities.keys() - {p.id for p in products}
    if missing:
        raise Unprocessable(f"products not available: {sorted(missing)}")

    items = [
        OrderItem(product_id=p.id, name=p.name, price=p.price, quantity=quantities[p.id])
        for p in products
    ]
    items_total = sum(item.price * item.quantity for item in items)
    if items_total < zone.min_order_amount:
        raise Unprocessable(
            f"minimum order amount for this zone is {zone.min_order_amount}, got {items_total}"
        )

    order = Order(
        customer_id=customer.id,
        zone_id=zone.id,
        status=OrderStatus.created,
        address=data.address,
        comment=data.comment,
        delivery_point=make_point(data.lat, data.lng),
        items=items,
        items_total=items_total,
        delivery_fee=zone.delivery_fee,
        total=items_total + zone.delivery_fee,
    )
    session.add(order)
    await session.commit()
    return order


async def list_customer_orders(
    session: AsyncSession, customer: User, limit: int, offset: int
) -> list[Order]:
    orders = await session.scalars(
        select(Order)
        .where(Order.customer_id == customer.id)
        .order_by(Order.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(orders)


async def get_customer_order(session: AsyncSession, customer: User, order_id: int) -> Order:
    order = await session.scalar(
        select(Order).where(Order.id == order_id, Order.customer_id == customer.id)
    )
    if order is None:
        raise NotFound("order not found")
    return order


async def cancel_order(session: AsyncSession, user: User, order_id: int) -> Order:
    stmt = select(Order).where(Order.id == order_id).with_for_update()
    if user.role != Role.admin:
        stmt = stmt.where(Order.customer_id == user.id)
    order = await session.scalar(stmt)
    if order is None:
        raise NotFound("order not found")
    if user.role != Role.admin and order.status != OrderStatus.created:
        raise Conflict("paid orders can only be cancelled by support")

    change_status(order, OrderStatus.cancelled)
    await session.commit()
    return order
