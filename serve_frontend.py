import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Any, Tuple

# 預設設定：指向前端編譯後的靜態檔案目錄與監聽 Port
DIRECTORY: str = os.environ.get("STATIC_DIR", "../freds-pos-fe/dist")
PORT: int = int(os.environ.get("PORT", 3000))
HOST: str = os.environ.get("HOST", "0.0.0.0")


class SPAHandler(SimpleHTTPRequestHandler):
    """
    自訂 Request Handler：
    若請求的路徑找不到對應實體檔案或目錄，則 fallback 回傳 index.html，
    以支援 Vue / React 等 SPA 前端路由（History Mode）。
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def do_GET(self) -> None:
        # 取得請求對應於本地檔案系統的絕對路徑
        local_path: str = self.translate_path(self.path)

        # 若路徑不存在，Fallback 到 index.html 由前端路由接手處理
        if not os.path.exists(local_path):
            self.path = "/index.html"

        super().do_GET()


def run() -> None:
    if not os.path.exists(DIRECTORY):
        print(f"[警告] 目錄 '{DIRECTORY}' 不存在，請確認靜態檔案已放置或編譯完成。")

    server_address: Tuple[str, int] = (HOST, PORT)
    httpd = HTTPServer(server_address, SPAHandler)
    print(f"==================================================")
    print(f"  SPA HTTP Server 啟動中...")
    print(f"  - 託管目錄: {os.path.abspath(DIRECTORY)}")
    print(f"  - 伺服器網址: http://{HOST if HOST != '0.0.0.0' else 'localhost'}:{PORT}")
    print(f"==================================================")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] 伺服器已安全停止。")
        httpd.server_close()
        sys.exit(0)


if __name__ == "__main__":
    run()
