# Backend

後端專案服務與相關工具說明。

## 靜態網頁伺服器 (Static Web Server)

專案提供 `serve_frontend.py`，使用 Python 內建的 `http.server` 託管已編譯的前端靜態資源（支援 Vue/React 等 SPA 前端路由 Fallback 機制，避免頁面重整出現 404）。

### 啟動方式

```bash
# 預設託管 ../fe/dist，監聽 port 3000
python3 serve_frontend.py
```

### 常用參數（透過環境變數）

```bash
# 自訂靜態檔案路徑
STATIC_DIR=../fe/dist python3 serve_frontend.py

# 自訂 Port
PORT=8080 python3 serve_frontend.py
```

---

## Python 開發環境設定 (venv)

為了避免套件衝突並確保使用正確的版本，建議使用 Python 內建的 `venv` 建立獨立虛擬環境：

### 1. 建立虛擬環境

```bash
# 在 be 目錄下建立 .venv 虛擬環境
python3 -m venv .venv
```

### 2. 啟用虛擬環境

- **Linux / macOS / WSL**：
  ```bash
  source .venv/bin/activate
  ```
- **Windows (Command Prompt / PowerShell)**：
  ```powershell
  .venv\Scripts\activate
  ```

> 啟用後，終端機提示字元前會出現 `(.venv)`，此時所有的 `pip install` 都會安裝於此隔離環境內。

### 3. 安裝與管理套件

```bash
# 確保 pip 為最新版
pip install --upgrade pip

# 依據 requirements.txt 安裝指定版本的套件
pip install -r requirements.txt
```

若有新增或更新套件，記得將版本鎖定寫入設定檔：

```bash
# 將當前環境安裝的套件版本輸出到 requirements.txt
pip freeze > requirements.txt
```

### 4. 退出虛擬環境

```bash
deactivate
```

---

## FastAPI 後端服務 (FastAPI Service)

後端主要 API 服務位於 `src/` 目錄，基於 FastAPI 框架打造，支援自動 OpenAPI 文件產生、Pydantic 資料驗證以及模組化路由。

### 目錄結構

```
src/
├── main.py                 # 應用程式入口點 (FastAPI App, CORS, Root 端點)
├── core/                   # 核心配置 (環境變數設定 Settings, 資料庫連線介面)
│   ├── config.py
│   └── database.py
├── api/                    # 路由層
│   ├── deps.py             # 依賴注入 (Dependencies)
│   └── v1/                 # API v1 版本路由
│       ├── api.py          # 路由彙整
│       └── endpoints/      # 端點邏輯 (health, products, orders 等)
├── schemas/                # Pydantic 資料驗證模型 (Request/Response DTO)
│   ├── common.py
│   ├── product.py
│   └── order.py
├── models/                 # ORM / 資料實體模型 (保留未來資料庫擴充)
└── services/               # 業務邏輯層
    └── product_service.py
```

### 啟動 FastAPI 服務

在啟動虛擬環境並安裝 `requirements.txt` 後，可透過以下方式啟動：

```bash
# 方式一：使用本地輔助腳本（自動啟用 .venv 並啟動熱重載）
./run_backend.sh

# 方式二：直接使用 uvicorn 標準指令
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### 互動式 API 文件 (Swagger & ReDoc)

服務啟動後，可直接在瀏覽器造訪：
- **Swagger UI**：[http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**：[http://localhost:8000/redoc](http://localhost:8000/redoc)
- **健康檢查**：[http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)
