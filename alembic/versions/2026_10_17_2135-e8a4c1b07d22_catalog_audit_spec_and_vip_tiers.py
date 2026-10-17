"""catalog spec, audit actors, line note, and Retail/B/A/S tiers

Revision ID: e8a4c1b07d22
Revises: d7c1e4a92b08
Create Date: 2026-10-17 21:35:00.000000

"""
from typing import Optional, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8a4c1b07d22"
down_revision: Union[str, Sequence[str], None] = "d7c1e4a92b08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return any(col["name"] == column for col in sa.inspect(bind).get_columns(table))


def _add_text(table: str, column: str, length: Optional[int] = None) -> None:
    if _has_column(table, column):
        return
    col_type = sa.String(length=length) if length is not None else sa.Text()
    op.add_column(table, sa.Column(column, col_type, nullable=True))


def upgrade() -> None:
    _add_text("product", "spec")
    _add_text("product", "created_by", 128)
    _add_text("product", "updated_by", 128)
    _add_text("customer", "created_by", 128)
    _add_text("customer", "updated_by", 128)
    _add_text("checkout_order", "created_by", 128)
    _add_text("checkout_order", "updated_by", 128)
    _add_text("checkout_order_item", "note")

    op.execute(
        """
        UPDATE customer
        SET vip_tier = CASE vip_tier
            WHEN 'platinum' THEN 'S'
            WHEN 'gold' THEN 'A'
            WHEN 'silver' THEN 'B'
            WHEN 'regular' THEN 'Retail'
            ELSE vip_tier
        END
        WHERE vip_tier IN ('platinum', 'gold', 'silver', 'regular')
        """
    )
    op.execute(
        """
        UPDATE checkout_order
        SET created_by = cashier_name
        WHERE created_by IS NULL
        """
    )
    op.execute(
        """
        UPDATE checkout_order
        SET updated_by = cashier_name
        WHERE updated_by IS NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE customer
        SET vip_tier = CASE vip_tier
            WHEN 'S' THEN 'platinum'
            WHEN 'A' THEN 'gold'
            WHEN 'B' THEN 'silver'
            WHEN 'Retail' THEN 'regular'
            ELSE vip_tier
        END
        WHERE vip_tier IN ('S', 'A', 'B', 'Retail')
        """
    )
    op.drop_column("checkout_order_item", "note")
    op.drop_column("checkout_order", "updated_by")
    op.drop_column("checkout_order", "created_by")
    op.drop_column("customer", "updated_by")
    op.drop_column("customer", "created_by")
    op.drop_column("product", "updated_by")
    op.drop_column("product", "created_by")
    op.drop_column("product", "spec")
