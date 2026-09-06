from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool
from src.core.config import settings

is_sqlite: bool = settings.SQLALCHEMY_DATABASE_URI.startswith("sqlite")

engine: Engine
if is_sqlite:
    engine = create_engine(
        settings.SQLALCHEMY_DATABASE_URI,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
        echo=settings.DEBUG,
    )
else:
    # Serverless 專用資料庫連線設定：使用 NullPool，避免連線數耗盡與連線凍結
    engine = create_engine(
        settings.SQLALCHEMY_DATABASE_URI,
        poolclass=NullPool,
        echo=settings.DEBUG,
    )

# 資料庫 Session 工廠
SessionFactory: sessionmaker[Session] = sessionmaker(
    autocommit=False, autoflush=False, bind=engine
)

