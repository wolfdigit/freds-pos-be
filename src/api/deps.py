from typing import Any, Dict, Generator, Optional

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from src.db.session import SessionFactory

# 依賴注入 (Dependencies) 模組

# OAuth2 / JWT 預留 (開發階段先不啟用，未來開啟 PyJWT 或 python-jose 即可啟用)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_db() -> Generator[Session, None, None]:
    """
    資料庫 Session 依賴注入。
    確保每個 HTTP 請求開啟獨立 Session，並在請求結束後自動關閉釋放資源。
    """
    db = SessionFactory()
    try:
        yield db
    finally:
        db.close()


def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme),
) -> Dict[str, Any]:
    """
    JWT 身分驗證範例 (開發階段先回傳 Dummy User，未來啟用 JWT 解析驗證)
    """
    if not token:
        # 開發階段預設不強制要求 Token
        return {"id": 1, "username": "dev_user", "role": "admin"}

    # 未來在此加入 jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM]) 驗證邏輯
    return {"id": 1, "username": "dev_user", "role": "admin"}

