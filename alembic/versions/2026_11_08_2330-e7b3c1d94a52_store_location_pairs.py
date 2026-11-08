"""each store binds a normal location and a returned location

Revision ID: e7b3c1d94a52
Revises: d4f1a8c06e27
Create Date: 2026-11-08 23:30:00.000000

"""
from collections import defaultdict
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7b3c1d94a52"
down_revision: Union[str, Sequence[str], None] = "d4f1a8c06e27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RETURNED_LOCATION_ID = "e1a10005-0000-4000-8000-000000000005"


def upgrade() -> None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.text("SELECT 1 FROM stock_location WHERE id = :id").bindparams(id=RETURNED_LOCATION_ID)
    ).scalar()
    if not exists:
        bind.execute(
            sa.text(
                """
                INSERT INTO stock_location (id, name, icon, is_default, display_order, is_active)
                VALUES (:id, :name, :icon, :is_default, :display_order, :is_active)
                """
            ).bindparams(
                id=RETURNED_LOCATION_ID,
                name="退貨品",
                icon="↩️",
                is_default=False,
                display_order=5,
                is_active=True,
            )
        )
    op.add_column("store_branch", sa.Column("returned_stock_location_id", sa.String(length=64), nullable=True))
    op.execute(
        sa.text(
            "UPDATE store_branch SET returned_stock_location_id = :loc WHERE returned_stock_location_id IS NULL"
        ).bindparams(loc=RETURNED_LOCATION_ID)
    )
    with op.batch_alter_table("store_branch") as batch:
        batch.alter_column("returned_stock_location_id", existing_type=sa.String(length=64), nullable=False)
        batch.create_foreign_key(
            "fk_store_branch_returned_stock_location",
            "stock_location",
            ["returned_stock_location_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_index("ix_store_branch_stock_location_id", "store_branch", ["stock_location_id"])
    op.create_index(
        "ix_store_branch_returned_stock_location_id",
        "store_branch",
        ["returned_stock_location_id"],
    )

    returned_rows = bind.execute(
        sa.text("SELECT product_id, quantity FROM product_stock WHERE condition = 'returned'")
    ).fetchall()
    totals: dict[str, int] = defaultdict(int)
    for product_id, quantity in returned_rows:
        totals[product_id] += quantity
    for product_id, quantity in totals.items():
        existing = bind.execute(
            sa.text(
                """
                SELECT quantity FROM product_stock
                WHERE product_id = :product_id AND location = :location AND condition = 'normal'
                """
            ).bindparams(product_id=product_id, location=RETURNED_LOCATION_ID)
        ).fetchone()
        if existing is None:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO product_stock (product_id, location, condition, location_name, quantity)
                    VALUES (:product_id, :location, 'normal', '退貨品', :quantity)
                    """
                ).bindparams(product_id=product_id, location=RETURNED_LOCATION_ID, quantity=quantity)
            )
        else:
            bind.execute(
                sa.text(
                    """
                    UPDATE product_stock
                    SET quantity = quantity + :quantity
                    WHERE product_id = :product_id AND location = :location AND condition = 'normal'
                    """
                ).bindparams(product_id=product_id, location=RETURNED_LOCATION_ID, quantity=quantity)
            )
    op.execute(sa.text("DELETE FROM product_stock WHERE condition = 'returned'"))

    with op.batch_alter_table("product_stock") as batch:
        batch.drop_constraint("uq_product_stock_product_location_condition", type_="unique")
        batch.drop_column("condition")
        batch.create_unique_constraint("uq_product_stock_product_location", ["product_id", "location"])

    with op.batch_alter_table("stock_movement") as batch:
        batch.add_column(sa.Column("sku", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("name", sa.String(length=256), nullable=True))
    inspector = sa.inspect(bind)
    if "stock_receipt_item" in inspector.get_table_names():
        items = bind.execute(
            sa.text("SELECT receipt_id, product_id, sku, name FROM stock_receipt_item")
        ).fetchall()
        for receipt_id, product_id, sku, name in items:
            bind.execute(
                sa.text(
                    """
                    UPDATE stock_movement
                    SET sku = :sku, name = :name
                    WHERE source_id = :receipt_id AND product_id = :product_id
                      AND type = 'receipt' AND sku IS NULL
                    """
                ).bindparams(sku=sku, name=name, receipt_id=receipt_id, product_id=product_id)
            )
        op.drop_table("stock_receipt_item")
    with op.batch_alter_table("stock_movement") as batch:
        batch.drop_column("condition")
        batch.create_index("ix_stock_movement_source_id", ["source_id"])

    with op.batch_alter_table("checkout_order_item") as batch:
        batch.drop_column("stock_condition")
    with op.batch_alter_table("stock_location") as batch:
        batch.drop_column("is_active")


def downgrade() -> None:
    with op.batch_alter_table("stock_location") as batch:
        batch.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    with op.batch_alter_table("checkout_order_item") as batch:
        batch.add_column(sa.Column("stock_condition", sa.String(length=16), nullable=True))
    with op.batch_alter_table("stock_movement") as batch:
        batch.drop_index("ix_stock_movement_source_id")
        batch.add_column(sa.Column("condition", sa.String(length=16), nullable=False, server_default="normal"))
        batch.drop_column("sku")
        batch.drop_column("name")
    op.create_table(
        "stock_receipt_item",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("receipt_id", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("sku", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
    )
    with op.batch_alter_table("product_stock") as batch:
        batch.add_column(sa.Column("condition", sa.String(length=16), nullable=False, server_default="normal"))
        batch.drop_constraint("uq_product_stock_product_location", type_="unique")
        batch.create_unique_constraint(
            "uq_product_stock_product_location_condition",
            ["product_id", "location", "condition"],
        )
    op.drop_index("ix_store_branch_returned_stock_location_id", table_name="store_branch")
    op.drop_index("ix_store_branch_stock_location_id", table_name="store_branch")
    with op.batch_alter_table("store_branch") as batch:
        batch.drop_constraint("fk_store_branch_returned_stock_location", type_="foreignkey")
        batch.drop_column("returned_stock_location_id")
