import base64
import binascii
import hmac

from fastapi import FastAPI
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings
from app.db import SessionLocal
from app.models import Category, DeliveryZone, Order, Payment, Product, User


def check_basic_auth(header: str | None) -> bool:
    scheme, _, encoded = (header or "").partition(" ")
    if scheme.lower() != "basic":
        return False
    try:
        username, _, password = base64.b64decode(encoded).decode().partition(":")
    except (binascii.Error, UnicodeDecodeError):
        return False
    username_ok = hmac.compare_digest(username.encode(), settings.admin_username.encode())
    password_ok = hmac.compare_digest(password.encode(), settings.admin_password.encode())
    return username_ok and password_ok


class BasicAuth(AuthenticationBackend):
    # sqladmin only knows session logins; returning a 401 from authenticate()
    # makes the browser show its own basic auth prompt instead of the login form
    async def authenticate(self, request: Request) -> Response | bool:
        if check_basic_auth(request.headers.get("Authorization")):
            return True
        return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="admin"'})

    async def login(self, request: Request) -> bool:
        return False

    async def logout(self, request: Request) -> bool:
        return True


class UserAdmin(ModelView, model=User):
    column_list = [User.id, User.phone, User.name, User.role, User.is_active, User.created_at]
    column_searchable_list = [User.phone]
    column_details_exclude_list = [User.location]
    form_excluded_columns = [User.location, User.location_updated_at, User.created_at]
    can_delete = False


class CategoryAdmin(ModelView, model=Category):
    name_plural = "Categories"
    column_list = [Category.id, Category.name]
    form_excluded_columns = [Category.products]


class ProductAdmin(ModelView, model=Product):
    column_list = [
        Product.id,
        Product.sku,
        Product.name,
        Product.category,
        Product.price,
        Product.is_available,
    ]
    column_searchable_list = [Product.sku, Product.name]
    form_excluded_columns = [Product.updated_at]


class ZoneAdmin(ModelView, model=DeliveryZone):
    column_list = [
        DeliveryZone.id,
        DeliveryZone.name,
        DeliveryZone.delivery_fee,
        DeliveryZone.min_order_amount,
        DeliveryZone.is_active,
    ]
    column_details_exclude_list = [DeliveryZone.area]
    form_excluded_columns = [DeliveryZone.area]
    # polygons are drawn on a map and sent to POST /zones
    can_create = False


class OrderAdmin(ModelView, model=Order):
    column_list = [
        Order.id,
        Order.status,
        Order.customer_id,
        Order.courier_id,
        Order.total,
        Order.address,
        Order.created_at,
    ]
    column_details_exclude_list = [Order.delivery_point]
    column_default_sort = [(Order.id, True)]
    # status changes have to go through the API so transitions stay checked
    can_create = False
    can_edit = False
    can_delete = False


class PaymentAdmin(ModelView, model=Payment):
    column_list = [
        Payment.id,
        Payment.order_id,
        Payment.amount,
        Payment.status,
        Payment.provider_txn_id,
        Payment.created_at,
    ]
    column_default_sort = [(Payment.id, True)]
    can_create = False
    can_edit = False
    can_delete = False


def setup_admin(app: FastAPI) -> Admin:
    admin = Admin(
        app,
        session_maker=SessionLocal,
        authentication_backend=BasicAuth(secret_key=settings.jwt_secret),
        title="Delivery admin",
    )
    for view in (UserAdmin, CategoryAdmin, ProductAdmin, ZoneAdmin, OrderAdmin, PaymentAdmin):
        admin.add_view(view)
    return admin
