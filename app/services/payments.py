import hashlib
import hmac
import logging
from datetime import UTC, datetime
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import tasks
from app.config import settings
from app.errors import Conflict, NotFound, Unprocessable
from app.models import Order, OrderStatus, Payment, PaymentStatus, User
from app.schemas.payments import WebhookEvent
from app.services.orders import change_status

logger = logging.getLogger(__name__)


def sign(body: bytes) -> str:
    return hmac.new(settings.payment_secret.encode(), body, hashlib.sha256).hexdigest()


def verify_signature(body: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    # compare bytes: compare_digest raises TypeError on non-ASCII str input
    return hmac.compare_digest(sign(body).encode(), signature.strip().lower().encode())


def checkout_url(payment: Payment) -> str:
    query = urlencode({"merchant_ref": payment.id, "amount": payment.amount})
    return f"{settings.payment_checkout_url}?{query}"


async def create_payment(session: AsyncSession, customer: User, order_id: int) -> Payment:
    order = await session.scalar(
        select(Order).where(Order.id == order_id, Order.customer_id == customer.id)
    )
    if order is None:
        raise NotFound("order not found")
    if order.status != OrderStatus.created:
        raise Conflict(f"order is already {order.status}")

    payment = Payment(order_id=order.id, amount=order.total, status=PaymentStatus.pending)
    session.add(payment)
    await session.commit()
    return payment


async def process_webhook(session: AsyncSession, event: WebhookEvent) -> str:
    payment = await session.scalar(
        select(Payment).where(Payment.id == event.merchant_ref).with_for_update()
    )
    if payment is None:
        raise NotFound("unknown payment")
    if payment.status != PaymentStatus.pending:
        # providers retry until they get a 2xx, so a repeat is acknowledged and changes nothing
        return "duplicate" if payment.provider_txn_id == event.transaction_id else "ignored"

    order = await session.scalar(
        select(Order).where(Order.id == payment.order_id).with_for_update()
    )
    if event.amount != order.total:
        logger.warning(
            "payment %s: amount %s does not match order %s total %s",
            payment.id,
            event.amount,
            order.id,
            order.total,
        )
        raise Unprocessable("amount does not match order total")

    payment.provider_txn_id = event.transaction_id
    payment.processed_at = datetime.now(UTC)
    if event.status == "failed":
        payment.status = PaymentStatus.failed
        await session.commit()
        return "failed"

    payment.status = PaymentStatus.succeeded
    if order.status != OrderStatus.created:
        # usually auto-cancelled while the customer was still on the checkout page
        logger.error(
            "payment %s succeeded for order %s in status %s, refund needed",
            payment.id,
            order.id,
            order.status,
        )
        await session.commit()
        return "refund_required"

    change_status(order, OrderStatus.paid)
    await session.commit()
    # queued after commit so the worker never sees the order before it is paid
    tasks.notify_couriers.delay(order.id)
    return "ok"
