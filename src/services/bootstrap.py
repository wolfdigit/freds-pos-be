"""白名單還是空的時，依環境變數寫入第一位管理員。寫入後環境變數不再賦權。"""

from __future__ import annotations

import logging
import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.config import settings
from src.models.system import OAuthAccount

logger = logging.getLogger(__name__)

# 前端示範用信箱，不可當成真實授權。
DEMO_EMAILS = frozenset(
    {
        "fred@gmail.com",
        "admin@gmail.com",
        "clerk01@gmail.com",
        "clerk02@gmail.com",
        "staff@gmail.com",
    }
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def new_account_id() -> str:
    return f"acct-{uuid.uuid4().hex}"


def bootstrap_admin_if_empty(db: Session) -> None:
    raw_email = (settings.AUTH_BOOTSTRAP_ADMIN_EMAIL or "").strip().lower()
    if not raw_email:
        return
    if raw_email in DEMO_EMAILS or _EMAIL_RE.fullmatch(raw_email) is None:
        logger.error("Admin bootstrap refused: email is missing, invalid, or a frontend demo address")
        return
    existing = db.scalar(select(func.count()).select_from(OAuthAccount))
    if existing:
        return
    name = (settings.AUTH_BOOTSTRAP_ADMIN_NAME or "").strip() or raw_email
    if len(name) > 128:
        name = raw_email[:128]
    try:
        db.add(
            OAuthAccount(
                id=new_account_id(),
                email=raw_email,
                role="admin",
                name=name,
                note=None,
            )
        )
        db.commit()
    except IntegrityError:
        db.rollback()
    except Exception:
        db.rollback()
        logger.error("Admin bootstrap failed")
