from fastapi import APIRouter
<<<<<<< HEAD
from src.api.v1.endpoints import health, products, customers, checkout
=======
from src.api.v1.endpoints import health, products, customers
>>>>>>> 27ae09e34fd9ceac91a9c305e35364c13394d52e

api_router = APIRouter()

# 掛載健康檢查模組
api_router.include_router(health.router, tags=["Health"])

# 商品目錄
api_router.include_router(products.router, prefix="/products", tags=["Products"])

# 會員目錄
api_router.include_router(customers.router, prefix="/customers", tags=["Customers"])
<<<<<<< HEAD

# 結帳
api_router.include_router(checkout.router, prefix="/checkout", tags=["Checkout"])
=======
>>>>>>> 27ae09e34fd9ceac91a9c305e35364c13394d52e
