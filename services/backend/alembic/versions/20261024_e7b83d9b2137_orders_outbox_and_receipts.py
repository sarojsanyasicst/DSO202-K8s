"""Orders, order lines, the order outbox, and receipts.

Creates orders (unique per guest and Idempotency-Key), order_items (name and
price charged at checkout), outbox_events (exactly one per order, published_at
set by the publisher), and receipts (at most one per order, issued by the
worker). Order tables reference each other and guests without ON DELETE
CASCADE: orders are durable business records.

Revision ID: e7b83d9b2137
Revises: 371b57c4f5aa
Create Date: 2026-10-24 16:48:08.509752

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7b83d9b2137"
down_revision: Union[str, Sequence[str], None] = "371b57c4f5aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("guest_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("total_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("currency = 'USD'", name=op.f("ck_orders_currency_usd")),
        sa.CheckConstraint(
            "status IN ('accepted', 'processing', 'fulfilled', 'failed')", name=op.f("ck_orders_status_known")
        ),
        sa.CheckConstraint("total_cents > 0", name=op.f("ck_orders_total_cents_positive")),
        sa.ForeignKeyConstraint(["guest_id"], ["guests.id"], name=op.f("fk_orders_guest_id_guests")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
        sa.UniqueConstraint("guest_id", "idempotency_key", name=op.f("uq_orders_guest_id_idempotency_key")),
    )
    op.create_table(
        "order_items",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_order_items_quantity_positive")),
        sa.CheckConstraint("unit_price_cents > 0", name=op.f("ck_order_items_unit_price_cents_positive")),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name=op.f("fk_order_items_order_id_orders")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_order_items_product_id_products")),
        sa.PrimaryKeyConstraint("order_id", "product_id", name=op.f("pk_order_items")),
    )
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name=op.f("fk_outbox_events_order_id_orders")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_events")),
        sa.UniqueConstraint("order_id", name=op.f("uq_outbox_events_order_id")),
    )
    op.create_table(
        "receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name=op.f("fk_receipts_order_id_orders")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_receipts")),
        sa.UniqueConstraint("order_id", name=op.f("uq_receipts_order_id")),
    )


def downgrade() -> None:
    """Downgrade schema: drop dependants before the tables they reference."""
    op.drop_table("receipts")
    op.drop_table("outbox_events")
    op.drop_table("order_items")
    op.drop_table("orders")
