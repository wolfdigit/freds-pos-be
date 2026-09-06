import re
from typing import Any

from sqlalchemy.orm import DeclarativeBase, declared_attr


class Base(DeclarativeBase):
    """
    SQLAlchemy 2.0 DeclarativeBase 基底類別。
    自動將 CamelCase 類別名稱轉換為 snake_case 的資料表名稱。
    例如: Product -> product, OrderItem -> order_item
    """

    id: Any

    @declared_attr.directive
    def __tablename__(cls) -> str:
        name: str = cls.__name__
        return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
