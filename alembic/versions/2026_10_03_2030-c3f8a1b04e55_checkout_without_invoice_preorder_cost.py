"""drop invoice, cost, preorder, and extra payment fields from checkout

Revision ID: c3f8a1b04e55
Revises: b8e1d4f06a27
Create Date: 2026-10-03 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3f8a1b04e55"
down_revision: Union[str, Sequence[str], None] = "b8e1d4f06a27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_index_if_exists(table: str, name: str) -> None:
    bind = op.get_bind()
    names = {index["name"] for index in sa.inspect(bind).get_indexes(table)}
    if name in names:
        op.drop_index(name, table_name=table)


def _drop_fk_on(table: str, column: str) -> None:
    bind = op.get_bind()
    for fk in sa.inspect(bind).get_foreign_keys(table):
        if fk.get("constrained_columns") == [column] and fk.get("name"):
            op.drop_constraint(fk["name"], table, type_="foreignkey")


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return any(col["name"] == column for col in sa.inspect(bind).get_columns(table))


def upgrade() -> None:
    _drop_index_if_exists("checkout_order", "ix_checkout_order_invoice_number")
    for column in (
        "invoice_number",
        "invoice_type",
        "carrier_code",
        "tax_id",
        "buyer_title",
    ):
        if _has_column("checkout_order", column):
            op.drop_column("checkout_order", column)

    _drop_index_if_exists("checkout_order_item", "ix_checkout_order_item_pre_order_item_id")
    for column in ("pre_order_id", "pre_order_item_id", "cost_price"):
        if _has_column("checkout_order_item", column):
            _drop_fk_on("checkout_order_item", column)
            op.drop_column("checkout_order_item", column)

    if _has_column("checkout_order_item", "product_id"):
        _drop_fk_on("checkout_order_item", "product_id")
        op.alter_column(
            "checkout_order_item",
            "product_id",
            existing_type=sa.String(length=64),
            nullable=True,
        )
        op.create_foreign_key(
            "checkout_order_item_product_id_fkey",
            "checkout_order_item",
            "product",
            ["product_id"],
            ["id"],
            ondelete="SET NULL",
        )

    for column in ("name", "tendered_cash", "change_amount", "transaction_ref"):
        if _has_column("checkout_payment", column):
            op.drop_column("checkout_payment", column)


def downgrade() -> None:
    op.add_column(
        "checkout_payment",
        sa.Column("name", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column("checkout_payment", sa.Column("tendered_cash", sa.Integer(), nullable=True))
    op.add_column("checkout_payment", sa.Column("change_amount", sa.Integer(), nullable=True))
    op.add_column(
        "checkout_payment", sa.Column("transaction_ref", sa.String(length=64), nullable=True)
    )
    op.alter_column("checkout_payment", "name", server_default=None)

    op.drop_constraint(
        "checkout_order_item_product_id_fkey", "checkout_order_item", type_="foreignkey"
    )
    op.alter_column(
        "checkout_order_item",
        "product_id",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    op.create_foreign_key(
        "checkout_order_item_product_id_fkey",
        "checkout_order_item",
        "product",
        ["product_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "checkout_order_item",
        sa.Column("cost_price", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("checkout_order_item", "cost_price", server_default=None)
    op.add_column(
        "checkout_order_item", sa.Column("pre_order_id", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "checkout_order_item",
        sa.Column("pre_order_item_id", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "checkout_order_item_pre_order_id_fkey",
        "checkout_order_item",
        "pre_order",
        ["pre_order_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "checkout_order_item_pre_order_item_id_fkey",
        "checkout_order_item",
        "pre_order_item",
        ["pre_order_item_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_checkout_order_item_pre_order_item_id",
        "checkout_order_item",
        ["pre_order_item_id"],
    )

    op.add_column(
        "checkout_order",
        sa.Column("invoice_type", sa.String(length=32), nullable=False, server_default="none"),
    )
    op.alter_column("checkout_order", "invoice_type", server_default=None)
    op.add_column(
        "checkout_order", sa.Column("carrier_code", sa.String(length=64), nullable=True)
    )
    op.add_column("checkout_order", sa.Column("tax_id", sa.String(length=16), nullable=True))
    op.add_column(
        "checkout_order", sa.Column("buyer_title", sa.String(length=256), nullable=True)
    )
    op.add_column(
        "checkout_order",
        sa.Column("invoice_number", sa.String(length=64), nullable=True),
    )
    op.execute("UPDATE checkout_order SET invoice_number = id WHERE invoice_number IS NULL")
    op.alter_column("checkout_order", "invoice_number", nullable=False)
    op.create_index(
        "ix_checkout_order_invoice_number",
        "checkout_order",
        ["invoice_number"],
        unique=False,
    )
