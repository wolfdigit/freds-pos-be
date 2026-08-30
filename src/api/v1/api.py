from fastapi import APIRouter
from src.api.v1.endpoints import health

api_router = APIRouter()

# 掛載健康檢查模組
api_router.include_router(health.router, tags=["Health"])

# 未來若有新模組 (例如 products, orders, auth)，在此進行引進與掛載：
# from src.api.v1.endpoints import products
# api_router.include_router(products.router, prefix="/products", tags=["Products"])
