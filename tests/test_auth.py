import re

from app.config import settings

PHONE = "+998901234567"


async def request_code(client, queued, phone: str = PHONE) -> str:
    response = await client.post("/auth/otp/request", json={"phone": phone})
    assert response.status_code == 202
    _, text = queued["send_sms"][-1]
    return re.search(r"\d{6}", text).group()


async def login(client, queued) -> dict:
    code = await request_code(client, queued)
    response = await client.post("/auth/otp/verify", json={"phone": PHONE, "code": code})
    assert response.status_code == 200
    return response.json()


async def test_otp_login_creates_customer(client, queued):
    assert (await client.get("/users/me")).status_code == 401

    code = await request_code(client, queued, phone="998 90 123-45-67")
    assert queued["send_sms"][0][0] == PHONE

    response = await client.post("/auth/otp/verify", json={"phone": PHONE, "code": code})
    assert response.status_code == 200

    token = response.json()["access_token"]
    me = await client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["phone"] == PHONE
    assert me.json()["role"] == "customer"


async def test_bad_input_is_rejected(client, queued):
    response = await client.post("/auth/otp/request", json={"phone": "+7 999 123 45 67"})
    assert response.status_code == 422
    assert queued["send_sms"] == []

    await request_code(client, queued)
    # Arabic-Indic digits match \d; they must fail validation, compare_digest raises on them
    arabic_digits = "".join(chr(0x0661 + i) for i in range(6))
    response = await client.post("/auth/otp/verify", json={"phone": PHONE, "code": arabic_digits})
    assert response.status_code == 422


async def test_resend_is_rate_limited(client, queued):
    await request_code(client, queued)

    response = await client.post("/auth/otp/request", json={"phone": PHONE})
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0
    assert len(queued["send_sms"]) == 1


async def test_code_is_burned_after_too_many_attempts(client, queued):
    code = await request_code(client, queued)
    wrong = "000000" if code != "000000" else "111111"

    for _ in range(settings.otp_max_attempts):
        response = await client.post("/auth/otp/verify", json={"phone": PHONE, "code": wrong})
        assert response.status_code == 400

    # the right code no longer helps once the limit is hit
    response = await client.post("/auth/otp/verify", json={"phone": PHONE, "code": code})
    assert response.status_code == 429
    response = await client.post("/auth/otp/verify", json={"phone": PHONE, "code": code})
    assert response.status_code == 400


async def test_refresh_token_works_once(client, queued):
    tokens = await login(client, queued)

    response = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 200
    assert response.json()["refresh_token"] != tokens["refresh_token"]

    replay = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert replay.status_code == 401


async def test_access_token_is_not_accepted_as_refresh(client, queued):
    tokens = await login(client, queued)

    response = await client.post("/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert response.status_code == 401
