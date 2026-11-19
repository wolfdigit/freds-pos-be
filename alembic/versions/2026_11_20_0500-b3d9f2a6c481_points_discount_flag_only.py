"""points discount: store only the line flag, split order discount from points

Revision ID: b3d9f2a6c481
Revises: 8be3027059d9
Create Date: 2026-11-20 05:00:00.000000

- checkout_order_item.points_discount_amount (固定 360) 移除，只留 points_discount_applied 旗標。
  點數折抵金額改由 (original_price − unit_price) × quantity 計算。
- 原單點數列的退貨列沿用旗標，退回的差額記在點數折抵。
- checkout_order.discount_amount（折讓）重算成：手動改價且沒有點數旗標的列的差額。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3d9f2a6c481"
down_revision: Union[str, Sequence[str], None] = "8be3027059d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 純 SQL，Postgres 與 SQLite 都能跑。
UPGRADE_BACKFILL = (
    # 退貨列沿用原單點數列的旗標。
    """
    UPDATE checkout_order_item
    SET points_discount_applied = TRUE
    WHERE quantity < 0
      AND points_discount_applied = FALSE
      AND original_order_item_id IN (
        SELECT id FROM (
          SELECT id FROM checkout_order_item
          WHERE quantity > 0 AND points_discount_applied = TRUE
        ) AS redeemed
      )
    """,
    # 折讓不含點數列。
    """
    UPDATE checkout_order
    SET discount_amount = COALESCE((
      SELECT SUM((i.original_price - i.unit_price) * i.quantity)
      FROM checkout_order_item i
      WHERE i.order_id = checkout_order.id
        AND i.is_manual_price = TRUE
        AND i.points_discount_applied = FALSE
    ), 0)
    """,
)

DOWNGRADE_BACKFILL = (
    # 舊版每個點數銷售列固定記 360，退貨列不帶旗標。
    """
    UPDATE checkout_order_item
    SET points_discount_amount = CASE
      WHEN points_discount_applied = TRUE AND quantity > 0 THEN 360 ELSE 0 END
    """,
    """
    UPDATE checkout_order_item
    SET points_discount_applied = FALSE
    WHERE quantity < 0
    """,
    # 舊版折讓 = 所有手動改價列的差額（含點數列）。
    """
    UPDATE checkout_order
    SET discount_amount = COALESCE((
      SELECT SUM((i.original_price - i.unit_price) * i.quantity)
      FROM checkout_order_item i
      WHERE i.order_id = checkout_order.id
        AND i.is_manual_price = TRUE
    ), 0)
    """,
)


def apply_upgrade_backfill(execute) -> None:
    for statement in UPGRADE_BACKFILL:
        execute(sa.text(statement))


def apply_downgrade_backfill(execute) -> None:
    for statement in DOWNGRADE_BACKFILL:
        execute(sa.text(statement))


def upgrade() -> None:
    apply_upgrade_backfill(op.execute)
    with op.batch_alter_table("checkout_order_item") as batch:
        batch.drop_column("points_discount_amount")


def downgrade() -> None:
    with op.batch_alter_table("checkout_order_item") as batch:
        batch.add_column(
            sa.Column("points_discount_amount", sa.Integer(), nullable=False, server_default="0")
        )
    apply_downgrade_backfill(op.execute)
