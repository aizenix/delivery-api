import io

from sqlalchemy import func, select

from app.models import Category, Product
from app.services.catalog import import_catalog

CSV = """sku,name,category,price,available
MLK-001,Milk 3.2% 1L,Dairy,13500,1
BRD-010,Non,Bakery,"4 000,50",yes
VEG-101,Cucumbers 1kg,Vegetables,n/a,1
,No sku,Dairy,1000,1
MLK-001,Milk 3.2% 1L,Dairy,13900,1
"""


async def test_import_creates_products(session):
    report = await import_catalog(session, io.StringIO(CSV))

    assert (report.created, report.updated) == (2, 0)
    assert [e.line for e in report.errors] == [4, 5]
    prices = dict((await session.execute(select(Product.sku, Product.price))).all())
    # repeated SKU: the last row wins; prices are stored in tiyin
    assert prices == {"MLK-001": 1_390_000, "BRD-010": 400_050}


async def test_reimport_updates_by_sku(session):
    await import_catalog(session, io.StringIO(CSV))
    update_csv = (
        "sku,name,category,price,available\n"
        "MLK-001,Milk 3.2% 1L,Dairy,14500,0\n"
        "AYR-001,Ayran 0.5L,Dairy,7000,1\n"
    )
    report = await import_catalog(session, io.StringIO(update_csv))
    assert (report.created, report.updated) == (1, 1)

    milk = await session.scalar(select(Product).where(Product.sku == "MLK-001"))
    assert milk.price == 1_450_000
    assert milk.is_available is False
    assert await session.scalar(select(func.count()).select_from(Category)) == 2


async def test_import_endpoint_is_admin_only(client, customer, admin, auth):
    files = {"file": ("catalog.csv", CSV.encode("utf-8-sig"), "text/csv")}

    response = await client.post("/catalog/import", files=files, headers=auth(customer))
    assert response.status_code == 403

    response = await client.post("/catalog/import", files=files, headers=auth(admin))
    assert response.status_code == 200
    assert response.json()["created"] == 2

    response = await client.get("/products")
    assert {p["sku"] for p in response.json()} == {"MLK-001", "BRD-010"}
