# pig_price — Giá heo hơi

Web app theo dõi & so sánh giá heo hơi Việt Nam từ 5 nguồn (nongnghiepmoitruong.vn,
vietnambiz.vn, greenfeed.com.vn, vinanet.vn, baovanhoa.vn), kèm tính năng "kế hoạch
xuất bán" cho trang trại.

## Chạy nhanh

1. Cài Python 3.11+ (đã test với 3.13).
2. Chạy `lay_gia_heo.bat` — menu tương tác: xem giá, backfill dữ liệu cũ, bật/tắt
   web server, tạo link Internet (tunnel), xem log truy cập. Lần đầu chạy sẽ tự
   `pip install -r requirements.txt`.
3. Hoặc chạy trực tiếp:
   - `start_server.bat` — khởi động web server nền (không hiện cửa sổ) trên cổng 5000.
   - `restart_server.bat` — dừng rồi khởi động lại (dùng sau khi sửa code/đổi mật khẩu).
   - `stop_server.bat` — dừng server.
   - `start_tunnel.bat` / `stop_tunnel.bat` — bật/tắt Cloudflare Tunnel để xem từ
     Internet (cần cài `cloudflared`; link đổi mỗi lần chạy lại).

Truy cập `http://localhost:5000` trên máy, hoặc `http://<tên máy>:5000` từ máy khác
cùng mạng WiFi.

## Đăng nhập & tài khoản

Mỗi người dùng có tài khoản riêng (tên đăng nhập + mật khẩu), không còn dùng
chung 1 mật khẩu như trước. Lần đầu chạy server (chưa có tài khoản nào), hệ
thống tự tạo 1 tài khoản admin mặc định (`admin`), mật khẩu ngẫu nhiên ghi vào
`webapp/password.txt` (không commit vào git) — đăng nhập bằng tài khoản này rồi
vào mục **Tài khoản** (chỉ admin thấy) để tạo tài khoản cho từng người và đổi
mật khẩu. Admin cũng có thể khoá/mở lại tài khoản hoặc đặt lại mật khẩu cho
người khác tại đó.

Mục **Nhật ký** (chỉ admin) ghi lại lịch sử hoạt động: đăng nhập, tạo/khoá tài
khoản, tạo/sửa/xoá kế hoạch xuất bán — kèm ai làm, lúc nào, từ IP nào. Mỗi kế
hoạch xuất bán cũng hiển thị "Tạo bởi" ngay trên thẻ.

## Dữ liệu

Toàn bộ giá được lưu trong SQLite tại `data/gia_heo_hoi.db` (bảng `prices`; thêm
`farms`/`zones`/`sale_plans` cho kế hoạch xuất bán; `users`/`audit_log` cho tài
khoản và nhật ký hoạt động). Server tự động cập nhật giá mới mỗi ngày lúc 7:00
sáng (APScheduler chạy nền trong tiến trình web).

## Cấu trúc dự án

```
pig_price/
├── core/                       # logic domain dùng chung cho CLI và web
│   ├── db.py                    # kết nối SQLite, schema, migration nhẹ (thêm cột/bảng nếu chưa có)
│   ├── scrapers/                 # cào dữ liệu — 1 module/nguồn (5 nguồn) + BaseScraper dùng chung
│   │   ├── base.py                # interface chung: fetch_latest/fetch_by_date + helper pick_latest/find_by_date
│   │   ├── nongnghiepmoitruong.py, vietnambiz.py, greenfeed.py, vinanet.py, baovanhoa.py
│   │   ├── registry.py             # điều phối theo nguồn: fetch_latest_all(), fetch_by_date_all()
│   │   └── utils.py                # fetch(), normalize_province(), parse_3col_table()...
│   ├── repositories/              # CRUD thuần sqlite3 (không ORM)
│   │   ├── prices_repo.py, farms_repo.py, sale_plans_repo.py, users_repo.py, audit_repo.py
│   └── services/                   # tính toán nghiệp vụ: pivot giá theo nguồn, export Excel
│       ├── price_service.py, export_service.py
├── pig_price_scraper.py        # CLI: xem giá, backfill, export — import trực tiếp từ core/
├── webapp/
│   ├── app.py                    # entry point mỏng: tạo app, bootstrap admin, chạy scheduler
│   ├── app_factory.py             # create_app(): đăng ký blueprint, secret key, ProxyFix
│   ├── extensions.py               # db_lock, đường dẫn file, log_access()/log_audit() dùng chung
│   ├── data_access.py               # bọc db_lock quanh core.repositories cho routes gọi
│   ├── scheduler.py                  # cron 7h sáng tự động cập nhật giá
│   ├── routes/                        # Flask Blueprint theo domain
│   │   ├── auth.py                     # đăng nhập/đăng xuất, guard yêu cầu đăng nhập, bootstrap admin
│   │   ├── admin.py                     # quản lý tài khoản + xem nhật ký hoạt động (chỉ admin)
│   │   ├── prices.py                     # trang giá + API (today/date/refresh/history/export)
│   │   └── plans.py                       # trang kế hoạch xuất bán + API (farms/zones/plans)
│   ├── templates/
│   │   ├── base.html                       # layout dùng chung (header/nav/footer), các trang kế thừa
│   │   └── index.html, plans.html, login.html, admin_users.html, admin_audit.html
│   └── static/
│       ├── js/common.js                    # el(), fmtPrice(), dmyToIso()/fmtIsoDate() dùng chung
│       ├── js/app.js, js/plan.js, js/admin_users.js
│       ├── css/style.css
│       └── img/logo-icon.png, img/logo-full.png
├── data/gia_heo_hoi.db          # SQLite, không commit thay đổi runtime
└── *.bat                        # Script chạy trên Windows (không cần Docker/CI) — không path nào đổi
```

Dự án chạy trên 1 máy Windows, không có CI — cố tình giữ đơn giản: không ORM,
không test suite, không container hoá, không đóng gói Docker.
