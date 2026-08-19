# PIG_PRICE — ENTERPRISE REFACTOR CONTEXT

> Tài liệu checkpoint trước khi refactor kiến trúc.
> Mục đích: lưu lại context, kiến trúc hiện tại, kiến trúc mục tiêu và thứ tự triển khai để có thể tiếp tục công việc mà không mất định hướng.
> Ngày tạo: 2026-08-19

---

## 1. Repository

- GitHub: `duchop0974/pig_price`
- Branch hiện tại cần giữ nguyên làm baseline: `main`
- Branch phát triển kiến trúc: `refactor/enterprise-foundation`
- Framework: Flask
- Frontend: Jinja2 + Vanilla JavaScript
- CSS: một hệ thống CSS chung
- Database: SQLite thuần `sqlite3`
- ORM: Không sử dụng
- Deployment hiện tại: 1 máy Windows
- Kiến trúc hiện tại: Modular Monolith

## 2. Nguyên tắc bất di bất dịch

1. KHÔNG rewrite toàn bộ hệ thống.
2. KHÔNG đổi Flask/Jinja/Vanilla JS chỉ vì lý do kiến trúc.
3. KHÔNG chuyển PostgreSQL ngay.
4. KHÔNG xây microservices.
5. Migration ưu tiên additive-only:
   - `ALTER TABLE ADD COLUMN`
   - `CREATE TABLE IF NOT EXISTS`
   - Không thay đổi cấu trúc bảng đang chạy nếu chưa thật sự bắt buộc.
6. Không sửa trực tiếp `main` trong quá trình refactor.
7. Mỗi thay đổi lớn phải:
   - backup
   - thực hiện thay đổi nhỏ
   - test
   - verify
   - commit
8. Nếu thay đổi schema/kiến trúc/UI lớn: phải lập plan trước khi code.
9. Sau mỗi đợt thay đổi lớn phải cập nhật `docs/PROJECT_CONTEXT.md`.
10. Không để dữ liệu test tồn tại trong DB thật.

---

# 3. Bối cảnh nghiệp vụ

Hệ thống số hóa quy trình bán heo theo QT001/XTTH.

Phạm vi hiện tại:
- XH1
- XH2
- XH3

Mục tiêu:
- Chuẩn hóa quy trình bán heo.
- Kiểm soát thất thoát/gian lận.
- Xác định nguồn dữ liệu chuẩn.
- Theo dõi đầy đủ từ kế hoạch trại đến bán, xuất, cân và đối soát.
- Có audit/evidence để truy vết.

Nguyên tắc dữ liệu:
- Số lượng/trọng lượng thực tế phải căn cứ dữ liệu cân.
- Không tự ý sửa số liệu sau cân.
- Thay đổi phát sinh phải có biên bản/văn bản/evidence phù hợp.
- Data Freeze là cơ chế kiểm soát dữ liệu sau khi hoàn tất.

---

# 4. Actors

## Trang trại
- Lập kế hoạch bán BM01.
- Chuẩn bị heo.
- Phối hợp bàn giao.

## Sales
- Duyệt kế hoạch.
- Chốt đơn.
- Lập thông báo nhận heo.
- Nhận/bàn giao heo.
- Kiểm soát quá trình xuất.
- Đối soát.

## Logistics
- Nhận heo từ trại.
- Vận chuyển.
- Phối hợp bàn giao.

> Lưu ý: role/tài khoản Logistics chưa phải domain hoàn chỉnh trong hệ thống hiện tại.

## Accounting
- Kiểm tra chứng từ.
- Đối chiếu Sales/Trạm cân/Trại.
- Kiểm soát thanh toán.
- Kiểm soát hóa đơn.

## Leadership
- Chủ yếu view/report.

---

# 5. Kiến trúc hiện tại

```text
Browser
   |
   v
Flask Routes / Blueprints
   |
   v
webapp/data_access.py
   |
   +--> core.repositories
   |
   +--> core.services (hiện mới có một số service)
   |
   v
SQLite
```

Các thành phần chính:

```text
core/
├── db.py
├── permissions.py
├── audit_actions.py
├── repositories/
└── services/

webapp/
├── routes/
├── templates/
├── static/
├── data_access.py
└── extensions.py
```

---

# 6. Database hiện tại

Các nhóm bảng chính:

## Security / Identity

```text
users
roles
role_permissions
user_farms
```

## Master Data

```text
farms
zones
pig_types
customers
prices
```

## Sales Transaction

```text
sale_plans
sale_orders
sale_allocations
sale_deliveries
```

## Operational / Evidence

```text
weighing_records
incident_reports
media_proof
plan_reconciliations
audit_log
```

---

# 7. Quan hệ nghiệp vụ quan trọng

```text
Farm
  |
  +--> Sale Plan (BM01)
          |
          +--> Sale Allocation (BM02)
                    |
                    +--> Sale Order
                    |
                    +--> Sale Delivery
                    |
                    +--> Weighing
                    |
                    +--> Incident
                    |
                    +--> Reconciliation
                    |
                    +--> Media Evidence
```

Một kế hoạch trại có thể sinh nhiều dòng kế hoạch bán.

Không được phá quan hệ này trong quá trình refactor.

---

# 8. Kiến trúc mục tiêu

```text
Browser
   |
   v
Flask Routes
   |
   v
Application / Business Services
   |
   +--> Authorization / Data Scope
   +--> Validation
   +--> Transaction
   +--> Audit
   +--> Domain Rules
   |
   v
Repositories
   |
   v
Database
```

Nguyên tắc:

### Route
Chỉ xử lý HTTP:
- request
- response
- session
- redirect
- serialization

### Service
Xử lý use case/business:
- validation
- permission
- data scope
- state transition
- transaction
- audit

### Repository
Chỉ truy cập DB:
- SELECT
- INSERT
- UPDATE
- DELETE

---

# 9. Service Layer mục tiêu

Tạo dần:

```text
core/services/
├── plan_service.py
├── order_service.py
├── delivery_service.py
├── reconciliation_service.py
├── customer_service.py
└── authorization_service.py
```

Không tạo toàn bộ cùng lúc.

Thứ tự ưu tiên:

1. `plan_service.py`
2. `order_service.py`
3. `delivery_service.py`
4. `reconciliation_service.py`
5. `authorization_service.py`
6. `customer_service.py`

---

# 10. Authorization mục tiêu

Không chỉ:

```text
RBAC
```

mà:

```text
RBAC + Data Scope
```

Ví dụ:

```text
Farm XH1 user
    -> chỉ xem/sửa dữ liệu XH1 theo quyền

Farm XH2 user
    -> chỉ xem/sửa dữ liệu XH2 theo quyền

Sales
    -> xem các farm được phép

Leadership
    -> view toàn hệ thống

Admin
    -> quản trị toàn hệ thống
```

Nền tảng hiện tại đã có:
- `roles`
- `role_permissions`
- `user_farms`
- permission catalog

=> Không rewrite RBAC.

---

# 11. Transaction mục tiêu

Mỗi business action quan trọng phải được xử lý theo transaction.

Ví dụ:

```text
Create Delivery
    |
    +--> Validate
    |
    +--> Check Permission
    |
    +--> Check Farm Scope
    |
    +--> Check Plan/Order State
    |
    +--> Insert Delivery
    |
    +--> Update related data
    |
    +--> Write Audit
    |
    +--> Commit
```

Không để business action bị chia thành nhiều commit độc lập nếu các bước phải thành công đồng thời.

---

# 12. Audit / Evidence

Mọi nghiệp vụ quan trọng cần truy được:

```text
Who
What
When
Entity
Entity ID
Before
After
IP
Evidence
```

Đã có:
- `audit_log`
- `media_proof`

=> tiếp tục chuẩn hóa, không tạo hệ thống audit thứ hai.

---

# 13. Data Freeze

Mục tiêu:

```text
Business transaction completed
        |
        v
Admin / authorized user locks
        |
        v
Read-only
```

Sau khi lock:
- Không sửa tùy tiện.
- Không xóa tùy tiện.
- Nếu cần điều chỉnh phải có nghiệp vụ/biên bản phù hợp.
- Audit phải ghi nhận.

Không triển khai workflow engine trước khi Service Layer ổn định.

---

# 14. Frontend mục tiêu

Giữ công nghệ hiện tại.

Không rewrite frontend framework.

Chuẩn hóa theo hướng ERP / Operations Console:

```text
Navigation
Page Header
KPI
Filter
Table
Detail
Action Bar
Status
Exception
Mobile
```

Navigation nên nhóm:

```text
VẬN HÀNH
- Tổng quan
- Quy trình bán
- Kế hoạch trại
- Kế hoạch bán
- Xuất giao
- Đối soát

DỮ LIỆU
- Khách hàng
- Trang trại
- Loại heo
- Giá thị trường

BÁO CÁO
- Báo cáo
- Nhật ký

QUẢN TRỊ
- Tài khoản
- Vai trò & quyền
- Cấu hình
```

---

# 15. Control Tower mục tiêu

Sau khi backend ổn:

```text
Dashboard
   |
   v
Task Center
   |
   v
Exception Center
   |
   v
Entity Detail
   |
   v
Action
```

Task Center trả lời:
- Tôi cần làm gì?

Exception Center trả lời:
- Có vấn đề gì cần xử lý?

Dashboard trả lời:
- Doanh nghiệp đang vận hành thế nào?

---

# 16. Workflow Engine

Chưa triển khai ngay.

Kiến trúc tương lai:

```text
workflow_definitions
workflow_states
workflow_transitions
workflow_instances
workflow_history
```

Chỉ bắt đầu sau khi:
- Service Layer ổn.
- Transaction ổn.
- Authorization ổn.
- Test ổn.

Ưu tiên áp dụng workflow cho domain mới trước:
- KPI thưởng
- Vật tư
- Sự cố
- Đề nghị điều chỉnh

Không migrate toàn bộ sale workflow ngay.

---

# 17. Security Hardening

Ưu tiên P0:

1. CSRF protection.
2. Login rate limiting / brute-force protection.
3. Secret key từ environment/config.
4. Kiểm soát trusted proxy headers.
5. Session security.
6. Permission + data scope ở backend, không chỉ frontend.
7. Không lưu secret/password thật trong Git.

---

# 18. Database Hardening

Ưu tiên:

1. Kiểm tra `PRAGMA foreign_keys`.
2. Kiểm tra transaction behavior.
3. Kiểm tra WAL.
4. `busy_timeout`.
5. Chuẩn hóa connection lifecycle.
6. Backup strategy.
7. Restore test.
8. Index cho các truy vấn nghiệp vụ chính.

Chưa chuyển PostgreSQL.

---

# 19. Testing Strategy

Tạo dần:

```text
tests/
├── services/
├── repositories/
├── security/
└── integration/
```

Ưu tiên test:

```text
Plan
  -> create
  -> approve
  -> reject
  -> receive

Order
  -> create
  -> allocate
  -> modify
  -> lock

Delivery
  -> create
  -> validate
  -> reconcile

Authorization
  -> permission
  -> farm scope
```

Mục tiêu là có regression protection trước khi refactor sâu.

---

# 20. Roadmap

```text
STEP 0
Baseline
    |
    v
STEP 1
Database Hardening
    |
    v
STEP 2
Service Layer
    |
    v
STEP 3
Authorization + Data Scope
    |
    v
STEP 4
Transaction Standardization
    |
    v
STEP 5
Security Hardening
    |
    v
STEP 6
Automated Tests
    |
    v
STEP 7
Route Refactor
    |
    v
STEP 8
Enterprise UI
    |
    v
STEP 9
Task Center
    |
    v
STEP 10
Exception Center
    |
    v
STEP 11
Workflow Engine
    |
    v
STEP 12
PostgreSQL Readiness
```

---

# 21. STEP 0 — Baseline hiện tại

Không sửa code.

Thực hiện:

```bash
git status
git branch
git log -1 --oneline
```

Tạo branch:

```bash
git checkout -b refactor/enterprise-foundation
```

Backup database:

```powershell
Copy-Item data\gia_heo_hoi.db data\gia_heo_hoi.baseline.db
```

Nếu có media:

```powershell
Copy-Item data\media data\media.baseline -Recurse
```

Kiểm tra server vẫn chạy.

Kết quả cần ghi lại:

```text
Git status:
Git branch:
Git commit:
Server:
Database backup:
Media backup:
```

---

# 22. Quy trình làm việc từ nay

Mỗi bước sẽ theo đúng vòng:

```text
1. Tôi phân tích repo hiện tại
        ↓
2. Tôi nói rõ mục tiêu
        ↓
3. Tôi hướng dẫn bạn sửa từng file
        ↓
4. Bạn thực hiện
        ↓
5. Bạn gửi kết quả / lỗi
        ↓
6. Tôi kiểm tra
        ↓
7. Test
        ↓
8. Commit
        ↓
9. Sang bước tiếp theo
```

Không nhảy bước.

---

# 23. Trạng thái checkpoint

Khi hoàn thành mỗi bước, cập nhật:

```text
Current Step:
Completed:
Files changed:
DB changed:
Tests:
Commit:
Known issues:
Next Step:
```

Đây là phần quan trọng để sau này dù cuộc hội thoại bị gián đoạn vẫn có thể tiếp tục chính xác.

---

# 24. Điều KHÔNG được làm trong quá trình refactor

```text
KHÔNG:
- Rewrite toàn bộ
- Đổi framework
- Xóa bảng cũ tùy tiện
- Đổi tên column tùy tiện
- Xóa dữ liệu thật
- Commit trực tiếp vào main
- Thay đổi nhiều domain cùng lúc
- Refactor UI và DB trong cùng một bước nếu không cần
- Thêm workflow engine quá sớm
- Chuyển PostgreSQL khi chưa có nhu cầu
```

---

# 25. Mục tiêu cuối cùng

Hệ thống sau refactor phải đạt:

```text
Enterprise Web App
       |
       +-- Reliable Database
       +-- Clear Business Services
       +-- Strong Authorization
       +-- Farm Data Scope
       +-- Transaction Integrity
       +-- Audit Trail
       +-- Evidence
       +-- Data Freeze
       +-- Testable Architecture
       +-- ERP-grade UI
       +-- Task Center
       +-- Exception Center
       +-- Future Workflow Engine
       +-- PostgreSQL-ready
```

---

## CHECKPOINT — KHÔNG SỬA CODE TRƯỚC KHI HOÀN THÀNH

**Hiện tại chúng ta đang ở STEP 0.**

Chưa bắt đầu Step 1.

Sau khi bạn hoàn thành:

```text
git status
git branch
git log -1 --oneline
backup DB
backup media
```

hãy gửi tôi kết quả. Tôi sẽ tiếp tục hướng dẫn **STEP 1 — Database Hardening**, bắt đầu từ `core/db.py` và `get_connection()`; tôi sẽ chỉ cho bạn **từng dòng cần kiểm tra/sửa**, thay vì đưa một đống thay đổi cùng lúc.
