# CLAUDE.md

Hướng dẫn cho Claude Code khi làm việc trong repo này.

## Đọc trước khi làm bất kỳ việc gì

**Luôn đọc `docs/PROJECT_CONTEXT.md` trước** khi bắt đầu — tài liệu này tổng
hợp bối cảnh nghiệp vụ (quy trình QT001/XTTH), kiến trúc hệ thống hiện tại,
quy ước code, và các đề xuất thiết kế mở rộng đang cân nhắc. Đọc file này
trước khi tự dò lại code từ đầu — nó được cập nhật sau mỗi đợt thay đổi lớn
(schema, kiến trúc, redesign UI...) chính vì mục đích đó.

Nếu `docs/PROJECT_CONTEXT.md` có vẻ không khớp với code thực tế (VD nhắc tới
hàm/bảng không còn tồn tại), **tin vào code hiện tại**, không tin tài liệu —
rồi cập nhật lại tài liệu cho khớp.

## Tóm tắt nhanh (chi tiết đầy đủ ở docs/PROJECT_CONTEXT.md)

- Flask app, Jinja2 templates + vanilla JS (`webapp/static/js/*.js`, không
  framework frontend) + `webapp/static/css/style.css` (1 file CSS chung).
- SQLite thuần (`sqlite3`, không ORM), 1 file DB tại `data/gia_heo_hoi.db`.
- Kiến trúc: `core/` (repositories + business logic, framework-agnostic) —
  `webapp/routes/` (Flask blueprints, 1 file/domain: `plans.py`, `admin.py`,
  `auth.py`, `prices.py`...).
- RBAC động qua bảng `roles`/`role_permissions` + `core/permissions.py`
  (catalog permission key) — **không** hardcode role trong route, quản lý
  qua `/admin/permissions`.
- `sale_plans` (kế hoạch trại, BM01, chỉ nguồn cung) và `sale_allocations`
  (kế hoạch bán, BM02, giá/khách hàng/doanh thu) là 2 bảng tách riêng —
  1 kế hoạch trại → N kế hoạch bán.

## Quy ước làm việc đã thống nhất với người dùng

- **Migration kiểu "thuần cộng thêm"**: thêm cột/bảng mới
  (`ALTER TABLE ADD COLUMN`, `CREATE TABLE IF NOT EXISTS`), không đổi cấu
  trúc bảng đang chạy trừ khi thật sự bắt buộc.
- **Backup/restore DB khi verify trên dữ liệu thật**: trước khi chạy
  migration hoặc test có ghi dữ liệu thật vào `data/gia_heo_hoi.db`, `cp` 1
  bản backup có timestamp; sau khi verify xong thì restore lại — không để
  sót dữ liệu test trong DB thật.
- **Plan Mode cho mọi thay đổi không nhỏ**: các thay đổi liên quan schema,
  kiến trúc, hoặc redesign UI nhiều file nên đi qua Plan Mode (khám phá →
  hỏi lại các điểm rẽ nhánh thật sự → viết plan → xin duyệt) trước khi sửa
  code, thay vì code thẳng.
- Sau mỗi đợt thay đổi lớn (schema/kiến trúc/redesign UI), **cập nhật lại
  `docs/PROJECT_CONTEXT.md`** cho khớp trạng thái mới — đây là tài liệu sống,
  không phải chụp nhanh 1 lần.
