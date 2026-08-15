"""Entry point web app xem & so sánh giá heo hơi trên điện thoại/trình duyệt."""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app_factory import create_app  # noqa: E402
from routes.auth import bootstrap_admin_if_needed  # noqa: E402
from scheduler import start_scheduler  # noqa: E402
from waitress import serve  # noqa: E402

app = create_app()

if __name__ == "__main__":
    if sys.stdout is None or sys.stderr is None:
        # Chạy qua pythonw.exe (không có console): sys.stdout/sys.stderr là None,
        # print() sẽ crash ngay nếu không chuyển hướng ra file log trước.
        log_path = Path(__file__).resolve().parent / "server.log"
        log_file = open(log_path, "a", encoding="utf-8", buffering=1)
        sys.stdout = log_file
        sys.stderr = log_file
    elif sys.stdout.encoding is None or sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    print("=" * 50)
    bootstrap_admin_if_needed()
    print("=" * 50)
    start_scheduler()
    port = int(os.environ.get("PORT", 5000))
    print(f"Waitress dang chay tren cong {port}...")
    serve(app, host="0.0.0.0", port=port)
