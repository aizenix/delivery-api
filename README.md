# delivery-api

Order and delivery backend for a local business: customers order from a catalog and pay online, couriers pick orders up and deliver them. It follows the structure of a delivery service I built in Tashkent, without the client-specific parts.

Stack: Python 3.12+, FastAPI, SQLAlchemy 2 (async, asyncpg), Alembic, PostgreSQL 16 + PostGIS, Redis, Celery + beat, SQLAdmin, pytest, ruff.

## Run with Docker

```bash
cp .env.example .env
docker compose up --build
```

- API docs: http://localhost:8000/docs
- Admin: http://localhost:8000/admin (`ADMIN_USERNAME` / `ADMIN_PASSWORD` from `.env`)

Migrations run when the api container starts. With `SMS_BACKEND=console` login codes are printed to the worker log (`docker compose logs -f worker`). Every new phone number signs up as a customer; roles (courier, admin) are changed in the admin.

Load the sample catalog:

```bash
docker compose exec api python -m app.cli import-catalog samples/catalog.csv
```

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
docker compose up -d db redis

alembic upgrade head
uvicorn app.main:app --reload
celery -A app.tasks worker -l info   # separate terminal, add --pool=solo on Windows
celery -A app.tasks beat -l info     # separate terminal
```

## Tests

Tests run against a real PostGIS database, Redis is replaced with fakeredis. The run drops and recreates the database from `TEST_DATABASE_URL` (default `postgresql+asyncpg://postgres:postgres@localhost:5432/delivery_test`), so don't point it at anything you care about.

```bash
docker compose up -d db
pytest
ruff check . && ruff format --check .
```

## Main flow

1. `POST /auth/otp/request`, `POST /auth/otp/verify` - phone login, returns access and refresh tokens
2. `GET /zones/check?lat=&lng=` - is the address served, delivery fee, minimum order
3. `POST /orders` - order from cart items and a map point
4. `POST /payments` - returns the provider checkout URL; the provider then calls `POST /payments/webhook`
5. `GET /courier/orders/available` - paid orders, nearest first
6. `POST /courier/orders/{id}/accept`, then `POST /courier/orders/{id}/status` with `picked_up` / `delivered`

Unpaid orders are cancelled by a beat task after `UNPAID_ORDER_MINUTES`. `GET /healthz` checks the database and Redis.

## Structure

```
app/
  api/          routers: parse input, call a service, return a schema
  services/     orders, payments, couriers, zones, auth, catalog import
  models/       SQLAlchemy models
  schemas/      Pydantic request and response models
  tasks.py      Celery app, tasks, beat schedule
  admin.py      SQLAdmin views behind basic auth
  sms.py        console and HTTP SMS backends
  cli.py        catalog import command
migrations/     Alembic
tests/
```

## Notes

- Accepting an order uses `SELECT ... FOR UPDATE SKIP LOCKED`. When two couriers accept the same order at once, the second one doesn't wait for the first transaction to finish: the row is skipped and they get a 409 immediately. The auto-cancel job skips locked rows as well, so it leaves alone any order that a payment webhook is holding at that moment.
- The payment webhook is signed with `X-Signature: hex(HMAC-SHA256(secret, body))`. The signature is checked against the raw request bytes before the JSON is parsed, using `hmac.compare_digest` on bytes (it raises on non-ASCII `str`, and a junk header should be a 401, not a 500).
- Webhooks are idempotent: the payment row is locked and the provider transaction id is stored under a unique constraint. A repeated delivery gets 200 with `"duplicate"` and changes nothing. The amount must match the order total or the webhook gets a 422 and the order stays unpaid. A successful payment for an order that was already cancelled is recorded and logged for a refund instead of reviving the order.
- Zone lookup uses `ST_Covers` rather than `ST_Contains`, so an address lying exactly on a zone border is still served. Where zones overlap, the cheaper delivery fee wins. Zone polygons have a GiST index.
- Money is stored as integer tiyin (1/100 sum). Supplier CSVs list prices in sum, sometimes as `"12 500,50"`, so the importer parses them with `Decimal` and upserts by SKU with `INSERT ... ON CONFLICT`.

## License

MIT
