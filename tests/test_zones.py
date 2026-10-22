from sqlalchemy import update

from app.models import DeliveryZone

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[69.0, 41.0], [69.1, 41.0], [69.1, 41.1], [69.0, 41.1], [69.0, 41.0]]],
}


async def test_point_inside_zone(client, zone):
    response = await client.get("/zones/check", params={"lat": 41.3111, "lng": 69.2797})
    assert response.status_code == 200
    assert response.json()["id"] == zone.id
    assert response.json()["delivery_fee"] == zone.delivery_fee


async def test_point_outside_zone(client, zone):
    # Samarkand
    response = await client.get("/zones/check", params={"lat": 39.6542, "lng": 66.9597})
    assert response.status_code == 422


async def test_point_on_border_is_inside(client, zone):
    response = await client.get("/zones/check", params={"lat": 41.30, "lng": 69.20})
    assert response.status_code == 200


async def test_inactive_zone_is_ignored(client, session, zone):
    await session.execute(update(DeliveryZone).values(is_active=False))
    await session.commit()

    response = await client.get("/zones/check", params={"lat": 41.3111, "lng": 69.2797})
    assert response.status_code == 422


async def test_admin_creates_zone(client, admin, auth):
    payload = {"name": "Test", "area": SQUARE, "delivery_fee": 800_000, "min_order_amount": 0}
    response = await client.post("/zones", json=payload, headers=auth(admin))
    assert response.status_code == 201
    assert response.json()["area"]["type"] == "Polygon"

    check = await client.get("/zones/check", params={"lat": 41.05, "lng": 69.05})
    assert check.json()["id"] == response.json()["id"]


async def test_zone_validation_and_permissions(client, customer, admin, auth):
    payload = {"name": "Test", "area": SQUARE, "delivery_fee": 800_000}
    response = await client.post("/zones", json=payload, headers=auth(customer))
    assert response.status_code == 403

    bow_tie = {
        "type": "Polygon",
        "coordinates": [[[69.0, 41.0], [69.1, 41.1], [69.1, 41.0], [69.0, 41.1], [69.0, 41.0]]],
    }
    response = await client.post("/zones", json={**payload, "area": bow_tie}, headers=auth(admin))
    assert response.status_code == 422
