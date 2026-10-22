import hashlib
import hmac
import json

import pytest

from app.config import settings
from app.models import OrderStatus, Payment, PaymentStatus


def signed(event: dict, secret: str | None = None) -> tuple[bytes, dict]:
    body = json.dumps(event).encode()
    key = (secret or settings.payment_secret).encode()
    signature = hmac.new(key, body, hashlib.sha256).hexdigest()
    return body, {"X-Signature": signature, "Content-Type": "application/json"}


def event_for(payment: dict, **overrides) -> dict:
    event = {
        "transaction_id": "txn-1001",
        "merchant_ref": payment["payment_id"],
        "amount": payment["amount"],
        "status": "succeeded",
    }
    return event | overrides


@pytest.fixture
async def order(make_order, customer):
    return await make_order(customer)


@pytest.fixture
async def payment(client, customer, auth, order) -> dict:
    response = await client.post("/payments", json={"order_id": order.id}, headers=auth(customer))
    assert response.status_code == 201
    return response.json()


async def test_create_payment_returns_checkout_url(payment, order):
    assert payment["amount"] == order.total
    assert f"merchant_ref={payment['payment_id']}" in payment["checkout_url"]


async def test_webhook_marks_order_paid(client, session, payment, order, queued):
    body, headers = signed(event_for(payment))
    response = await client.post("/payments/webhook", content=body, headers=headers)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    await session.refresh(order)
    assert order.status == OrderStatus.paid
    assert order.paid_at is not None
    assert queued["notify_couriers"] == [(order.id,)]


async def test_webhook_rejects_bad_signature(client, session, payment, order, queued):
    body, headers = signed(event_for(payment), secret="not-the-secret")
    response = await client.post("/payments/webhook", content=body, headers=headers)
    assert response.status_code == 401

    _, headers = signed(event_for(payment))
    tampered = json.dumps(event_for(payment, amount=100)).encode()
    response = await client.post("/payments/webhook", content=tampered, headers=headers)
    assert response.status_code == 401

    # non-ASCII garbage in the header must be a 401, not a 500 from compare_digest
    response = await client.post(
        "/payments/webhook", content=tampered, headers={"X-Signature": b"zzz\xc3\xa9"}
    )
    assert response.status_code == 401

    await session.refresh(order)
    assert order.status == OrderStatus.created
    assert queued["notify_couriers"] == []


async def test_webhook_amount_mismatch(client, session, payment, order, queued):
    body, headers = signed(event_for(payment, amount=payment["amount"] - 100))
    response = await client.post("/payments/webhook", content=body, headers=headers)
    assert response.status_code == 422

    await session.refresh(order)
    assert order.status == OrderStatus.created
    db_payment = await session.get(Payment, payment["payment_id"])
    assert db_payment.status == PaymentStatus.pending
    assert queued["notify_couriers"] == []


async def test_repeated_webhook_is_applied_once(client, session, payment, order, queued):
    body, headers = signed(event_for(payment))
    first = await client.post("/payments/webhook", content=body, headers=headers)
    second = await client.post("/payments/webhook", content=body, headers=headers)

    assert first.json() == {"status": "ok"}
    assert second.status_code == 200
    assert second.json() == {"status": "duplicate"}
    assert len(queued["notify_couriers"]) == 1


async def test_failed_payment_leaves_order_unpaid(client, session, payment, order):
    body, headers = signed(event_for(payment, status="failed"))
    response = await client.post("/payments/webhook", content=body, headers=headers)
    assert response.json() == {"status": "failed"}

    await session.refresh(order)
    assert order.status == OrderStatus.created


async def test_payment_for_cancelled_order_is_flagged(
    client, session, customer, auth, payment, order, queued
):
    await client.post(f"/orders/{order.id}/cancel", headers=auth(customer))

    body, headers = signed(event_for(payment))
    response = await client.post("/payments/webhook", content=body, headers=headers)
    assert response.json() == {"status": "refund_required"}

    await session.refresh(order)
    assert order.status == OrderStatus.cancelled
    db_payment = await session.get(Payment, payment["payment_id"])
    assert db_payment.status == PaymentStatus.succeeded
    assert queued["notify_couriers"] == []
