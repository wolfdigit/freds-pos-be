from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.core.config import settings
from src.api.v1.api import api_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if settings.DEBUG else None,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# 設定 CORS 中間件 (支援本地 5173/3000 以及 Vercel 部署網域 *.vercel.app)
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_origin_regex=r"https://.*\.vercel\.app",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# 掛載 API v1 路由前綴 (/api/v1)
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Root"])
def root_welcome():
    """
    後端服務根目錄歡迎訊息
    """
    response = {
        "message": f"Welcome to {settings.PROJECT_NAME} API Service",
        "health": f"{settings.API_V1_STR}/health",
        "environment": settings.ENVIRONMENT,
    }
    if settings.DEBUG:
        response["docs"] = "/docs"
        response["redoc"] = "/redoc"
        response["openapi"] = f"{settings.API_V1_STR}/openapi.json"
    return response
