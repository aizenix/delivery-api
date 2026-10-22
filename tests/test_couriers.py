import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.errors import Conflict
from app.models import Order, Role
from app.services.couriers import accept_order, couriers_near
from app.services.zones import make_point


@pytest.fixture
async def paid_order(make_order, customer) -> Order:
    return await make_order(customer, paid=True)


async def test_available_orders_nearest_first(client, courier, customer, auth, make_order):
    far = await make_order(customer, lat=41.34, lng=69.33, paid=True)
    near = await make_order(customer, lat=41.315, lng=69.285, paid=True)
    await make_order(customer)  # unpaid, must not be offered

    response = await client.put(
        "/courier/location", json={"lat": 41.3111, "lng": 69.2797}, headers=auth(courier)
    )
    assert response.status_code == 204

    response = await client.get("/courier/orders/available", headers=auth(courier))
    orders = response.json()
    assert [o["id"] for o in orders] == [near.id, far.id]
    assert orders[0]["distance_m"] < 1000 < orders[1]["distance_m"]


async def test_customer_cannot_use_courier_api(client, customer, auth):
    response = await client.get("/courier/orders/available", headers=auth(customer))
    assert response.status_code == 403


async def test_taken_order_cannot_be_accepted_again(client, make_user, auth, paid_order):
    first, second = await make_user(Role.courier), await make_user(Role.courier)

    response = await client.post(f"/courier/orders/{paid_order.id}/accept", headers=auth(first))
    assert response.status_code == 200
    assert response.json()["status"] == "assigned"
    assert response.json()["courier_id"] == first.id

    response = await client.post(f"/courier/orders/{paid_order.id}/accept", headers=auth(second))
    assert response.status_code == 409


async def test_concurrent_accept_has_one_winner(client, make_user, auth, paid_order):
    couriers = [await make_user(Role.courier) for _ in range(5)]

    responses = await asyncio.gather(
        *(client.post(f"/courier/orders/{paid_order.id}/accept", headers=auth(c)) for c in couriers)
    )
    codes = sorted(r.status_code for r in responses)
    assert codes == [200, 409, 409, 409, 409]


async def test_locked_order_is_skipped_without_waiting(courier, paid_order):
    async with SessionLocal() as other:
        # another courier's transaction is in the middle of accepting this order
        await other.execute(select(Order).where(Order.id == paid_order.id).with_for_update())

        async with SessionLocal() as session:
            with pytest.raises(Conflict):
                await asyncio.wait_for(accept_order(session, courier, paid_order.id), timeout=5)

        await other.rollback()

    async with SessionLocal() as session:
        order = await accept_order(session, courier, paid_order.id)
    assert order.courier_id == courier.id


async def test_courier_delivers_order(client, make_user, auth, paid_order):
    courier, stranger = await make_user(Role.courier), await make_user(Role.courier)
    url = f"/courier/orders/{paid_order.id}"
    await client.post(f"{url}/accept", headers=auth(courier))

    response = await client.post(
        f"{url}/status", json={"status": "delivered"}, headers=auth(courier)
    )
    assert response.status_code == 409

    response = await client.post(
        f"{url}/status", json={"status": "picked_up"}, headers=auth(stranger)
    )
    assert response.status_code == 404

    for status in ("picked_up", "delivered"):
        response = await client.post(
            f"{url}/status", json={"status": status}, headers=auth(courier)
        )
        assert response.status_code == 200
        assert response.json()["status"] == status

    response = await client.get("/courier/orders", headers=auth(courier))
    assert response.json() == []


async def test_only_nearby_online_couriers_are_notified(session, make_user, make_order, customer):
    now = datetime.now(UTC)
    nearby = await make_user(
        Role.courier,
        telegram_chat_id=1,
        location=make_point(41.32, 69.28),
        location_updated_at=now,
    )
    await make_user(  # in Chilonzor, ~7 km away
        Role.courier,
        telegram_chat_id=2,
        location=make_point(41.2756, 69.2034),
        location_updated_at=now,
    )
    await make_user(  # close, but went quiet an hour ago
        Role.courier,
        telegram_chat_id=3,
        location=make_point(41.312, 69.28),
        location_updated_at=now - timedelta(hours=1),
    )
    order = await make_order(customer, paid=True)

    couriers = await couriers_near(session, order)
    assert [c.id for c in couriers] == [nearby.id]
