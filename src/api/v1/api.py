from fastapi import APIRouter
from src.api.v1.endpoints import health, products, customers

api_router = APIRouter()

# 掛載健康檢查模組
api_router.include_router(health.router, tags=["Health"])

# 商品目錄
api_router.include_router(products.router, prefix="/products", tags=["Products"])

# 會員目錄
api_router.include_router(customers.router, prefix="/customers", tags=["Customers"])
