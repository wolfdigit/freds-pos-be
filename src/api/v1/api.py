from fastapi import APIRouter
from src.api.v1.endpoints import checkout, customers, health, inventory, preorders, products, system

api_router = APIRouter()

# 掛載健康檢查模組
api_router.include_router(health.router, tags=["Health"])

# 商品目錄
api_router.include_router(products.router, prefix="/products", tags=["Products"])

# 會員目錄
api_router.include_router(customers.router, prefix="/customers", tags=["Customers"])

# 結帳
api_router.include_router(checkout.router, prefix="/checkout", tags=["Checkout"])

# 庫存據點與調整
api_router.include_router(inventory.router, prefix="/inventory", tags=["Inventory"])

# 預購
api_router.include_router(preorders.router, prefix="/preorders", tags=["Preorders"])

# 門市與 OAuth 白名單
api_router.include_router(system.router, prefix="/system", tags=["System"])
