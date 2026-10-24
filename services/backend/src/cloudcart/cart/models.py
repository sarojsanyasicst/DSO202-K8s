"""Cart tables: one cart per guest, one line per product."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from cloudcart.catalog.models import Product
from cloudcart.db import Base
from cloudcart.identity.models import Guest


class Cart(Base):
    __tablename__ = "carts"
    __table_args__ = (CheckConstraint("version >= 0", name="version_not_negative"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    guest_id: Mapped[UUID] = mapped_column(ForeignKey(Guest.id, ondelete="CASCADE"), unique=True)
    # Incremented by exactly one on every change; checkout (Task 3) compares it to detect a stale cart.
    version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CartItem(Base):
    __tablename__ = "cart_items"
    # The per-line maximum is an API rule (cart/service.py); the table only forbids empty lines.
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)

    cart_id: Mapped[UUID] = mapped_column(ForeignKey(Cart.id, ondelete="CASCADE"), primary_key=True)
    product_id: Mapped[UUID] = mapped_column(ForeignKey(Product.id), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer)
