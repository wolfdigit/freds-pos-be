# 統一匯入 Base，並註冊 ORM 模型供 Base.metadata / Alembic 使用
from src.db.base_class import Base  # noqa: F401
from src.models.product import Product, ProductPreOrderPending, ProductStock  # noqa: F401
