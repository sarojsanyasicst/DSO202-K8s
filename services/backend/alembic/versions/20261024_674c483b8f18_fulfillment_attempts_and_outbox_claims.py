"""Fulfillment attempts and failure records on orders; publisher claims on outbox events.

Adds orders.fulfillment_attempts (attempts the worker started, 0 for existing
orders) and orders.failure_reason (set exactly when an order failed), plus
outbox_events.claimed_until (a publisher's lease) and a partial index on
unpublished events for the publisher's claim query.

Revision ID: 674c483b8f18
Revises: e7b83d9b2137
Create Date: 2026-10-24 21:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "674c483b8f18"
down_revision: Union[str, Sequence[str], None] = "e7b83d9b2137"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "orders", sa.Column("fulfillment_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False)
    )
    op.add_column("orders", sa.Column("failure_reason", sa.String(length=200), nullable=True))
    op.create_check_constraint(
        op.f("ck_orders_fulfillment_attempts_not_negative"), "orders", "fulfillment_attempts >= 0"
    )
    op.create_check_constraint(
        op.f("ck_orders_failure_reason_when_failed"), "orders", "(status = 'failed') = (failure_reason IS NOT NULL)"
    )
    op.add_column("outbox_events", sa.Column("claimed_until", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_outbox_events_unpublished",
        "outbox_events",
        ["created_at", "id"],
        unique=False,
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_outbox_events_unpublished", table_name="outbox_events", postgresql_where=sa.text("published_at IS NULL")
    )
    op.drop_column("outbox_events", "claimed_until")
    op.drop_constraint(op.f("ck_orders_failure_reason_when_failed"), "orders", type_="check")
    op.drop_constraint(op.f("ck_orders_fulfillment_attempts_not_negative"), "orders", type_="check")
    op.drop_column("orders", "failure_reason")
    op.drop_column("orders", "fulfillment_attempts")
