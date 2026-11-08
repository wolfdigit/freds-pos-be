"""Store-to-location foreign key failures.

PostgreSQL names this constraint ``fk_store_branch_stock_location`` and reports
SQLSTATE 23503. SQLite, with foreign keys enabled, reports only
``FOREIGN KEY constraint failed`` and ignores ``FOR UPDATE``. Callers that
write more than ``store_branch`` must not treat that unnamed error as this
constraint unless a store row actually references the location.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.system import StoreBranch

STORE_LOCATION_FK = "fk_store_branch_stock_location"


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
    if name == STORE_LOCATION_FK and sqlstate in (None, "23503"):
        return True
    return sqlstate == "23503" and STORE_LOCATION_FK in text


def is_unnamed_sqlite_fk(exc: IntegrityError) -> bool:
    sqlstate, name, text = _parts(exc)
    return sqlstate is None and name is None and "FOREIGN KEY constraint failed" in text


def is_store_location_fk_violation(exc: IntegrityError) -> bool:
    """True for this mapping FK.

    SQLite cannot name the constraint. This is safe for a statement that only
    inserts or updates ``store_branch``, which has no other foreign key.
    """

    return is_named_store_location_fk(exc) or is_unnamed_sqlite_fk(exc)


def location_is_mapped(db: Session, location_id: str) -> bool:
    return (
        db.scalar(
            select(StoreBranch.name).where(StoreBranch.stock_location_id == location_id).limit(1)
        )
        is not None
    )


def location_delete_blocked_by_store_fk(db: Session, exc: IntegrityError, location_id: str) -> bool:
    """Roll back the delete, then say whether this error is the mapping FK.

    A named PostgreSQL violation is enough. SQLite's unnamed foreign-key error
    is accepted only when a store references the location after the rollback,
    so a different foreign key in the same delete is left untouched.
    """

    db.rollback()
    if is_named_store_location_fk(exc):
        return True
    return is_unnamed_sqlite_fk(exc) and location_is_mapped(db, location_id)
