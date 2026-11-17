"""migrate legacy checkout payment types to frontend values

Revision ID: 8be3027059d9
Revises: f8c4e2a17b63
Create Date: 2026-11-17 10:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8be3027059d9"
down_revision: Union[str, Sequence[str], None] = "f8c4e2a17b63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Plain UPDATE statements so the same SQL can run on Postgres and SQLite.
UPGRADE_STATEMENTS = (
    """
    UPDATE checkout_payment
    SET type = 'credit_card_physical',
        name = CASE WHEN name = '信用卡' THEN '信用卡(實體)' ELSE name END
    WHERE type = 'credit_card'
    """,
    """
    UPDATE checkout_payment
    SET type = 'bank_transfer_ctbc',
        name = CASE WHEN name = '銀行轉帳' THEN '轉帳(中信)' ELSE name END
    WHERE type = 'bank_transfer'
    """,
)


def apply_upgrade(execute) -> None:
    for statement in UPGRADE_STATEMENTS:
        execute(sa.text(statement))


def upgrade() -> None:
    apply_upgrade(op.execute)


def downgrade() -> None:
    # Reverse mapping is lossy: credit_card_physical and bank_transfer_ctbc
    # may have been written by new checkouts, not only by this migration, and
    # the current application already accepts those detailed values.
    pass
