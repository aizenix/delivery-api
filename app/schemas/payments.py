from typing import Literal

from pydantic import BaseModel, Field


class PaymentCreate(BaseModel):
    order_id: int


class PaymentOut(BaseModel):
    payment_id: int
    amount: int
    checkout_url: str


class WebhookEvent(BaseModel):
    transaction_id: str = Field(min_length=1, max_length=64)
    # our payment id, sent to the provider in the checkout url
    merchant_ref: int
    amount: int
    status: Literal["succeeded", "failed"]
