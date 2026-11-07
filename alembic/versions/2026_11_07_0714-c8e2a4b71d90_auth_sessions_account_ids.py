"""auth sessions, stable oauth account ids, wider checkout branch id

Revision ID: c8e2a4b71d90
Revises: b7d2a91c05e6
Create Date: 2026-11-07 07:14:00.000000

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


revision: str = "c8e2a4b71d90"
down_revision: Union[str, Sequence[str], None] = "b7d2a91c05e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("oauth_account", sa.Column("id", sa.String(length=64), nullable=True))
    bind = op.get_bind()
    emails = bind.execute(sa.text("SELECT email FROM oauth_account")).fetchall()
    for (email,) in emails:
        bind.execute(
            sa.text("UPDATE oauth_account SET id = :id WHERE email = :email"),
            {"id": f"acct-{uuid.uuid4().hex}", "email": email},
        )
    with op.batch_alter_table("oauth_account") as batch:
        batch.alter_column("id", existing_type=sa.String(length=64), nullable=False)
    op.create_index("uq_oauth_account_id", "oauth_account", ["id"], unique=True)
    op.create_table(
        "auth_session",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=256), nullable=False),
        sa.Column("store_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_auth_session_account_id", "auth_session", ["account_id"])
    op.create_index("ix_auth_session_email", "auth_session", ["email"])
    with op.batch_alter_table("checkout_order") as batch:
        batch.alter_column(
            "branch_id",
            existing_type=sa.String(length=64),
            type_=sa.String(length=128),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("checkout_order") as batch:
        batch.alter_column(
            "branch_id",
            existing_type=sa.String(length=128),
            type_=sa.String(length=64),
            existing_nullable=False,
        )
    op.drop_index("ix_auth_session_email", table_name="auth_session")
    op.drop_index("ix_auth_session_account_id", table_name="auth_session")
    op.drop_table("auth_session")
    op.drop_index("uq_oauth_account_id", table_name="oauth_account")
    with op.batch_alter_table("oauth_account") as batch:
        batch.drop_column("id")
