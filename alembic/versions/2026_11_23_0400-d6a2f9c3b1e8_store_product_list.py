"""per-store product list: store_branch.product_scope + store_product

Revision ID: d6a2f9c3b1e8
Revises: d7a2c4e9b156
Create Date: 2026-11-23 04:00:00.000000

- store_branch.product_scope：'all'（預設，既有門市不變）或 'list'。
- store_product：'list' 門市販售的商品。刪除門市時一併刪除（CASCADE）；
  商品只會軟刪除，所以商品 FK 用 RESTRICT，已刪除商品留在清單裡但不顯示。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d6a2f9c3b1e8"
down_revision: Union[str, Sequence[str], None] = "d7a2c4e9b156"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("store_branch") as batch_op:
        batch_op.add_column(
            sa.Column("product_scope", sa.String(length=16), nullable=False, server_default="all")
        )
        batch_op.create_check_constraint(
            "ck_store_branch_product_scope", "product_scope IN ('all', 'list')"
        )
    op.create_table(
        "store_product",
        sa.Column("store_name", sa.String(length=128), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(
            ["store_name"], ["store_branch.name"], name="fk_store_product_store", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["product.id"], name="fk_store_product_product", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("store_name", "product_id", name="pk_store_product"),
    )
    op.create_index("ix_store_product_product_id", "store_product", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_store_product_product_id", table_name="store_product")
    op.drop_table("store_product")
    with op.batch_alter_table("store_branch") as batch_op:
        batch_op.drop_constraint("ck_store_branch_product_scope", type_="check")
        batch_op.drop_column("product_scope")
