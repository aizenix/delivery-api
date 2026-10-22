from app.models import OrderStatus


def order_payload(products, lines, lat=41.3111, lng=69.2797) -> dict:
    return {
        "items": [{"product_id": products[i].id, "quantity": qty} for i, qty in lines],
        "lat": lat,
        "lng": lng,
        "address": "Amir Temur 1, apt 5",
    }


async def test_total_is_items_plus_delivery_fee(client, customer, auth, zone, products):
    payload = order_payload(products, [(0, 2), (1, 1), (0, 1)])
    response = await client.post("/orders", json=payload, headers=auth(customer))
    assert response.status_code == 201

    order = response.json()
    # duplicate lines for the same product are merged
    assert {(i["product_id"], i["quantity"]) for i in order["items"]} == {
        (products[0].id, 3),
        (products[1].id, 1),
    }
    assert order["items_total"] == 3 * 2_000_000 + 3_500_000
    assert order["delivery_fee"] == zone.delivery_fee
    assert order["total"] == order["items_total"] + zone.delivery_fee
    assert order["status"] == "created"
    assert (order["lat"], order["lng"]) == (41.3111, 69.2797)


async def test_minimum_order_amount(client, customer, auth, zone, products):
    payload = order_payload(products, [(0, 2)])
    response = await client.post("/orders", json=payload, headers=auth(customer))
    assert response.status_code == 422
    assert "minimum" in response.json()["detail"]


async def test_address_outside_zones(client, customer, auth, zone, products):
    payload = order_payload(products, [(1, 2)], lat=39.6542, lng=66.9597)
    response = await client.post("/orders", json=payload, headers=auth(customer))
    assert response.status_code == 422


async def test_unavailable_product(client, customer, auth, zone, products):
    payload = order_payload(products, [(1, 2), (2, 1)])
    response = await client.post("/orders", json=payload, headers=auth(customer))
    assert response.status_code == 422
    assert str(products[2].id) in response.json()["detail"]


async def test_customer_sees_only_own_orders(client, make_user, auth, make_order):
    alice, bob = await make_user(), await make_user()
    alice_order = await make_order(alice)
    bob_order = await make_order(bob)

    response = await client.get("/orders", headers=auth(alice))
    assert [o["id"] for o in response.json()] == [alice_order.id]

    response = await client.get(f"/orders/{bob_order.id}", headers=auth(alice))
    assert response.status_code == 404


async def test_customer_cancels_only_unpaid_orders(client, customer, auth, make_order):
    unpaid = await make_order(customer)
    paid = await make_order(customer, paid=True)

    response = await client.post(f"/orders/{unpaid.id}/cancel", headers=auth(customer))
    assert response.status_code == 200
    assert response.json()["status"] == OrderStatus.cancelled

    response = await client.post(f"/orders/{paid.id}/cancel", headers=auth(customer))
    assert response.status_code == 409
