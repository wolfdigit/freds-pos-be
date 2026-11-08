"""Store-to-location foreign key failures.

PostgreSQL names the constraints and reports SQLSTATE 23503. SQLite, with
foreign keys enabled, reports only ``FOREIGN KEY constraint failed`` and
ignores ``FOR UPDATE``. A statement that also writes other tables must not
treat that unnamed error as a store mapping unless a store still references
the location after rollback.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.system import StoreBranch

STORE_LOCATION_FKS = (
    "fk_store_branch_stock_location",
    "fk_store_branch_returned_stock_location",
)


def _parts(exc: IntegrityError) -> tuple[str | None, str | None, str]:
    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
    diag = getattr(orig, "diag", None)
    name = getattr(diag, "constraint_name", None) if diag is not None else None
    if name is None:
        name = getattr(orig, "constraint_name", None)
    text = str(orig if orig is not None else exc)
    return sqlstate, name, text


def is_named_store_location_fk(exc: IntegrityError) -> bool:
    sqlstate, name, text = _parts(exc)
    if name in STORE_LOCATION_FKS and sqlstate in (None, "23503"):
        return True
    return sqlstate == "23503" and any(constraint in text for constraint in STORE_LOCATION_FKS)


def is_unnamed_sqlite_fk(exc: IntegrityError) -> bool:
    sqlstate, name, text = _parts(exc)
    return sqlstate is None and name is None and "FOREIGN KEY constraint failed" in text


def is_store_location_fk_violation(exc: IntegrityError) -> bool:
    """True when this statement only writes ``store_branch``.

    That table's foreign keys both point at ``stock_location``.
    """

    return is_named_store_location_fk(exc) or is_unnamed_sqlite_fk(exc)


def location_is_mapped(db: Session, location_id: str) -> bool:
    return (
        db.scalar(
            select(StoreBranch.name)
            .where(
                or_(
                    StoreBranch.stock_location_id == location_id,
                    StoreBranch.returned_stock_location_id == location_id,
                )
            )
            .limit(1)
        )
        is not None
    )


def location_delete_blocked_by_store_fk(db: Session, exc: IntegrityError, location_id: str) -> bool:
    """Roll back, then say whether this error is a store mapping foreign key."""

    db.rollback()
    if is_named_store_location_fk(exc):
        return True
    return is_unnamed_sqlite_fk(exc) and location_is_mapped(db, location_id)
