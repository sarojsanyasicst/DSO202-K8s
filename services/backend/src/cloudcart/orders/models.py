"""Order tables: accepted orders and their lines, the outbox event per order, and receipts.

Orders are durable business records: nothing deletes them, and the foreign keys
below deliberately have no ON DELETE CASCADE, so a guest with orders cannot be
deleted either.
"""

from datetime import datetime
from typing import Literal, get_args
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cloudcart.catalog.models import CURRENCY, NAME_MAX_LENGTH, Product
from cloudcart.db import Base
from cloudcart.identity.models import Guest

OrderStatus = Literal["accepted", "processing", "fulfilled", "failed"]
ORDER_STATUSES: tuple[str, ...] = get_args(OrderStatus)
IDEMPOTENCY_KEY_MAX_LENGTH = 128
FINGERPRINT_LENGTH = 64  # hex SHA-256


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        # A retried checkout finds its order by key; a key only has meaning within one guest.
        UniqueConstraint("guest_id", "idempotency_key"),
        CheckConstraint(f"status IN ({', '.join(repr(status) for status in ORDER_STATUSES)})", name="status_known"),
        CheckConstraint("total_cents > 0", name="total_cents_positive"),
        CheckConstraint(f"currency = '{CURRENCY}'", name="currency_usd"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    guest_id: Mapped[UUID] = mapped_column(ForeignKey(Guest.id))
    idempotency_key: Mapped[str] = mapped_column(String(IDEMPOTENCY_KEY_MAX_LENGTH))
    # SHA-256 of the checkout request body: a retry with the same key must repeat the same request.
    request_fingerprint: Mapped[str] = mapped_column(String(FINGERPRINT_LENGTH))
    status: Mapped[str] = mapped_column(String(16), default="accepted")
    # Up to 20 lines of 10 units at any Integer price, so the sum needs 64 bits.
    total_cents: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default=CURRENCY)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items: Mapped[list["OrderItem"]] = relationship(lazy="selectin")
    outbox_event: Mapped["OutboxEvent | None"] = relationship(lazy="selectin")
    receipt: Mapped["Receipt | None"] = relationship(lazy="selectin")


class OrderItem(Base):
    """One ordered product, with the name and unit price charged at checkout."""

    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price_cents > 0", name="unit_price_cents_positive"),
    )

    order_id: Mapped[UUID] = mapped_column(ForeignKey(Order.id), primary_key=True)
    product_id: Mapped[UUID] = mapped_column(ForeignKey(Product.id), primary_key=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_cents: Mapped[int] = mapped_column(Integer)


class OutboxEvent(Base):
    """Hands one accepted order to the fulfillment worker.

    Checkout writes it in the same transaction as the order. The publisher (Task 4)
    sets `published_at` only after the broker confirms the message.
    """

    __tablename__ = "outbox_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(ForeignKey(Order.id), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Receipt(Base):
    """Issued by the fulfillment worker (Task 4); at most one per order. Lines and totals come from the order."""

    __tablename__ = "receipts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(ForeignKey(Order.id), unique=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
