# 統一匯入 Base，並註冊 ORM 模型供 Base.metadata / Alembic 使用
from src.db.base_class import Base  # noqa: F401
from src.models.product import Product, ProductPreOrderPending, ProductStock  # noqa: F401
from src.models.customer import Customer  # noqa: F401
from src.models.checkout import CheckoutOrder, CheckoutOrderItem, CheckoutPayment  # noqa: F401
from src.models.preorder import PreOrder, PreOrderItem  # noqa: F401
from src.models.location import (  # noqa: F401
    StockAdjustmentLog,
    StockLocation,
    StockMovement,
    StockReceipt,
)
from src.models.system import OAuthAccount, StoreBranch  # noqa: F401
from src.models.auth import AuthSession  # noqa: F401
