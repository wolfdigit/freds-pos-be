"""checkout soft-delete, payment fields, and required product id

Revision ID: d7c1e4a92b08
Revises: c3f8a1b04e55
Create Date: 2026-10-17 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7c1e4a92b08"
down_revision: Union[str, Sequence[str], None] = "c3f8a1b04e55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_fk_on(table: str, column: str) -> None:
    bind = op.get_bind()
    for fk in sa.inspect(bind).get_foreign_keys(table):
        if fk.get("constrained_columns") == [column] and fk.get("name"):
            op.drop_constraint(fk["name"], table, type_="foreignkey")


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return any(col["name"] == column for col in sa.inspect(bind).get_columns(table))


def _replace_product_fk(table: str, ondelete: str) -> None:
    _drop_fk_on(table, "product_id")
    op.create_foreign_key(
        f"{table}_product_id_fkey",
        table,
        "product",
        ["product_id"],
        ["id"],
        ondelete=ondelete,
    )


def upgrade() -> None:
    if not _has_column("product", "deleted"):
        op.add_column(
            "product",
            sa.Column(
                "deleted",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )

    bind = op.get_bind()
    null_product_ids = bind.execute(
        sa.text("SELECT COUNT(*) FROM checkout_order_item WHERE product_id IS NULL")
    ).scalar()
    if null_product_ids:
        raise RuntimeError(
            "checkout_order_item.product_id is NULL on existing rows; "
            "a sale line must keep its product id"
        )

    _drop_fk_on("checkout_order_item", "product_id")
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

    _replace_product_fk("product_stock", "RESTRICT")
    _replace_product_fk("product_pre_order_pending", "RESTRICT")

    if not _has_column("checkout_payment", "name"):
        op.add_column("checkout_payment", sa.Column("name", sa.String(length=128), nullable=True))
    if not _has_column("checkout_payment", "tendered_cash"):
        op.add_column("checkout_payment", sa.Column("tendered_cash", sa.Integer(), nullable=True))
    if not _has_column("checkout_payment", "change_amount"):
        op.add_column("checkout_payment", sa.Column("change_amount", sa.Integer(), nullable=True))
    if not _has_column("checkout_payment", "transaction_ref"):
        op.add_column(
            "checkout_payment",
            sa.Column("transaction_ref", sa.String(length=64), nullable=True),
        )

    op.execute(
        """
        UPDATE checkout_payment
        SET type = CASE
            WHEN type IN ('bank_transfer_ctbc', 'bank_transfer_ubot') THEN 'bank_transfer'
            WHEN type IN ('credit_card_physical', 'credit_card_online') THEN 'credit_card'
            ELSE type
        END
        """
    )
    op.execute(
        """
        UPDATE checkout_payment
        SET name = CASE type
            WHEN 'cash' THEN '現金'
            WHEN 'credit_card' THEN '信用卡'
            WHEN 'line_pay' THEN 'LINE Pay'
            WHEN 'bank_transfer' THEN '銀行轉帳'
            WHEN 'cod' THEN '貨到付款'
            ELSE type
        END
        WHERE name IS NULL OR name = ''
        """
    )
    op.alter_column("checkout_payment", "name", existing_type=sa.String(length=128), nullable=False)


def downgrade() -> None:
    op.alter_column("checkout_payment", "name", existing_type=sa.String(length=128), nullable=True)
    op.drop_column("checkout_payment", "transaction_ref")
    op.drop_column("checkout_payment", "change_amount")
    op.drop_column("checkout_payment", "tendered_cash")
    op.drop_column("checkout_payment", "name")

    _replace_product_fk("product_pre_order_pending", "CASCADE")
    _replace_product_fk("product_stock", "CASCADE")

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

    op.drop_column("product", "deleted")
