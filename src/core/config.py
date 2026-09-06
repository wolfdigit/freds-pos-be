import os
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 支援環境切換：可透過 APP_ENV (例如 staging, production) 或直接指定 ENV_FILE；預設僅載入 .env
APP_ENV = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", ""))
ENV_FILE = os.getenv("ENV_FILE")

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

    # CORS 設定
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    @field_validator("SQLALCHEMY_DATABASE_URI", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: Union[str, None]) -> str:
        if isinstance(v, str):
            # 自動處理 Supabase 或雲端 PostgreSQL 預設提供的 postgres:// 格式
            if v.startswith("postgres://"):
                return v.replace("postgres://", "postgresql+psycopg2://", 1)
            elif v.startswith("postgresql://") and not v.startswith("postgresql+"):
                return v.replace("postgresql://", "postgresql+psycopg2://", 1)
        return v

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    model_config = SettingsConfigDict(
        env_file=_env_files,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )



settings = Settings()
