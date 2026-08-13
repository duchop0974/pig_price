# Ghi chú học tập — Dự án pig_price

## Bước 1: Module & Import trong Python

**Module là gì:** một file `.py` bất kỳ chính là một module — bạn có thể `import` nó từ file khác để dùng lại các hàm/biến bên trong, thay vì copy-paste code.

**Python tìm module ở đâu — `sys.path`:** khi gặp `import tên_module`, Python duyệt qua một danh sách thư mục gọi là `sys.path`, theo thứ tự, và dùng file khớp đầu tiên tìm thấy. Danh sách này gồm:

1. Thư mục chứa file `.py` mà bạn **trực tiếp chạy** bằng lệnh `python ...` (không phải "thư mục gốc dự án" một cách trừu tượng — mà là thư mục vật lý chứa file khởi động).
2. Các thư mục cài đặt package (`site-packages`...).
3. Vài nơi khác theo cấu hình.

**Hệ quả thực tế:** nếu bạn chạy `python webapp/app.py` (hoặc `cd webapp && python app.py`), `sys.path` mặc định chỉ chứa `webapp/`, **không chứa** thư mục cha `pig_price/`. Vì vậy `import pig_sources` (đang nằm ở `pig_price/`) sẽ thất bại với `ModuleNotFoundError` nếu không có gì đặc biệt.

**Cách dự án này giải quyết — vá `sys.path` thủ công** (trong `webapp/app.py`):
```python
BASE_DIR = Path(__file__).resolve().parent.parent  # lùi từ app.py -> webapp/ -> pig_price/
sys.path.insert(0, str(BASE_DIR))                   # chèn pig_price/ vào đầu danh sách tìm kiếm
import pig_sources as src                            # giờ Python tìm thấy
```
`__file__` = đường dẫn file hiện tại; mỗi `.parent` lùi lên một cấp thư mục.

**Cách "chuẩn" hơn cho dự án lớn — package hoá:** biến `pig_price/` thành một package Python (qua `__init__.py` hoặc `pyproject.toml`), rồi dùng import tương đối (`from .. import pig_sources`). Cấu trúc quan hệ giữa các thư mục được khai báo **một lần**, không phải tự tính đường dẫn thủ công ở từng file — tránh lỗi khi di chuyển file hoặc khi nhiều module chèn `sys.path` theo thứ tự khác nhau.

**Bài học chuyển giao:** `sys.path.insert` là giải pháp "đủ dùng" hợp lý cho script/dự án nhỏ chạy trực tiếp; package hoá là chuẩn mực khi dự án lớn dần. Đây là một đánh đổi thực tế (pragmatism vs. chuẩn mực), không phải đúng/sai tuyệt đối.

## Kiến trúc tổng thể dự án (bối cảnh)

3 lớp rõ rệt:
- `pig_price_scraper.py` — entry point CLI, chỉ argparse + điều phối.
- `pig_sources.py` — logic domain dùng chung: fetch, parse, chuẩn hoá, lưu SQLite, export Excel. Cả CLI lẫn webapp cùng import module này.
- `webapp/app.py` — lớp giao diện Flask, gọi lại đúng các hàm trong `pig_sources.py`.

Nguyên tắc: tách "logic nghiệp vụ" khỏi "giao diện truy cập" — thêm giao diện mới (bot, API khác...) chỉ cần import `pig_sources`, không viết lại parser.

---
*Bước tiếp theo: đọc `pig_sources.py` — các hàm fetch/parse/chuẩn hoá dữ liệu.*
