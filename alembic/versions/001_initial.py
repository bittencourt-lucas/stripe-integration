"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "stripe_payment_intent_id", sa.String(255), unique=True, nullable=False
        ),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("customer_id", sa.String(255), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_payment_records_stripe_payment_intent_id",
        "payment_records",
        ["stripe_payment_intent_id"],
    )

    op.create_table(
        "webhook_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("stripe_event_id", sa.String(255), unique=True, nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_webhook_events_stripe_event_id",
        "webhook_events",
        ["stripe_event_id"],
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("request_path", sa.String(500), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("key", "request_path", name="uq_idempotency_key_path"),
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys")
    op.drop_index("ix_webhook_events_stripe_event_id", table_name="webhook_events")
    op.drop_table("webhook_events")
    op.drop_index(
        "ix_payment_records_stripe_payment_intent_id", table_name="payment_records"
    )
    op.drop_table("payment_records")
