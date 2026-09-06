from typing import Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from src.core.config import settings
from src.core.exceptions import BusinessException
from src.api.v1.api import api_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if settings.DEBUG else None,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)


@app.exception_handler(BusinessException)
async def business_exception_handler(
    _request: Request, exc: BusinessException
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code.value if hasattr(exc.code, "value") else exc.code, "message": exc.message},
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
def root_welcome() -> Dict[str, str]:
    """
    後端服務根目錄歡迎訊息
    """
    response: Dict[str, str] = {
        "message": f"Welcome to {settings.PROJECT_NAME} API Service",
        "health": f"{settings.API_V1_STR}/health",
        "environment": settings.ENVIRONMENT,
    }
    if settings.DEBUG:
        response["docs"] = "/docs"
        response["redoc"] = "/redoc"
        response["openapi"] = f"{settings.API_V1_STR}/openapi.json"
    return response
