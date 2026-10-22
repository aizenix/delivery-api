import base64


async def test_healthz(client):
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"db": "ok", "redis": "ok"}


async def test_admin_requires_basic_auth(client):
    response = await client.get("/admin/")
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Basic")

    wrong = base64.b64encode(b"admin:wrong").decode()
    response = await client.get("/admin/", headers={"Authorization": f"Basic {wrong}"})
    assert response.status_code == 401

    good = base64.b64encode(b"admin:secret").decode()
    response = await client.get("/admin/order/list", headers={"Authorization": f"Basic {good}"})
    assert response.status_code == 200
