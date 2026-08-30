#!/usr/bin/env bash
set -e

# 切換至腳本所在目錄
cd "$(dirname "$0")"

# 若本地存在虛擬環境則自動啟用
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# 預設連線參數（可透過環境變數覆寫）
HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8000}

echo "=================================================="
echo "  FastAPI 本地開發服務啟動中..."
echo "  - 伺服器網址: http://${HOST}:${PORT}"
echo "  - API 文件 (Swagger): http://localhost:${PORT}/docs"
echo "=================================================="

# 使用 exec 直接將行程替換為 uvicorn，確保 Ctrl+C / 系統信號能直接中斷服務釋放 Port
exec uvicorn src.main:app --host "$HOST" --port "$PORT" --reload
