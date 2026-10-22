import json
from datetime import timedelta

import httpx
from sqlalchemy import func, update

from app.models import Order, OrderStatus
from app.services.orders import cancel_expired_orders
from app.sms import HttpSMS


async def test_cancel_expired_orders(session, customer, make_order):
    stale = await make_order(customer)
    fresh = await make_order(customer)
    stale_paid = await make_order(customer, paid=True)
    await session.execute(
        update(Order)
        .where(Order.id.in_([stale.id, stale_paid.id]))
        .values(created_at=func.now() - timedelta(hours=1))
    )
    await session.commit()

    cancelled = await cancel_expired_orders(session, timedelta(minutes=15))
    assert cancelled == [stale.id]

    for order, expected in [
        (stale, OrderStatus.cancelled),
        (fresh, OrderStatus.created),
        (stale_paid, OrderStatus.paid),
    ]:
        await session.refresh(order)
        assert order.status == expected


def test_http_sms_request():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"status": "queued"})

    sms = HttpSMS(
        "https://sms.example.com/send",
        token="gateway-token",
        sender="Delivery",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    sms.send("+998901234567", "Delivery code: 123456")

    (request,) = requests
    assert request.headers["Authorization"] == "Bearer gateway-token"
    assert json.loads(request.content) == {
        "phone": "998901234567",
        "text": "Delivery code: 123456",
        "sender": "Delivery",
    }
