"""Request and response bodies for the catalog and instructor stock changes."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MAX_STOCK = 100_000


class ProductView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sku: str
    name: str
    description: str
    price_cents: int = Field(description="Price in US cents.")
    currency: Literal["USD"]
    stock: int = Field(description="Units available now.")
    image_path: str = Field(description="Storefront path of the product image.")


class StockUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    stock: int = Field(ge=0, le=MAX_STOCK)
