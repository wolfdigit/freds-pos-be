from typing import Generator, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# 依賴注入 (Dependencies) 模組

# OAuth2 / JWT 預留 (開發階段先不啟用，未來開啟 PyJWT 或 python-jose 即可啟用)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_db() -> Generator:
    """
    資料庫 Session 依賴注入範例 (預留 - 稍後提醒建立 DB 時啟用)
    """
    try:
        db = None
        yield db
    finally:
        pass


def get_current_user_optional(token: Optional[str] = Depends(oauth2_scheme)) -> Optional[dict]:
    """
    JWT 身分驗證範例 (開發階段先回傳 Dummy User，未來啟用 JWT 解析驗證)
    """
    if not token:
        # 開發階段預設不強制要求 Token
        return {"id": 1, "username": "dev_user", "role": "admin"}
    
    # 未來在此加入 jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM]) 驗證邏輯
    return {"id": 1, "username": "dev_user", "role": "admin"}

