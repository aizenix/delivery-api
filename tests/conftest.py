import asyncio
import itertools
import os
from pathlib import Path

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/delivery_test"
)
os.environ["JWT_SECRET"] = "test-jwt-secret-that-is-long-enough"
os.environ["PAYMENT_SECRET"] = "test-payment-secret"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "secret"
os.environ["SMS_BACKEND"] = "console"
os.environ["TELEGRAM_BOT_TOKEN"] = ""

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from fakeredis import FakeAsyncRedis
from geoalchemy2 import WKTElement
from httpx import ASGITransport, AsyncClient
from sqlalchemy import make_url, text

from app import tasks
from app.db import Base, SessionLocal, engine, get_redis
from app.main import app
from app.models import DeliveryZone, Order, OrderStatus, Product, Role, User
from app.schemas.orders import OrderCreate, OrderItemIn
from app.services.auth import create_tokens
from app.services.orders import change_status, create_order

ROOT = Path(__file__).resolve().parent.parent

# roughly central Tashkent
ZONE_POLYGON = "POLYGON((69.20 41.25, 69.35 41.25, 69.35 41.36, 69.20 41.36, 69.20 41.25))"
CENTER = (41.3111, 69.2797)


async def _recreate_database(url: str) -> None:
    db_url = make_url(url)
    conn = await asyncpg.connect(
        user=db_url.username,
        password=db_url.password,
        host=db_url.host,
        port=db_url.port,
        database="postgres",
    )
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{db_url.database}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{db_url.database}"')
    finally:
        await conn.close()


def pytest_sessionstart(session):
    # runs before pytest-asyncio starts its loop, so asyncio.run here and in env.py is fine
    asyncio.run(_recreate_database(os.environ["DATABASE_URL"]))
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")


@pytest.fixture(autouse=True)
async def clean_db():
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def queued(monkeypatch) -> dict[str, list[tuple]]:
    """Record celery .delay() calls instead of sending them to a broker."""
    calls: dict[str, list[tuple]] = {"send_sms": [], "notify_couriers": []}
    monkeypatch.setattr(tasks.send_sms, "delay", lambda *a: calls["send_sms"].append(a))
    monkeypatch.setattr(
        tasks.notify_couriers, "delay", lambda *a: calls["notify_couriers"].append(a)
    )
    return calls


@pytest.fixture
async def session():
    async with SessionLocal() as session:
        yield session


@pytest.fixture
async def redis():
    fake = FakeAsyncRedis(decode_responses=True)
    yield fake
    await fake.flushall()
    await fake.aclose()


@pytest.fixture
async def client(redis):
    app.dependency_overrides[get_redis] = lambda: redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


_phone_numbers = itertools.count(1000000)


@pytest.fixture
def make_user(session):
    async def make(role: Role = Role.customer, **fields) -> User:
        user = User(phone=f"+99890{next(_phone_numbers)}", role=role, **fields)
        session.add(user)
        await session.commit()
        return user

    return make


@pytest.fixture
async def customer(make_user) -> User:
    return await make_user()


@pytest.fixture
async def courier(make_user) -> User:
    return await make_user(Role.courier)


@pytest.fixture
async def admin(make_user) -> User:
    return await make_user(Role.admin)


@pytest.fixture
def auth():
    def headers(user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_tokens(user.id).access_token}"}

    return headers


@pytest.fixture
async def zone(session) -> DeliveryZone:
    zone = DeliveryZone(
        name="Tashkent center",
        area=WKTElement(ZONE_POLYGON, srid=4326),
        delivery_fee=1_000_000,
        min_order_amount=5_000_000,
    )
    session.add(zone)
    await session.commit()
    return zone


@pytest.fixture
async def products(session) -> list[Product]:
    items = [
        Product(sku="MLK-001", name="Milk 1L", price=2_000_000),
        Product(sku="BRD-010", name="Non", price=3_500_000),
        Product(sku="VEG-101", name="Cucumbers 1kg", price=1_500_000, is_available=False),
    ]
    session.add_all(items)
    await session.commit()
    return items


@pytest.fixture
def make_order(session, zone, products):
    async def make(
        customer: User, lat: float = CENTER[0], lng: float = CENTER[1], paid: bool = False
    ) -> Order:
        data = OrderCreate(
            items=[OrderItemIn(product_id=products[0].id, quantity=3)],
            lat=lat,
            lng=lng,
            address="Amir Temur 1",
        )
        order = await create_order(session, customer, data)
        if paid:
            change_status(order, OrderStatus.paid)
            await session.commit()
        return order

    return make
