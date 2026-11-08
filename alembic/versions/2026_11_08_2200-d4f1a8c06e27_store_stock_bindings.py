"""store stock bindings, stock conditions, receipts and movements

Revision ID: d4f1a8c06e27
Revises: c8e2a4b71d90
Create Date: 2026-11-08 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4f1a8c06e27"
down_revision: Union[str, Sequence[str], None] = "c8e2a4b71d90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SHELF_ID = "e1a10001-0000-4000-8000-000000000001"


def upgrade() -> None:
    op.add_column(
        "product_stock",
        sa.Column("condition", sa.String(length=16), nullable=True, server_default="normal"),
    )
    op.execute("UPDATE product_stock SET condition = 'normal' WHERE condition IS NULL")
    with op.batch_alter_table("product_stock") as batch:
        batch.alter_column("condition", existing_type=sa.String(length=16), nullable=False)
        batch.alter_column(
            "location_name",
            existing_type=sa.String(length=64),
            type_=sa.String(length=128),
            existing_nullable=False,
        )
        batch.drop_constraint("uq_product_stock_product_location", type_="unique")
        batch.create_unique_constraint(
            "uq_product_stock_product_location_condition",
            ["product_id", "location", "condition"],
        )
        batch.create_foreign_key(
            "fk_product_stock_location",
            "stock_location",
            ["location"],
            ["id"],
            ondelete="RESTRICT",
        )

    op.create_unique_constraint("uq_stock_location_name", "stock_location", ["name"])
    op.add_column("store_branch", sa.Column("stock_location_id", sa.String(length=64), nullable=True))
    op.execute(
        sa.text("UPDATE store_branch SET stock_location_id = :shelf WHERE stock_location_id IS NULL").bindparams(
            shelf=SHELF_ID
        )
    )
    with op.batch_alter_table("store_branch") as batch:
        batch.alter_column("stock_location_id", existing_type=sa.String(length=64), nullable=False)
        batch.create_foreign_key(
            "fk_store_branch_stock_location",
            "stock_location",
            ["stock_location_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    op.add_column("checkout_order_item", sa.Column("stock_location_id", sa.String(length=64), nullable=True))
    op.add_column("checkout_order_item", sa.Column("stock_location_name", sa.String(length=128), nullable=True))
    op.add_column("checkout_order_item", sa.Column("stock_condition", sa.String(length=16), nullable=True))

    op.create_table(
        "stock_receipt",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("location_id", sa.String(length=64), nullable=False),
        sa.Column("location_name", sa.String(length=128), nullable=False),
        sa.Column("supplier", sa.String(length=128), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("operator_name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "stock_receipt_item",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("receipt_id", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("sku", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
    )
    op.create_index("ix_stock_receipt_item_receipt_id", "stock_receipt_item", ["receipt_id"])
    op.create_index("ix_stock_receipt_item_product_id", "stock_receipt_item", ["product_id"])
    op.create_table(
        "stock_movement",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("location_id", sa.String(length=64), nullable=False),
        sa.Column("condition", sa.String(length=16), nullable=False),
        sa.Column("quantity_delta", sa.Integer(), nullable=False),
        sa.Column("quantity_after", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("operator_name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_stock_movement_product_id", "stock_movement", ["product_id"])
    op.create_index("ix_stock_movement_location_id", "stock_movement", ["location_id"])
    op.create_index("ix_stock_movement_created_at", "stock_movement", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_stock_movement_created_at", table_name="stock_movement")
    op.drop_index("ix_stock_movement_location_id", table_name="stock_movement")
    op.drop_index("ix_stock_movement_product_id", table_name="stock_movement")
    op.drop_table("stock_movement")
    op.drop_index("ix_stock_receipt_item_product_id", table_name="stock_receipt_item")
    op.drop_index("ix_stock_receipt_item_receipt_id", table_name="stock_receipt_item")
    op.drop_table("stock_receipt_item")
    op.drop_table("stock_receipt")
    op.drop_column("checkout_order_item", "stock_condition")
    op.drop_column("checkout_order_item", "stock_location_name")
    op.drop_column("checkout_order_item", "stock_location_id")
    with op.batch_alter_table("store_branch") as batch:
        batch.drop_constraint("fk_store_branch_stock_location", type_="foreignkey")
        batch.drop_column("stock_location_id")
    op.drop_constraint("uq_stock_location_name", "stock_location", type_="unique")
    with op.batch_alter_table("product_stock") as batch:
        batch.drop_constraint("fk_product_stock_location", type_="foreignkey")
        batch.drop_constraint("uq_product_stock_product_location_condition", type_="unique")
        batch.create_unique_constraint("uq_product_stock_product_location", ["product_id", "location"])
        batch.drop_column("condition")
        batch.alter_column(
            "location_name",
            existing_type=sa.String(length=128),
            type_=sa.String(length=64),
            existing_nullable=False,
        )
