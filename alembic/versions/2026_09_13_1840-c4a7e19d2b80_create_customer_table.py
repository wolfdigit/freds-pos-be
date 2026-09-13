"""create_customer_table

Revision ID: c4a7e19d2b80
Revises: 9fea24686b8f
Create Date: 2026-09-13 18:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c4a7e19d2b80"
down_revision: Union[str, Sequence[str], None] = "9fea24686b8f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customer",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("phone", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=256), nullable=False),
        sa.Column("vip_tier", sa.String(length=32), nullable=False),
        sa.Column("reward_points", sa.Integer(), nullable=False),
        sa.Column("total_spent", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_customer_name", "customer", ["name"], unique=False)
    op.create_index("ix_customer_vip_tier", "customer", ["vip_tier"], unique=False)
    op.create_index(
        "ix_customer_reward_points", "customer", ["reward_points"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_customer_reward_points", table_name="customer")
    op.drop_index("ix_customer_vip_tier", table_name="customer")
    op.drop_index("ix_customer_name", table_name="customer")
    op.drop_table("customer")
