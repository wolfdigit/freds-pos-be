"""restore product status as the soft-delete record

Revision ID: b7d2a91c05e6
Revises: a1c6e8d04f11
Create Date: 2026-10-17 22:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7d2a91c05e6"
down_revision: Union[str, Sequence[str], None] = "a1c6e8d04f11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("product", sa.Column("status", sa.String(length=32), nullable=True))
    op.execute(
        sa.text(
            "UPDATE product SET status = CASE WHEN deleted THEN 'deleted' ELSE 'active' END"
        )
    )
    op.alter_column(
        "product",
        "status",
        existing_type=sa.String(length=32),
        nullable=False,
        server_default="active",
    )
    op.alter_column("product", "status", server_default=None)


def downgrade() -> None:
    op.drop_column("product", "status")
