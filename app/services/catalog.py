import csv
from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from itertools import batched

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import Unprocessable
from app.models import Category, Product
from app.schemas.catalog import ImportReport, RowError

REQUIRED_COLUMNS = {"sku", "name", "category", "price"}
FALSE_VALUES = {"0", "false", "no", "n"}
BATCH_SIZE = 500


def parse_price(raw: str) -> int:
    """Supplier price in sum ("12500", "12 500,50") to tiyin."""
    value = Decimal(raw.replace(" ", "").replace(",", "."))
    if value < 0:
        raise ValueError("negative price")
    return int((value * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


async def import_catalog(session: AsyncSession, lines: Iterable[str]) -> ImportReport:
    reader = csv.DictReader(lines)
    missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
    if missing:
        raise Unprocessable(f"missing columns: {', '.join(sorted(missing))}")

    report = ImportReport()
    rows: dict[str, dict] = {}
    for line_no, row in enumerate(reader, start=2):
        sku = (row["sku"] or "").strip()
        name = (row["name"] or "").strip()
        if not sku or not name:
            report.errors.append(RowError(line=line_no, error="sku and name are required"))
            continue
        try:
            price = parse_price(row["price"] or "")
        except (InvalidOperation, ValueError):
            report.errors.append(RowError(line=line_no, error=f"bad price {row['price']!r}"))
            continue
        # a SKU repeated in the file keeps its last row; ON CONFLICT DO UPDATE fails
        # if one statement touches the same row twice
        rows[sku] = {
            "sku": sku,
            "name": name,
            "price": price,
            "is_available": (row.get("available") or "1").strip().lower() not in FALSE_VALUES,
            "category": (row["category"] or "").strip(),
        }

    if not rows:
        return report

    category_ids = await _ensure_categories(session, {r["category"] for r in rows.values()})
    existing = set(await session.scalars(select(Product.sku).where(Product.sku.in_(list(rows)))))

    for row in rows.values():
        row["category_id"] = category_ids.get(row.pop("category"))

    for chunk in batched(rows.values(), BATCH_SIZE):
        stmt = insert(Product).values(list(chunk))
        stmt = stmt.on_conflict_do_update(
            index_elements=[Product.sku],
            set_={
                "name": stmt.excluded.name,
                "price": stmt.excluded.price,
                "is_available": stmt.excluded.is_available,
                "category_id": stmt.excluded.category_id,
                "updated_at": func.now(),
            },
        )
        await session.execute(stmt)
    await session.commit()

    report.created = len(rows.keys() - existing)
    report.updated = len(existing)
    return report


async def _ensure_categories(session: AsyncSession, names: set[str]) -> dict[str, int]:
    names.discard("")
    if not names:
        return {}
    await session.execute(
        insert(Category)
        .values([{"name": name} for name in names])
        .on_conflict_do_nothing(index_elements=[Category.name])
    )
    result = await session.execute(
        select(Category.name, Category.id).where(Category.name.in_(names))
    )
    return dict(result.all())
