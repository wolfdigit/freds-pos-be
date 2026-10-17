"""checkout orders and preorder pickup tables

Revision ID: e4b7c2a91d30
Revises: a7c3e91f4d12
Create Date: 2026-09-29 02:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e4b7c2a91d30"
down_revision: Union[str, Sequence[str], None] = "a7c3e91f4d12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_number"),
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
        sa.ForeignKeyConstraint(["pre_order_id"], ["pre_order.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pre_order_item_pre_order_id", "pre_order_item", ["pre_order_id"])
    op.create_index("ix_pre_order_item_product_id", "pre_order_item", ["product_id"])

    op.create_table(
        "checkout_order",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("order_number", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("idempotency_body_hash", sa.String(length=64), nullable=True),
        sa.Column("branch_id", sa.String(length=64), nullable=False),
        sa.Column("branch_name", sa.String(length=128), nullable=False),
        sa.Column("cashier_id", sa.String(length=64), nullable=False),
        sa.Column("cashier_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("customer_id", sa.String(length=64), nullable=True),
        sa.Column("customer_name", sa.String(length=256), nullable=True),
        sa.Column("customer_phone", sa.String(length=64), nullable=True),
        sa.Column("items_subtotal", sa.Integer(), nullable=False),
        sa.Column("discount_amount", sa.Integer(), nullable=False),
        sa.Column("shipping_fee", sa.Integer(), nullable=False),
        sa.Column("total_amount", sa.Integer(), nullable=False),
        sa.Column("invoice_type", sa.String(length=32), nullable=False),
        sa.Column("carrier_code", sa.String(length=64), nullable=True),
        sa.Column("tax_id", sa.String(length=16), nullable=True),
        sa.Column("buyer_title", sa.String(length=256), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_number"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_checkout_order_branch_id", "checkout_order", ["branch_id"])
    op.create_index("ix_checkout_order_status", "checkout_order", ["status"])
    op.create_index("ix_checkout_order_customer_id", "checkout_order", ["customer_id"])
    op.create_index("ix_checkout_order_business_date", "checkout_order", ["business_date"])
    op.create_index("ix_checkout_order_created_at", "checkout_order", ["created_at"])

    op.create_table(
        "checkout_order_item",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("sku", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("scale", sa.String(length=32), nullable=False),
        sa.Column("brand", sa.String(length=128), nullable=False),
        sa.Column("original_price", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Integer(), nullable=False),
        sa.Column("cost_price", sa.Integer(), nullable=False),
        sa.Column("is_manual_price", sa.Boolean(), nullable=False),
        sa.Column("price_diff_reason", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("subtotal", sa.Integer(), nullable=False),
        sa.Column("points_discount_applied", sa.Boolean(), nullable=False),
        sa.Column("points_discount_amount", sa.Integer(), nullable=False),
        sa.Column("returned_quantity", sa.Integer(), nullable=False),
        sa.Column("pre_order_id", sa.String(length=64), nullable=True),
        sa.Column("pre_order_item_id", sa.String(length=64), nullable=True),
        sa.Column("original_order_id", sa.String(length=64), nullable=True),
        sa.Column("original_order_item_id", sa.String(length=64), nullable=True),
        sa.Column("restock", sa.Boolean(), nullable=True),
        sa.Column("return_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["checkout_order.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pre_order_id"], ["pre_order.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pre_order_item_id"], ["pre_order_item.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["original_order_item_id"], ["checkout_order_item.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", "line_no", name="uq_checkout_order_item_line"),
    )
    op.create_index("ix_checkout_order_item_order_id", "checkout_order_item", ["order_id"])
    op.create_index("ix_checkout_order_item_product_id", "checkout_order_item", ["product_id"])
    op.create_index(
        "ix_checkout_order_item_pre_order_item_id",
        "checkout_order_item",
        ["pre_order_item_id"],
    )
    op.create_index(
        "ix_checkout_order_item_original_order_item_id",
        "checkout_order_item",
        ["original_order_item_id"],
    )

    op.create_table(
        "checkout_payment",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("tendered_cash", sa.Integer(), nullable=True),
        sa.Column("change_amount", sa.Integer(), nullable=True),
        sa.Column("transaction_ref", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["checkout_order.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id", "line_no", name="uq_checkout_payment_line"),
    )
    op.create_index("ix_checkout_payment_order_id", "checkout_payment", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_checkout_payment_order_id", table_name="checkout_payment")
    op.drop_table("checkout_payment")
    op.drop_index("ix_checkout_order_item_original_order_item_id", table_name="checkout_order_item")
    op.drop_index("ix_checkout_order_item_pre_order_item_id", table_name="checkout_order_item")
    op.drop_index("ix_checkout_order_item_product_id", table_name="checkout_order_item")
    op.drop_index("ix_checkout_order_item_order_id", table_name="checkout_order_item")
    op.drop_table("checkout_order_item")
    op.drop_index("ix_checkout_order_created_at", table_name="checkout_order")
    op.drop_index("ix_checkout_order_business_date", table_name="checkout_order")
    op.drop_index("ix_checkout_order_customer_id", table_name="checkout_order")
    op.drop_index("ix_checkout_order_status", table_name="checkout_order")
    op.drop_index("ix_checkout_order_branch_id", table_name="checkout_order")
    op.drop_table("checkout_order")
    op.drop_index("ix_pre_order_item_product_id", table_name="pre_order_item")
    op.drop_index("ix_pre_order_item_pre_order_id", table_name="pre_order_item")
    op.drop_table("pre_order_item")
    op.drop_index("ix_pre_order_customer_id", table_name="pre_order")
    op.drop_table("pre_order")
