from datetime import datetime, timezone
from typing import Dict, Any
from fastapi import APIRouter
from src.core.config import settings

router = APIRouter()


@router.get("/health", response_model=Dict[str, Any], summary="健康檢查端點")
def check_health() -> Dict[str, Any]:
    """
    回傳服務當前的健康狀態、專案名稱及時間戳記
    """
    return {
        "status": "ok",
        "project": settings.PROJECT_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": "development" if settings.DEBUG else "production",
    }
