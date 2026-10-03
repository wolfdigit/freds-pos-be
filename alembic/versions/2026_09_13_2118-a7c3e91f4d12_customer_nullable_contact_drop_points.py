"""customer nullable contact drop reward_points

Revision ID: a7c3e91f4d12
Revises: c4a7e19d2b80
Create Date: 2026-09-13 21:18:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a7c3e91f4d12"
down_revision: Union[str, Sequence[str], None] = "c4a7e19d2b80"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("customer") as batch_op:
        batch_op.drop_index("ix_customer_reward_points")
        batch_op.drop_column("reward_points")
        batch_op.alter_column(
            "phone",
            existing_type=sa.String(length=64),
            nullable=True,
        )
        batch_op.alter_column(
            "email",
            existing_type=sa.String(length=256),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("customer") as batch_op:
        batch_op.alter_column(
            "email",
            existing_type=sa.String(length=256),
            nullable=False,
        )
        batch_op.alter_column(
            "phone",
            existing_type=sa.String(length=64),
            nullable=False,
        )
        batch_op.add_column(
            sa.Column(
                "reward_points",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.create_index(
            "ix_customer_reward_points", ["reward_points"], unique=False
        )
    with op.batch_alter_table("customer") as batch_op:
        batch_op.alter_column("reward_points", server_default=None)
