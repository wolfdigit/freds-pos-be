"""create_product_catalog_tables

Revision ID: 9fea24686b8f
Revises:
Create Date: 2026-09-07 04:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "9fea24686b8f"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "product",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("sku", sa.String(length=128), nullable=False),
        sa.Column("normalized_sku", sa.String(length=128), nullable=False),
        sa.Column("barcode", sa.String(length=128), nullable=False),
        sa.Column("brand", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("scale", sa.String(length=32), nullable=False),
        sa.Column("material", sa.String(length=128), nullable=True),
        sa.Column("color", sa.String(length=128), nullable=True),
        sa.Column("image_url", sa.String(length=512), nullable=True),
        sa.Column("list_price", sa.Integer(), nullable=False),
        sa.Column("cost_price", sa.Integer(), nullable=False),
        sa.Column("vip_price", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sku"),
    )
    op.create_index("ix_product_barcode", "product", ["barcode"], unique=False)
    op.create_index("ix_product_brand", "product", ["brand"], unique=False)
    op.create_index(
        "ix_product_normalized_sku", "product", ["normalized_sku"], unique=False
    )

    op.create_table(
        "product_stock",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("location", sa.String(length=32), nullable=False),
        sa.Column("location_name", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_id", "location", name="uq_product_stock_product_location"
        ),
    )
    op.create_index(
        "ix_product_stock_product_id", "product_stock", ["product_id"], unique=False
    )

    op.create_table(
        "product_pre_order_pending",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id"),
    )


def downgrade() -> None:
    op.drop_table("product_pre_order_pending")
    op.drop_index("ix_product_stock_product_id", table_name="product_stock")
    op.drop_table("product_stock")
    op.drop_index("ix_product_normalized_sku", table_name="product")
    op.drop_index("ix_product_brand", table_name="product")
    op.drop_index("ix_product_barcode", table_name="product")
    op.drop_table("product")
