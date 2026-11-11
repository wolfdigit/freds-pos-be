import os
from typing import List, Optional, Tuple, Union

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _is_production(value: Optional[str]) -> bool:
    return (value or "").strip().lower() == "production"


# 支援環境切換：可透過 APP_ENV (例如 staging, production) 或直接指定 ENV_FILE；預設僅載入 .env
APP_ENV: str = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", ""))
ENV_FILE: Optional[str] = os.getenv("ENV_FILE")

_env_files: Tuple[str, ...]
if ENV_FILE:
    _env_files = (ENV_FILE,)
elif APP_ENV:
    # 載入順序：先載入通用 .env，若存在 .env.{APP_ENV} 則會覆寫同名設定
    _env_files = (".env", f".env.{APP_ENV}")
else:
    # 預設載入 .env
    _env_files = (".env",)


class Settings(BaseSettings):
    ENVIRONMENT: str = APP_ENV
    PROJECT_NAME: str = "Fred's POS Backend"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = True

    # 資料庫設定
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///./freds_pos.db"

    # 伺服器設定
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Google 登入。逗號可放多個 OAuth client id（正式、預覽、本地）。空值則登入一律拒絕。
    GOOGLE_CLIENT_ID: str = ""
    # 白名單還是空的時，寫入一筆管理員後就不再使用。不是永久權限。
    AUTH_BOOTSTRAP_ADMIN_EMAIL: str = ""
    AUTH_BOOTSTRAP_ADMIN_NAME: str = ""
    # 測試或預覽部署可跳過登入。預設關閉。正式環境一律忽略，見 skip_login_active。
    SKIP_LOGIN: bool = False
    # SKIP_LOGIN 生效時綁定的門市名稱。空白則用名稱排序後的第一間既有門市。
    SKIP_LOGIN_STORE: str = ""
    # Vercel 注入。與 ENVIRONMENT 一起擋住正式環境誤開 SKIP_LOGIN。
    VERCEL_ENV: str = ""

    # CORS 設定
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    @field_validator("SQLALCHEMY_DATABASE_URI", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: Union[str, None]) -> Union[str, None]:
        if isinstance(v, str):
            # 自動處理 Supabase 或雲端 PostgreSQL 預設提供的 postgres:// 格式
            if v.startswith("postgres://"):
                return v.replace("postgres://", "postgresql+psycopg2://", 1)
            elif v.startswith("postgresql://") and not v.startswith("postgresql+"):
                return v.replace("postgresql://", "postgresql+psycopg2://", 1)
        return v

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[str, List[str]]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    def google_client_ids(self) -> List[str]:
        return [part.strip() for part in self.GOOGLE_CLIENT_ID.split(",") if part.strip()]

    def skip_login_active(self) -> bool:
        """非正式環境且 SKIP_LOGIN 為真時，沒有有效 session 的請求改走測試身份。"""
        if not self.SKIP_LOGIN:
            return False
        if _is_production(self.ENVIRONMENT) or _is_production(self.VERCEL_ENV):
            return False
        return True

    model_config = SettingsConfigDict(
        env_file=_env_files,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )



settings = Settings()
