"""map each store to one stock location

Revision ID: d5a9c2e18b44
Revises: c8e2a4b71d90
Create Date: 2026-11-08 04:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5a9c2e18b44"
down_revision: Union[str, Sequence[str], None] = "c8e2a4b71d90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 既有「門市現貨」。與 inventory migration 寫入的 id 相同，不另造一個地點。
SHARED_STOCK_LOCATION_ID = "e1a10001-0000-4000-8000-000000000001"


def upgrade() -> None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.text("SELECT count(*) FROM stock_location WHERE id = :id"),
        {"id": SHARED_STOCK_LOCATION_ID},
    ).scalar()
    if not exists:
        raise RuntimeError("找不到既有的門市現貨庫存地點 e1a10001-0000-4000-8000-000000000001，無法回填門市對應")
    op.add_column("store_branch", sa.Column("stock_location_id", sa.String(length=64), nullable=True))
    op.execute(
        sa.text(
            "UPDATE store_branch SET stock_location_id = :loc WHERE stock_location_id IS NULL"
        ).bindparams(loc=SHARED_STOCK_LOCATION_ID)
    )
    with op.batch_alter_table("store_branch") as batch:
        batch.alter_column("stock_location_id", existing_type=sa.String(length=64), nullable=False)
        batch.create_foreign_key(
            "fk_store_branch_stock_location",
            "stock_location",
            ["stock_location_id"],
            ["id"],
        )
    op.create_index("ix_store_branch_stock_location_id", "store_branch", ["stock_location_id"])


def downgrade() -> None:
    op.drop_index("ix_store_branch_stock_location_id", table_name="store_branch")
    with op.batch_alter_table("store_branch") as batch:
        batch.drop_constraint("fk_store_branch_stock_location", type_="foreignkey")
        batch.drop_column("stock_location_id")
