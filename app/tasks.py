import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

import httpx
from celery import Celery
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import telegram
from app.config import settings
from app.models import Order, OrderStatus
from app.services.couriers import couriers_near
from app.services.orders import cancel_expired_orders
from app.sms import get_sms_client

logger = logging.getLogger(__name__)

celery_app = Celery("delivery", broker=settings.celery_broker_url)
celery_app.conf.update(
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    beat_schedule={
        "cancel-unpaid-orders": {"task": "app.tasks.cancel_unpaid_orders", "schedule": 60.0},
    },
)


@asynccontextmanager
async def task_session() -> AsyncIterator[AsyncSession]:
    # each asyncio.run() gets a new event loop and asyncpg connections can't be shared
    # between loops, so tasks use a throwaway engine instead of the app's pool
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            yield session
    finally:
        await engine.dispose()


@celery_app.task(autoretry_for=(httpx.HTTPError,), retry_backoff=True, max_retries=3)
def send_sms(phone: str, text: str) -> None:
    get_sms_client().send(phone, text)


async def _order_and_courier_chats(order_id: int) -> tuple[Order | None, list[int]]:
    async with task_session() as session:
        order = await session.get(Order, order_id)
        if order is None or order.status != OrderStatus.paid:
            return None, []
        couriers = await couriers_near(session, order)
        return order, [c.telegram_chat_id for c in couriers]


@celery_app.task
def notify_couriers(order_id: int) -> None:
    order, chat_ids = asyncio.run(_order_and_courier_chats(order_id))
    if order is None:
        return

    text = f"New order #{order.id}\n{order.address}\nTotal: {order.total // 100} sum"
    for chat_id in chat_ids:
        try:
            telegram.send_message(chat_id, text)
        except httpx.HTTPError:
            logger.exception("failed to notify courier chat %s about order %s", chat_id, order.id)


async def _cancel_unpaid() -> list[int]:
    async with task_session() as session:
        return await cancel_expired_orders(
            session, timedelta(minutes=settings.unpaid_order_minutes)
        )


@celery_app.task
def cancel_unpaid_orders() -> None:
    cancelled = asyncio.run(_cancel_unpaid())
    if cancelled:
        logger.info("cancelled unpaid orders: %s", cancelled)
