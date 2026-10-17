import logging
import traceback
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from src.core.config import settings
from src.core.exceptions import BusinessException
from src.api.v1.api import api_router

logger = logging.getLogger(__name__)

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


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """未處理例外回 500。DEBUG 時把伺服器錯誤日誌一併放進 response。"""
    error_log = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.error(
        "Unhandled exception on %s %s\n%s",
        request.method,
        request.url.path,
        error_log,
    )
    content: Dict[str, Any] = {
        "code": "INTERNAL_SERVER_ERROR",
        "message": "Internal server error",
    }
    if settings.DEBUG:
        content["error_log"] = error_log
    return JSONResponse(status_code=500, content=content)

# 設定 CORS 中間件 (支援本地 5173/3000、LAN / WSL IP，以及 Vercel 部署網域 *.vercel.app)
# allow_private_network：Chrome / Edge 對 localhost、私有網段會先發 Private Network Access
# preflight（Access-Control-Request-Private-Network）。未開啟時 OPTIONS 會回 400
# "Disallowed CORS private-network"，實際 GET 搜尋永遠不會送出。
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_origin_regex=(
            r"https://.*\.vercel\.app"
            r"|https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?"
            r"|https?://.+\.localhost(:\d+)?"
            r"|https?://(10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
            r"|192\.168\.\d{1,3}\.\d{1,3}"
            r"|172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})(:\d+)?"
        ),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_private_network=True,
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
