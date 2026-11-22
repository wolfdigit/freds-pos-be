"""drop preorder tables

Revision ID: c5e8f1a3d7b2
Revises: b3d9f2a6c481
Create Date: 2026-11-23 02:00:00.000000

預購功能整個移除，刪掉 pre_order_item、pre_order、product_pre_order_pending 三張表。
沒有其他表的 FK 指向這三張表（checkout_order_item 的預購欄位已在 c3f8a1b04e55 移除）。

不可逆：upgrade 會刪掉表裡的資料。downgrade 只依原結構重建空表（含 FK 與索引），
不會還原任何資料。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c5e8f1a3d7b2"
down_revision: Union[str, Sequence[str], None] = "b3d9f2a6c481"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 子表先刪；索引與 FK 隨表一起刪除。
    op.drop_table("pre_order_item")
    op.drop_table("pre_order")
    op.drop_table("product_pre_order_pending")


def downgrade() -> None:
    # 結構對齊 b3d9f2a6c481 時的樣子。只建空表，資料不會回來。
    op.create_table(
        "product_pre_order_pending",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["product.id"],
            name="product_pre_order_pending_product_id_fkey",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="product_pre_order_pending_pkey"),
        sa.UniqueConstraint("product_id", name="product_pre_order_pending_product_id_key"),
    )

    op.create_table(
        "pre_order",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("order_number", sa.String(length=32), nullable=False),
        sa.Column("customer_id", sa.String(length=64), nullable=True),
        sa.Column("customer_name", sa.String(length=256), nullable=True),
        sa.Column("customer_phone", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("expected_arrival_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("operator_name", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customer.id"],
            name="pre_order_customer_id_fkey",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pre_order_pkey"),
        sa.UniqueConstraint("order_number", name="pre_order_order_number_key"),
    )
    op.create_index("ix_pre_order_customer_id", "pre_order", ["customer_id"])

    op.create_table(
        "pre_order_item",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("pre_order_id", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("sku", sa.String(length=128), nullable=False),
        sa.Column("product_name", sa.String(length=256), nullable=False),
        sa.Column("scale", sa.String(length=32), nullable=False),
        sa.Column("brand", sa.String(length=128), nullable=False),
        sa.Column("quoted_price", sa.Integer(), nullable=False),
        sa.Column("qty_ordered", sa.Integer(), nullable=False),
        sa.Column("qty_arrived", sa.Integer(), nullable=False),
        sa.Column("qty_delivered", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["pre_order_id"],
            ["pre_order.id"],
            name="pre_order_item_pre_order_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["product.id"],
            name="pre_order_item_product_id_fkey",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pre_order_item_pkey"),
    )
    op.create_index("ix_pre_order_item_pre_order_id", "pre_order_item", ["pre_order_id"])
    op.create_index("ix_pre_order_item_product_id", "pre_order_item", ["product_id"])
