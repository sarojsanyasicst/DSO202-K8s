"""Catalog, guest and instructor sessions, and persistent carts.

Creates products, guests, instructors, instructor_sessions, carts, and
cart_items. Session tables hold only SHA-256 digests of session tokens; the
instructor table holds only an Argon2id password hash. Demo data comes from the
seed command (`python -m cloudcart.seed`), never from migrations.

Revision ID: 371b57c4f5aa
Revises:
Create Date: 2026-10-24 10:34:07.889979

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "371b57c4f5aa"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("stock", sa.Integer(), nullable=False),
        sa.CheckConstraint("sku ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name=op.f("ck_products_sku_slug")),
        sa.CheckConstraint("price_cents > 0", name=op.f("ck_products_price_cents_positive")),
        sa.CheckConstraint("currency = 'USD'", name=op.f("ck_products_currency_usd")),
        sa.CheckConstraint("stock >= 0", name=op.f("ck_products_stock_not_negative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.UniqueConstraint("sku", name=op.f("uq_products_sku")),
    )
    op.create_table(
        "guests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_guests")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_guests_token_hash")),
    )
    op.create_table(
        "instructors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_instructors")),
        sa.UniqueConstraint("username", name=op.f("uq_instructors_username")),
    )
    op.create_table(
        "instructor_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("instructor_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["instructor_id"],
            ["instructors.id"],
            name=op.f("fk_instructor_sessions_instructor_id_instructors"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_instructor_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_instructor_sessions_token_hash")),
    )
    op.create_table(
        "carts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("guest_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("version >= 0", name=op.f("ck_carts_version_not_negative")),
        sa.ForeignKeyConstraint(["guest_id"], ["guests.id"], name=op.f("fk_carts_guest_id_guests"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_carts")),
        sa.UniqueConstraint("guest_id", name=op.f("uq_carts_guest_id")),
    )
    op.create_table(
        "cart_items",
        sa.Column("cart_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_cart_items_quantity_positive")),
        sa.ForeignKeyConstraint(
            ["cart_id"], ["carts.id"], name=op.f("fk_cart_items_cart_id_carts"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name=op.f("fk_cart_items_product_id_products")),
        sa.PrimaryKeyConstraint("cart_id", "product_id", name=op.f("pk_cart_items")),
    )


def downgrade() -> None:
    """Downgrade schema: drop dependants before the tables they reference."""
    op.drop_table("cart_items")
    op.drop_table("carts")
    op.drop_table("instructor_sessions")
    op.drop_table("instructors")
    op.drop_table("guests")
    op.drop_table("products")
