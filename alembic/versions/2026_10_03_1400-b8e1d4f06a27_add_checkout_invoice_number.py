"""add checkout invoice number

Revision ID: b8e1d4f06a27
Revises: e4b7c2a91d30
Create Date: 2026-10-03 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8e1d4f06a27"
down_revision: Union[str, Sequence[str], None] = "e4b7c2a91d30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "checkout_order",
        sa.Column("invoice_number", sa.String(length=64), nullable=True),
    )
    op.execute(
        "UPDATE checkout_order SET invoice_number = id WHERE invoice_number IS NULL"
    )
    op.alter_column("checkout_order", "invoice_number", nullable=False)
    op.create_index(
        "ix_checkout_order_invoice_number",
        "checkout_order",
        ["invoice_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_checkout_order_invoice_number", table_name="checkout_order")
    op.drop_column("checkout_order", "invoice_number")
