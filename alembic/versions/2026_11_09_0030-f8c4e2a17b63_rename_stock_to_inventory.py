"""rename stock tables and columns to inventory

Revision ID: f8c4e2a17b63
Revises: e7b3c1d94a52
Create Date: 2026-11-09 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f8c4e2a17b63"
down_revision: Union[str, Sequence[str], None] = "e7b3c1d94a52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = (
    ("stock_location", "inventory_location"),
    ("product_stock", "product_inventory"),
    ("stock_receipt", "inventory_receipt"),
    ("stock_movement", "inventory_movement"),
    ("stock_adjustment_log", "inventory_adjustment_log"),
)

COLUMNS = (
    ("store_branch", "stock_location_id", "inventory_location_id"),
    ("store_branch", "returned_stock_location_id", "returned_inventory_location_id"),
    ("checkout_order_item", "stock_location_id", "inventory_location_id"),
    ("checkout_order_item", "stock_location_name", "inventory_location_name"),
)

CONSTRAINTS = (
    ("inventory_location", "stock_location_pkey", "inventory_location_pkey"),
    ("inventory_location", "uq_stock_location_name", "uq_inventory_location_name"),
    ("product_inventory", "product_stock_pkey", "product_inventory_pkey"),
    ("product_inventory", "product_stock_product_id_fkey", "product_inventory_product_id_fkey"),
    ("product_inventory", "fk_product_stock_location", "fk_product_inventory_location"),
    ("product_inventory", "uq_product_stock_product_location", "uq_product_inventory_product_location"),
    ("inventory_receipt", "stock_receipt_pkey", "inventory_receipt_pkey"),
    ("inventory_movement", "stock_movement_pkey", "inventory_movement_pkey"),
    ("inventory_adjustment_log", "stock_adjustment_log_pkey", "inventory_adjustment_log_pkey"),
    ("store_branch", "fk_store_branch_stock_location", "fk_store_branch_inventory_location"),
    ("store_branch", "fk_store_branch_returned_stock_location", "fk_store_branch_returned_inventory_location"),
)

INDEXES = (
    ("ix_product_stock_product_id", "ix_product_inventory_product_id"),
    ("ix_stock_movement_product_id", "ix_inventory_movement_product_id"),
    ("ix_stock_movement_location_id", "ix_inventory_movement_location_id"),
    ("ix_stock_movement_created_at", "ix_inventory_movement_created_at"),
    ("ix_stock_movement_source_id", "ix_inventory_movement_source_id"),
    ("ix_store_branch_stock_location_id", "ix_store_branch_inventory_location_id"),
    ("ix_store_branch_returned_stock_location_id", "ix_store_branch_returned_inventory_location_id"),
    ("uq_stock_location_name", "uq_inventory_location_name"),
    ("uq_product_stock_product_location", "uq_product_inventory_product_location"),
    ("stock_location_pkey", "inventory_location_pkey"),
    ("product_stock_pkey", "product_inventory_pkey"),
    ("stock_receipt_pkey", "inventory_receipt_pkey"),
    ("stock_movement_pkey", "inventory_movement_pkey"),
    ("stock_adjustment_log_pkey", "inventory_adjustment_log_pkey"),
)


def _rename_table(old: str, new: str) -> None:
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF to_regclass('public.{old}') IS NOT NULL THEN
                    ALTER TABLE "{old}" RENAME TO "{new}";
                END IF;
            END $$;
            """
        )
    )


def _rename_column(table: str, old: str, new: str) -> None:
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = '{table}' AND column_name = '{old}'
                ) THEN
                    ALTER TABLE "{table}" RENAME COLUMN "{old}" TO "{new}";
                END IF;
            END $$;
            """
        )
    )


def _rename_constraint(table: str, old: str, new: str) -> None:
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = '{old}' AND conrelid = '{table}'::regclass
                ) THEN
                    ALTER TABLE "{table}" RENAME CONSTRAINT "{old}" TO "{new}";
                END IF;
            END $$;
            """
        )
    )


def _rename_index(old: str, new: str) -> None:
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF to_regclass('public.{old}') IS NOT NULL THEN
                    ALTER INDEX "{old}" RENAME TO "{new}";
                END IF;
            END $$;
            """
        )
    )


def upgrade() -> None:
    for old, new in TABLES:
        _rename_table(old, new)
    for table, old, new in COLUMNS:
        _rename_column(table, old, new)
    for table, old, new in CONSTRAINTS:
        _rename_constraint(table, old, new)
    for old, new in INDEXES:
        _rename_index(old, new)


def downgrade() -> None:
    for old, new in reversed(INDEXES):
        _rename_index(new, old)
    for table, old, new in reversed(CONSTRAINTS):
        _rename_constraint(table, new, old)
    for table, old, new in reversed(COLUMNS):
        _rename_column(table, new, old)
    for old, new in reversed(TABLES):
        _rename_table(new, old)
