"""Product table: catalog entries with prices in USD cents and available stock."""

from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from cloudcart.db import Base

CURRENCY = "USD"
SKU_MAX_LENGTH = 64
NAME_MAX_LENGTH = 120
DESCRIPTION_MAX_LENGTH = 500


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        # The SKU becomes part of the image URL, so it is limited to a URL- and file-safe slug.
        CheckConstraint(r"sku ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="sku_slug"),
        CheckConstraint("price_cents > 0", name="price_cents_positive"),
        # One currency keeps cart and order totals a plain sum.
        CheckConstraint(f"currency = '{CURRENCY}'", name="currency_usd"),
        # Checkout (Task 3) decrements stock with a guarded UPDATE; this is the backstop.
        CheckConstraint("stock >= 0", name="stock_not_negative"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    sku: Mapped[str] = mapped_column(String(SKU_MAX_LENGTH), unique=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    description: Mapped[str] = mapped_column(String(DESCRIPTION_MAX_LENGTH))
    price_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default=CURRENCY)
    stock: Mapped[int] = mapped_column(Integer)

    @property
    def image_path(self) -> str:
        """Bundled frontend image for this product, served by the storefront."""
        return f"/products/{self.sku}.svg"
