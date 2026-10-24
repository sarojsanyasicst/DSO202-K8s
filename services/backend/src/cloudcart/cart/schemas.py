"""Request and response bodies for the guest cart."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MAX_LINE_QUANTITY = 10


class CartItemView(BaseModel):
    product_id: UUID
    quantity: int
    unit_price_cents: int = Field(description="The product's current price; checkout re-prices on the server.")


class CartView(BaseModel):
    id: UUID
    version: int = Field(description="Starts at 0 and increases by exactly 1 with every change to the cart.")
    items: list[CartItemView]
    total_cents: int


class CartItemQuantity(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    quantity: int = Field(ge=1, le=MAX_LINE_QUANTITY, description="The line's new quantity (replaces, not adds).")
