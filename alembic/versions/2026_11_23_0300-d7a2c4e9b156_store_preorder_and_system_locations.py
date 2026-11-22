"""store preorder binding, system locations, preorder pickup line flag

Revision ID: d7a2c4e9b156
Revises: c5e8f1a3d7b2
Create Date: 2026-11-23 03:00:00.000000

- inventory_location.system_role：company（公司總倉）/ preorder（預購保留）/ defective（退貨品），唯一。
  - 公司總倉沿用 e1a10003、退貨品沿用 e1a10005，都不改名（沒有就找同名，再沒有就用原名新建）。
  - 預購保留：已有同名地點就接管，否則新建 e1a10006。
  - 地點表是空的（全新資料庫）時不建立，交給程式的 ensure_locations 連同預設地點一起建立。
- store_branch.preorder_inventory_location_id：NOT NULL、FK RESTRICT。既有門市回填為「預購保留」。
  門市庫存與退貨綁定不變。
- checkout_order_item.preorder_pickup：NOT NULL，預設 false。

downgrade 刪掉三個新欄位；新建的系統地點保留為一般地點（不刪，避免遺失庫存數量與異動紀錄）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7a2c4e9b156"
down_revision: Union[str, Sequence[str], None] = "c5e8f1a3d7b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (system_role, 固定 id, 名稱, 圖示, 是否沿用固定 id 的既有地點)
SYSTEM_LOCATIONS = (
    ("company", "e1a10003-0000-4000-8000-000000000003", "公司總倉", "🏢", True),
    ("defective", "e1a10005-0000-4000-8000-000000000005", "退貨品", "↩️", True),
    ("preorder", "e1a10006-0000-4000-8000-000000000006", "預購保留", "📋", False),
)


def assign_system_locations(conn) -> None:
    """給三個系統地點設定 system_role；缺的就新建。地點表是空的時候什麼都不做。"""

    if conn.execute(sa.text("SELECT COUNT(*) FROM inventory_location")).scalar() == 0:
        return
    for role, loc_id, name, icon, reuse_id in SYSTEM_LOCATIONS:
        if conn.execute(
            sa.text("SELECT 1 FROM inventory_location WHERE system_role = :role"), {"role": role}
        ).first():
            continue
        target = None
        if reuse_id:
            target = conn.execute(
                sa.text("SELECT id FROM inventory_location WHERE id = :id AND system_role IS NULL"), {"id": loc_id}
            ).scalar()
        if target is None:
            target = conn.execute(
                sa.text("SELECT id FROM inventory_location WHERE name = :name AND system_role IS NULL"),
                {"name": name},
            ).scalar()
        if target is not None:
            conn.execute(
                sa.text("UPDATE inventory_location SET system_role = :role WHERE id = :id"),
                {"role": role, "id": target},
            )
            continue
        next_order = conn.execute(sa.text("SELECT COALESCE(MAX(display_order), 0) + 1 FROM inventory_location")).scalar()
        conn.execute(
            sa.text(
                "INSERT INTO inventory_location (id, name, icon, is_default, display_order, system_role) "
                "VALUES (:id, :name, :icon, FALSE, :display_order, :role)"
            ),
            {"id": loc_id, "name": name, "icon": icon, "display_order": next_order, "role": role},
        )


def backfill_store_preorder(conn) -> None:
    preorder_id = conn.execute(
        sa.text("SELECT id FROM inventory_location WHERE system_role = 'preorder'")
    ).scalar()
    if preorder_id is None:
        if conn.execute(sa.text("SELECT COUNT(*) FROM store_branch")).scalar():
            raise RuntimeError("store_branch 有資料但找不到預購保留地點")
        return
    conn.execute(
        sa.text(
            "UPDATE store_branch SET preorder_inventory_location_id = :id "
            "WHERE preorder_inventory_location_id IS NULL"
        ),
        {"id": preorder_id},
    )


def upgrade() -> None:
    with op.batch_alter_table("inventory_location") as batch:
        batch.add_column(sa.Column("system_role", sa.String(length=16), nullable=True))
        batch.create_unique_constraint("uq_inventory_location_system_role", ["system_role"])

    conn = op.get_bind()
    assign_system_locations(conn)

    op.add_column("store_branch", sa.Column("preorder_inventory_location_id", sa.String(length=64), nullable=True))
    backfill_store_preorder(conn)
    with op.batch_alter_table("store_branch") as batch:
        batch.alter_column("preorder_inventory_location_id", existing_type=sa.String(length=64), nullable=False)
        batch.create_foreign_key(
            "fk_store_branch_preorder_inventory_location",
            "inventory_location",
            ["preorder_inventory_location_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_index(
        "ix_store_branch_preorder_inventory_location_id", "store_branch", ["preorder_inventory_location_id"]
    )

    op.add_column(
        "checkout_order_item",
        sa.Column("preorder_pickup", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    with op.batch_alter_table("checkout_order_item") as batch:
        batch.drop_column("preorder_pickup")

    op.drop_index("ix_store_branch_preorder_inventory_location_id", table_name="store_branch")
    with op.batch_alter_table("store_branch") as batch:
        batch.drop_constraint("fk_store_branch_preorder_inventory_location", type_="foreignkey")
        batch.drop_column("preorder_inventory_location_id")

    with op.batch_alter_table("inventory_location") as batch:
        batch.drop_constraint("uq_inventory_location_system_role", type_="unique")
        batch.drop_column("system_role")
