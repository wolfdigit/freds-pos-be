"""drop product cost_price and status

Revision ID: f3b9d2e18a44
Revises: e8a4c1b07d22
Create Date: 2026-10-17 21:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3b9d2e18a44"
down_revision: Union[str, Sequence[str], None] = "e8a4c1b07d22"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("product", "cost_price")
    op.drop_column("product", "status")


def downgrade() -> None:
    op.add_column(
        "product",
        sa.Column("cost_price", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "product",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
    )
    op.alter_column("product", "cost_price", server_default=None)
    op.alter_column("product", "status", server_default=None)
