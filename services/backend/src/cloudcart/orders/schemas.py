"""Request and response bodies for checkout, guest orders, and receipts."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from cloudcart.identity.schemas import UtcDatetime
from cloudcart.orders.models import OrderStatus

PaymentOutcome = Literal["approved", "declined"]
# Clients send a fresh random value (e.g. a UUID) per checkout attempt and reuse it only for retries.
IDEMPOTENCY_KEY_PATTERN = r"^[A-Za-z0-9_-]{8,128}$"
MAX_CART_VERSION = 2**31 - 1  # the carts.version column is a PostgreSQL integer


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    cart_version: int = Field(
        ge=0,
        le=MAX_CART_VERSION,
        description="The `version` of the cart the shopper reviewed; checkout refuses a cart that changed since.",
    )
    payment_outcome: PaymentOutcome = Field(description="Simulated payment result. No real payment is taken.")


class OrderItemView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: UUID
    name: str = Field(description="Product name at checkout.")
    quantity: int
    unit_price_cents: int = Field(description="Price charged per unit at checkout, in US cents.")


class OrderView(BaseModel):
    id: UUID
    status: OrderStatus
    publication_pending: bool = Field(description="True until the order has been handed to the fulfillment queue.")
    total_cents: int
    created_at: UtcDatetime
    receipt_available: bool
    items: list[OrderItemView]


class ReceiptView(BaseModel):
    id: UUID
    order_id: UUID
    issued_at: UtcDatetime
    items: list[OrderItemView]
    total_cents: int
    currency: Literal["USD"]


class FulfillmentResult(BaseModel):
    """Outcome of one fulfillment step on an order, as the worker records it in PostgreSQL."""

    order_id: UUID
    status: OrderStatus
    receipt_id: UUID | None
    already_applied: bool = Field(description="True when an earlier delivery had already finished the order.")
