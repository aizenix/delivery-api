from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import ValidationError

from app.api.deps import CurrentUser, SessionDep
from app.schemas.payments import PaymentCreate, PaymentOut, WebhookEvent
from app.services import payments

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("", status_code=201)
async def create_payment(data: PaymentCreate, user: CurrentUser, session: SessionDep) -> PaymentOut:
    payment = await payments.create_payment(session, user, data.order_id)
    return PaymentOut(
        payment_id=payment.id,
        amount=payment.amount,
        checkout_url=payments.checkout_url(payment),
    )


@router.post("/webhook")
async def payment_webhook(
    request: Request,
    session: SessionDep,
    x_signature: Annotated[str | None, Header()] = None,
) -> dict:
    # the signature covers the exact bytes the provider sent, so verify before parsing
    body = await request.body()
    if not payments.verify_signature(body, x_signature):
        raise HTTPException(401, "invalid signature")
    try:
        event = WebhookEvent.model_validate_json(body)
    except ValidationError:
        raise HTTPException(400, "malformed payload") from None

    return {"status": await payments.process_webhook(session, event)}
