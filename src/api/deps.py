from typing import Any, Dict, Generator, Optional

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from src.db.session import SessionFactory

# 依賴注入 (Dependencies) 模組

# OAuth2 / JWT 預留 (開發階段先不啟用，未來開啟 PyJWT 或 python-jose 即可啟用)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

# 登入尚未完成。結帳把這位使用者的 id / name 寫成收銀員快照。
# 真正的員工登入上線後，只替換這個回傳值，不要再從結帳 body 收收銀員。
DEMO_CASHIER: Dict[str, Any] = {
    "id": "staff-001",
    "name": "店長 Fred",
    "username": "fred",
    "role": "admin",
}


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
    _token: Optional[str] = Depends(oauth2_scheme),
) -> Dict[str, Any]:
    """
    目前操作的員工。結帳的收銀員快照只讀這裡的 `id` 與 `name`。
    登入尚未完成，有沒有 token 都回傳示範收銀員。之後改成 jwt.decode。
    """
    return DEMO_CASHIER

