from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Order, Role, User

# a courier who hasn't sent a location for this long is treated as offline
LOCATION_FRESHNESS = timedelta(minutes=30)


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
