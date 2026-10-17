"""inventory locations, system tables, required customer phone

Revision ID: a1c6e8d04f11
Revises: f3b9d2e18a44
Create Date: 2026-10-17 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1c6e8d04f11"
down_revision: Union[str, Sequence[str], None] = "f3b9d2e18a44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LOCATIONS = (
    ("e1a10001-0000-4000-8000-000000000001", "門市現貨", "🏪", True, 1, "store"),
    ("e1a10002-0000-4000-8000-000000000002", "後方倉庫", "📦", False, 2, "warehouse"),
    ("e1a10003-0000-4000-8000-000000000003", "公司總倉", "🏢", False, 3, "company"),
    ("e1a10004-0000-4000-8000-000000000004", "調度暫存", "🚚", False, 4, "other"),
)


def upgrade() -> None:
    op.create_table(
        "stock_location",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("icon", sa.String(length=16), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    location_table = sa.table(
        "stock_location",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("icon", sa.String),
        sa.column("is_default", sa.Boolean),
        sa.column("display_order", sa.Integer),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        location_table,
        [
            {
                "id": loc_id,
                "name": name,
                "icon": icon,
                "is_default": is_default,
                "display_order": order,
                "is_active": True,
            }
            for loc_id, name, icon, is_default, order, _legacy in LOCATIONS
        ],
    )

    op.alter_column(
        "product_stock",
        "location",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
    for loc_id, name, _icon, _default, _order, legacy in LOCATIONS:
        op.execute(
            sa.text(
                "UPDATE product_stock SET location = :loc_id, location_name = :name "
                "WHERE location = :legacy"
            ).bindparams(loc_id=loc_id, name=name, legacy=legacy)
        )

    op.create_table(
        "stock_adjustment_log",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("operator_name", sa.String(length=128), nullable=False),
        sa.Column("items_json", sa.Text(), nullable=False),
        sa.Column("total_qty_change", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_table(
        "store_branch",
        sa.Column("name", sa.String(length=128), primary_key=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.bulk_insert(
        sa.table(
            "store_branch",
            sa.column("name", sa.String),
            sa.column("is_default", sa.Boolean),
        ),
        [
            {"name": "台北旗艦店", "is_default": True},
            {"name": "官網", "is_default": False},
        ],
    )
    op.create_table(
        "oauth_account",
        sa.Column("email", sa.String(length=256), primary_key=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.add_column("pre_order", sa.Column("operator_name", sa.String(length=128), nullable=True))

    bind = op.get_bind()
    missing_phone = bind.execute(
        sa.text("SELECT count(*) FROM customer WHERE phone IS NULL OR btrim(phone) = ''")
    ).scalar()
    if missing_phone:
        raise RuntimeError("customer.phone 仍有空白，無法改成必填")
    op.alter_column("customer", "phone", existing_type=sa.String(length=64), nullable=False)


def downgrade() -> None:
    op.alter_column("customer", "phone", existing_type=sa.String(length=64), nullable=True)
    op.drop_column("pre_order", "operator_name")
    op.drop_table("oauth_account")
    op.drop_table("store_branch")
    op.drop_table("stock_adjustment_log")
    for loc_id, _name, _icon, _default, _order, legacy in LOCATIONS:
        op.execute(
            sa.text("UPDATE product_stock SET location = :legacy WHERE location = :loc_id").bindparams(
                legacy=legacy, loc_id=loc_id
            )
        )
    op.alter_column(
        "product_stock",
        "location",
        existing_type=sa.String(length=64),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
    op.drop_table("stock_location")
