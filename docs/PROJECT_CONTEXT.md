# Bối cảnh & thiết kế dự án — Quản lý bán heo (pig_price)

> Tài liệu này tổng hợp nghiệp vụ + kiến trúc + đề xuất thiết kế mở rộng, dùng để
> trao đổi với AI khác (Gemini...) hoặc người mới tham gia dự án. Khác với
> `README.md` (hướng dẫn vận hành/cài đặt), file này tập trung vào **tại sao** hệ
> thống được thiết kế như vậy và **những gì đang được cân nhắc mở rộng**.

---

## I. Bối cảnh nghiệp vụ

### 1. Căn cứ & phạm vi

Hệ thống số hoá quy trình bán heo theo **Quyết định số 52/QĐ-XTG** ("Quy trình bán
heo QT001/XTTH", ban hành 20/07/2026), áp dụng cho 3 trang trại **XH1, XH2, XH3**.

Mục tiêu cốt lõi: chuẩn hoá toàn bộ hoạt động bán heo, ngăn ngừa rủi ro thất
thoát/gian lận, và xác định nguồn dữ liệu chuẩn để các bên đối chiếu.

**Nguyên tắc dữ liệu bất di bất dịch**: toàn bộ số lượng, trọng lượng heo phải
căn cứ theo kết quả cân thực tế. Nghiêm cấm tự ý sửa đổi/điều chỉnh/làm sai lệch
số liệu sau khi cân. Mọi thay đổi phát sinh phải có biên bản hoặc văn bản xác
nhận của các bên liên quan. → Đây là lý do thiết kế **Data Freeze** (mục III.5)
và bắt buộc **Media Proof** (mục III.3) cho các bước cân.

### 2. Actors & luồng nghiệp vụ

| Actor | Trách nhiệm chính |
|---|---|
| **Trang trại (XH1/XH2/XH3)** | Lập kế hoạch bán (BM01) gửi Phòng bán hàng; chuẩn bị heo; ký Biên bản bàn giao heo (BM04) với Hậu cần. |
| **Phòng Bán hàng (Sales)** | Duyệt kế hoạch, chốt đơn với khách; lập thông báo nhận heo (BM03) gửi Trại; nhận heo từ Hậu cần, kiểm đếm giao lên xe khách, ký BM04; **kiểm soát chặt rủi ro cân xe không tải trước khi nhận heo tại bàn cân** (đặc biệt XH2, XH3); cuối ngày lập BM05 (tổng hợp giao nhận trong ngày). |
| **Hậu cần (Logistics)** | Nhận heo từ Trại, vận chuyển ra khu giao nhận, ký BM04 với Trại và Sales. |
| **Kế toán** | Kế toán Thanh Hoá kiểm tra tính hợp lệ bộ chứng từ, đối chiếu Sales/Trạm cân/Trại; giao ngày nghỉ/lễ thì yêu cầu khách thanh toán trước; chỉ lập hoá đơn khi hồ sơ đầy đủ hợp lệ. Kế toán Tập đoàn ký phát hành hoá đơn điện tử sau khi Thanh Hoá lập. |

### 3. Ràng buộc hệ thống hiện tại

1. **Thiết bị**: ưu tiên giao diện mobile cho các bộ phận hiện trường (Trại,
   Sales, Hậu cần).
2. **Trạm cân**: chưa liên kết API trực tiếp — cần UX nhập mã phiếu cân hoặc
   chụp ảnh màn hình cân thay thế.
3. **Thanh toán**: chưa tích hợp API Ngân hàng — cần luồng "duyệt thanh toán thủ
   công" cho Kế toán.
4. **Xử lý sự cố**: chưa có form biên bản điều chỉnh điện tử phức tạp — cần
   "Báo cáo sự cố nhanh" bắt buộc kèm ảnh/video khi có bù đắp tổn thất.
5. **Data Freeze**: dữ liệu Đơn hàng/Lô heo phải "khoá vĩnh viễn" (read-only)
   với mọi tài khoản ngay khi Admin bấm khoá.

### 4. Yêu cầu khả năng mở rộng

Hệ thống tương lai sẽ tích hợp thêm các quy trình khác (xét duyệt KPI thưởng
cho Trang trại, quản lý vật tư...). Do đó:
- CSDL nên theo hướng Modular Monolith (tách Core dùng chung khỏi Feature module).
- Luồng phê duyệt nên theo mô hình **State Machine chung** (tái sử dụng cho
  quy trình khác), không hardcode riêng từng domain.
- RBAC và Media/Proof phải là **generic component** dùng chung.

---

## II. Trạng thái hệ thống hiện tại (đã build)

*(Xem chi tiết lịch sử ở `memory/project_sales_workflow.md` trong workspace Claude.)*

- **4 role**: `farm` / `sales` / `accounting` / `admin` (+ `leadership` view-only),
  RBAC **động** qua bảng `roles` + `role_permissions` + `core/permissions.py`
  (catalog permission key), quản lý tại `/admin/permissions` — không hardcode
  role trong route.
- **`sale_plans`** = kế hoạch trại (BM01, chỉ nguồn cung: farm/zone/shed/lot/
  pig_type/quantity, `received_quantity` tracking, approval `pending_approval→
  approved/rejected`). **Không có giá, không khách hàng.**
- **`sale_allocations`** = kế hoạch bán (BM02, Phòng bán hàng "nhặt" số lượng
  từ 1 `sale_plans` đã duyệt): giá bán, khách hàng, liên hệ, giao hàng, doanh
  thu, hoá đơn. 1 kế hoạch trại → N kế hoạch bán.
- **`customers`**, **`farms`/`zones`**, **`pig_types`**, **`audit_log`**
  (generic theo `entity_type`/`entity_id`) đã có sẵn.
- **Chủ động bỏ qua trước đây** (nay đang mở lại để thiết kế ở mục III):
  không có role/tài khoản Hậu cần trong hệ thống; không có state machine
  tổng quát (chỉ có `status` hardcode); không có bảng Media/Proof chung;
  không có Data Freeze; không có "báo cáo sự cố nhanh".
- Dự án chạy 1 máy Windows, không CI/Docker, thuần `sqlite3` không ORM,
  migration kiểu **"thuần cộng thêm"** (additive-only: thêm cột/bảng, không
  đổi cấu trúc bảng đang chạy trừ khi bắt buộc).

### 5. Giao diện (UI/UX) — đã redesign (2026-08-16)

Toàn bộ phần dưới đây là thay đổi **thuần frontend** (template/CSS/JS tĩnh) —
không đổi API, DB schema, hay business logic. Bối cảnh: người dùng phản ánh
qua ảnh chụp màn hình là giao diện "vỡ layout"/"rối", yêu cầu sửa lại theo
hướng phần mềm quản trị nội bộ (ERP), không phải landing page.

**Sửa lỗi layout nền tảng** (`webapp/static/css/style.css`, `base.html`):
- `.topbar-nav` (11 mục điều hướng) tràn khỏi khung `.topbar-inner`
  (`max-width: 960px`) ở **mọi** kích thước màn hình, vì nút hamburger cũ chỉ
  kích hoạt dưới 640px trong khi menu cần ~1247px mới đủ chỗ xếp 1 hàng ngang
  → sửa bằng cách cho hamburger (dropdown ẩn/hiện) hoạt động ở mọi kích
  thước, bỏ hẳn kiểu "menu ngang cố định + wrap".
- `h2.section-title` (tiêu đề mỗi trang) trước đó không có style dạng card
  (không nền/viền/bo góc) — nằm trơ trên nền xám của `<body>`, lệch hẳn phong
  cách với các `.card` bên dưới → thêm style card cho nhất quán.
- `.plan-actions` (nhóm nút hành động trên thẻ) thiếu `flex-wrap` nên tràn ra
  ngoài card khi có nhiều nút → đã thêm; nút `.btn-danger` cuối nhóm tách
  xuống dòng riêng để phân biệt hành động phá huỷ khỏi hành động thường.

**Redesign phân cấp thẻ `.plan-card`** (component dùng chung cho Kế hoạch
trại + Kế hoạch bán, `webapp/static/js/plan.js` + `allocation.js`): trước đó
là khối phẳng 6-9 dòng `label: value` cùng cỡ chữ không phân cấp; thẻ đơn
hàng còn lồng nguyên thẻ "dòng" (line) con bên trong (hộp trong hộp). Đã
thêm `.plan-meta-grid` (lưới 2 cột, label/value xếp dọc từng ô — gọn hơn hẳn
so với 1 cột dài), `.plan-card-section` (khối phụ có nhãn riêng, VD "Thông
tin bán hàng"/"Doanh thu" — tách khỏi thông tin chính), và ẩn mặc định các
dòng con của đơn hàng sau 1 nút toggle tóm tắt ("N dòng · X con ▾").

**Redesign trang Kế hoạch bán (`/ke-hoach-ban`) thành giao diện ERP nội bộ**
(`webapp/templates/allocations.html` + `allocation.js`, brief chi tiết từ
người dùng): trang cũ là 5 khối rời rạc không thể hiện luồng thao tác thật.
Tổ chức lại đúng quy trình "Xem nguồn cung → Chọn → Nhập số lượng/giá → Thêm
vào đơn → Kiểm tra → Tạo đơn":
- **Tổng quan nguồn cung**: summary card theo loại heo, tái dùng nguyên
  `.kpi-tile` đã có ở dashboard (không viết CSS card mới).
- **Nguồn cung có thể bán**: bảng 9 cột (Trại/Loại heo/Kế hoạch/Ngày/Được
  duyệt/Đã bán/Còn lại/Trạng thái/nút) + filter client-side (Trại, Loại heo,
  khoảng ngày, Trạng thái, search) — lọc thuần JS vì `GET /api/plans` vốn đã
  trả về toàn bộ danh sách (không filter server-side), không cần sửa backend.
  Nguồn hết hàng vẫn hiển thị (mờ đi, badge "Đã bán hết") thay vì ẩn hẳn như
  trước.
- **Banner "Đã chọn nguồn"**: đồng bộ 2 chiều với `<select id="line-sale-plan">`
  — select vẫn là nguồn sự thật duy nhất cho `sale_plan_id` khi submit, banner
  chỉ là lớp hiển thị đẹp hơn phủ lên trên.
- **Validation số lượng real-time**: so với `remaining_quantity`, có trừ luôn
  số lượng đã "đặt chỗ" trong giỏ nháp cho cùng 1 nguồn (nếu người dùng thêm
  2 dòng cùng 1 kế hoạch trại trước khi tạo đơn) để không lách được giới hạn.
- **Format giá**: ô giá đổi từ `type="number"` sang `type="text"` + mask dấu
  chấm ngăn cách hàng nghìn khi gõ (`formatPriceInputValue`/
  `parsePriceInputValue`, thêm vào `common.js` để dùng lại được ở chỗ khác),
  parse lại đúng số thực khi submit — đã verify qua request thật gửi đúng số
  nguyên (`62000`), không phải chuỗi có dấu chấm.
- **Đơn hàng đang tạo**: đổi từ danh sách card sang bảng, có dòng "Tổng số
  lượng", nút "Tạo đơn hàng" là primary action nổi bật nhất khu vực.
- **Danh sách đơn hàng**: theo quyết định của người dùng (đơn hàng có nhiều
  badge/nút theo quyền/dòng con — ép vào 1 hàng bảng sẽ mất thông tin), **giữ
  nguyên** dạng thẻ vừa redesign ở trên, không tách tab.

Đã verify end-to-end bằng dữ liệu thật trên `data/gia_heo_hoi.db` theo đúng
protocol backup/restore của dự án (xem `memory/feedback_dev_workflow.md`
trong workspace Claude): tạo 1 đơn hàng thật (`201 CREATED`), xác nhận số
lượng/giá lưu đúng, sau đó xoá + restore DB về trạng thái sạch, không để lại
dữ liệu test.

### 6. Design System + Sales UX — Phase 0 & Phase 1 (2026-08-16)

Thực hiện theo brief "Web Design & UX Improvement Brief" của người dùng
(định hướng ERP/Operations console, triển khai theo phase, không rewrite).
Thuần frontend (CSS/JS/template), không đổi API/DB/business logic.

**Phase 0 — Design System Foundation**: mở rộng token trong `:root` của
`style.css` (spacing scale `--space-*`, font-size scale `--text-*`,
`--info`, z-index) và thêm các component CSS còn thiếu:
`.badge`/`.badge-*`, `.alert`, `.empty-state`, `.spinner`/`.loading-overlay`,
`.toast`/`.toast-container`, `.timeline`, `.stepper`/`.stepper-step`
(done/current/exception/locked), `.breadcrumb`, `.page-header`,
`.confirm-modal`. Thêm `webapp/static/js/core/`: `api.js` (fetch wrapper,
**chưa dùng**), `toast.js` (`showToast()`), `status.js` (`STATUS_CONFIG` +
`renderBadge()`), `modal.js` (`confirmModal()` + `promptModal()`, thay
`window.confirm()/alert()/prompt()`). `base.html` có mount `.toast-container`
+ block `breadcrumb`/`page_header` (trang nào chưa dùng thì rỗng).
`common.js` **giữ nguyên không đổi** — không biến thành shim cho
`core/formatters.js` vì nó được include riêng lẻ ở 8 template khác nhau,
gộp `const` trùng tên sẽ vỡ; `core/formatters.js` tồn tại song song, chưa
trang nào dùng.

⚠️ **Lưu ý kỹ thuật quan trọng về thứ tự script**: 4 file `core/*.js` được
include trong `base.html` **không có `defer`** (dù bản đầu Phase 0 có
`defer` — đã sửa lại khi Phase 1 phát hiện lỗi). Lý do: `{% block scripts
%}` (chứa `common.js` + `plan.js`/`allocation.js`, không `defer`) nằm sau
trong HTML source; nếu core script có `defer` mà page script thì không,
trình duyệt chạy **page script trước** (non-deferred chạy ngay khi parser
gặp, deferred chạy sau khi parse xong toàn trang) → `renderBadge`/
`confirmModal`/`showToast` sẽ là `undefined` khi trang gọi tới, kể cả sau
khi 1 `await fetch()` đã resolve (đã kiểm chứng thực nghiệm lỗi này trước
khi sửa). Nếu sau này thêm script mới vào `core/`, **không thêm `defer`**
trừ khi toàn bộ `{% block scripts %}` của mọi trang cũng chuyển sang
`defer` đồng bộ.

**Phase 1 Batch 1 — Kế hoạch trại** (`plans.html` + `plan.js`): thêm
`.breadcrumb`/`.page-header` thay `h2.section-title`; thêm mini stepper 3
bước (Chờ duyệt → Đã duyệt → Đã nhận) trên mỗi `.plan-card` qua
`planStepperHtml()`, dùng `.stepper` có sẵn; `planStatusBadge()` chuyển
sang gọi `renderBadge()`/dùng `.badge-*` cho phần trạng thái tĩnh (giữ
nguyên logic đếm ngày/phân bổ hết dạng badge thuần vì đó là giá trị động);
5 chỗ `alert()/confirm()/prompt()` (duyệt, từ chối, ghi nhận thực nhận, xoá,
vô hiệu hoá) chuyển hết sang `confirmModal()`/`promptModal()`/`showToast()`.

**Phase 1 Batch 2 — Kế hoạch bán/Đơn hàng** (`allocations.html` +
`allocation.js`): tương tự — breadcrumb/page-header; stepper 4 bước
(Đang xử lý → Chốt bán hàng → Đã bán → Doanh thu ghi nhận) trên mỗi order
card qua `orderStepperHtml()` — **mỗi bước tự tính "done" độc lập** theo dữ
liệu riêng (có `customer_name`? có `status==='done'`? có `paid_amount`?)
thay vì ép tuần tự cứng, vì "Chốt bán hàng" và "Đã bán" có thể xảy ra không
theo đúng thứ tự đó ở thực tế (backend không ép buộc) — chỉ bước đầu tiên
chưa xong được đánh dấu `is-current`, `disabled`/`cancelled` chèn
`is-exception` đúng tại vị trí còn dang dở; `orderStatusBadge()` và badge
khả dụng nguồn cung chuyển sang `renderBadge()`/`.badge-*`; 7 chỗ
`alert()/confirm()/prompt()` chuyển hết sang modal/toast mới (3 `prompt()`
sửa dòng hàng giữ nguyên hành vi tuần tự 3 bước, không gộp 1 modal nhiều
field). 2 bảng `.admin-table` (nguồn cung, giỏ hàng) thêm class
`.admin-table-responsive` + `data-label` trên từng `<td>` (JS render) +
`@media (max-width: 640px)` mới trong `style.css` chuyển bảng thành card
label/value trên mobile — chỉ áp dụng 2 bảng này qua class riêng, không ảnh
hưởng `.admin-table` ở các trang admin khác.

Chưa làm trong Phase 1: chưa migrate `fetch()` sang `core/api.js`, chưa tái
cấu trúc nav thành nhóm theo brief §8. Verify: syntax-check JS (`node -c`)
+ parse-check Jinja (`Environment.get_template`) qua toàn bộ; verify trực
quan qua trang scratch tạm (nạp đúng `style.css`/`core/*.js` thật, xoá sau
khi xong) vì phiên làm việc không có sẵn tài khoản đăng nhập hợp lệ để
click-through trực tiếp trên `/ke-hoach`/`/ke-hoach-ban` — **cần người
dùng tự verify luồng nghiệp vụ đầy đủ trên trình duyệt thật** (tạo/duyệt/
từ chối kế hoạch, tạo/chốt/mark-done đơn hàng, responsive mobile thật) khi
có tài khoản.

**2026-08-16, sau Phase 1: compact hoá card "Danh sách kế hoạch trại"**
(`plan.js`'s `renderPlans()`, theo wireframe chi tiết người dùng cung cấp
sau khi thấy card quá cao trên mobile): card cũ hiện 8+ dòng label/value +
stepper luôn hiện + tối đa 4 nút full-size xếp chồng. Đổi thành 1 layout
compact **dùng chung cho mọi kích thước màn hình** (không tách desktop/
mobile riêng — quyết định của người dùng, đơn giản/ít rủi ro hơn):
- Header 2 dòng: tên trại/khu + badge đếm ngày (`planDeadlineBadge()`, tách
  ra từ `planStatusBadge()` cũ — logic y hệt, đổi `"Đã qua N ngày"` →
  `"Quá hạn N ngày"` theo yêu cầu), rồi 1 dòng trạng thái nổi bật
  (`renderBadge(plan.status)`, lần đầu dùng tới key `approved` trong
  `STATUS_CONFIG` vốn có sẵn từ Phase 0 nhưng chưa ai gọi).
- Stepper 3 bước (`planStepperHtml()`, giữ nguyên hàm) **chuyển vào khối
  "Chi tiết" ẩn mặc định** thay vì luôn hiện — cùng chuồng/lô, thực nhận.
  Toggle dùng lại đúng CSS `.order-lines-toggle`/`.toggle-caret` (đang
  dùng ở `allocation.js`, đủ generic để tái dùng), nhưng nội dung bọc
  trong class mới `.detail-collapse` (không dùng `.order-lines` — class
  đó có `display:grid` cho nhiều card con, không hợp bố cục hàng đơn giản
  ở đây).
- "Đã phân bổ" đổi từ text `"X / Y con (còn Z)"` sang progress bar
  (`.progress-bar`/`.progress-bar-fill`, class mới) — % tính từ đúng 2
  field có sẵn (`allocated_quantity`/`quantity`), đạt 100% thì fill xanh
  `.is-complete` + badge nhỏ "Hết" cạnh label (thay cho badge "Đã phân bổ
  hết" đứng riêng trước đây).
- 4 nút hành động cũ → 1 primary action full-width (`.btn-block`, class
  mới) chọn theo thứ tự ưu tiên bước-tiếp-theo-hợp-lý (Duyệt → Ghi nhận
  xuất chuồng → Kích hoạt lại), phần còn lại vào menu `⋮`
  (`.action-menu`/`.action-menu-toggle`/`.action-menu-list`/
  `.action-menu-item`, class mới — component generic, đặt tên không gắn
  riêng "kế hoạch trại" để tái dùng được cho card đơn hàng ở
  `allocation.js` sau này nếu cần, hiện chưa áp dụng ở đó). Đóng menu khi
  click ra ngoài/Escape/khi 1 action bên trong được bấm — JS thuần, không
  thư viện. Token CSS mới `--z-dropdown: 150`.
- Toàn bộ handler/permission-gate/API call giữ nguyên 100% — chỉ đổi cách
  gom nhóm nút nào là primary/menu. `confirmModal()` xoá kế hoạch giờ nội
  suy `plan_code` vào nội dung ("Kế hoạch {code} sẽ bị xoá...") theo đúng
  spec, trước đó chỉ có text chung chung.

**2026-08-16, quyết định roadmap: bỏ Weighing UX khỏi các phase UI.**
Xác nhận lại với người dùng: công ty đã có phần mềm cân riêng ở trạm cân
(đã ghi nhận từ trước, xem mục "correction right after Phase 1" ở
[[project-sales-workflow]]) — `weighing_records` trong app này **chỉ nên
là tham chiếu ticket code**, không cần (và sẽ không) xây UI thao tác
cân bì/cân heo/chốt cân riêng trong `pig_price`. `core/repositories/
weighing_repo.py`/`media_repo.py` vẫn còn trong code (schema + repo, chưa
route) nhưng **không nằm trong roadmap UX brief nữa** — không cần ưu tiên
wire route cho weighing.

**2026-08-16, Phase 3 (bắt đầu) — Audit Timeline** (`webapp/templates/
admin_audit.html`, `webapp/routes/admin.py:admin_audit_page()`,
`core/audit_actions.py`): backend đã sẵn sàng hoàn toàn từ trước
(`audit_repo.list_audit_log()`/`count_audit_log()` đã wire vào mọi thao
tác quan trọng) nên chỉ cần đổi trình bày — trang trước là bảng
`.admin-table` 6 cột, nay chuyển thành `.timeline`/`.timeline-item` (CSS
có sẵn từ Phase 0, lần đầu được dùng). Thêm 2 helper Python mới trong
`audit_actions.py`: `icon_for(action)` (icon theo tiền tố entity của
action string, VD `"plan.create"` → `"plan"` → 📋) và `is_danger(action)`
(`True` nếu action kết thúc bằng `.delete`/`.reject` hoặc là
`login_failed` — tô đỏ `.timeline-item.is-danger`). Giữ nguyên 100% form
filter + phân trang + logic diff old_value/new_value cũ, chỉ đổi thẻ HTML
bọc quanh. **Evidence Gallery và Incident (2 phần còn lại của Phase 3)
chưa làm** — Evidence thiếu route wire cho `media_repo.py`, Incident thiếu
cả repo lẫn route (bảng `incident_reports` mới chỉ có schema).

**2026-08-16, Phase 3 (tiếp) — Ghi nhận heo Loại/Hủy** (ban đầu hiểu nhầm là
"Evidence Gallery" — người dùng sửa lại: không phải thư viện ảnh chung của
đơn hàng, mà là ghi nhận **số heo bị loại/hủy trong quá trình bán, kèm ảnh
bằng chứng, để giải thích chênh lệch kế hoạch → thực tế bán** — VD 500 con
kế hoạch − 3 loại − 2 hủy = 495 con thực tế bán). Sau khi inspect (không có
khái niệm "loại"/"hủy" ở đâu trong code/schema/docs cũ), xác định đây là
nhánh **Incident**, gắn ở **cấp dòng hàng** (`sale_allocations`), tái dùng
bảng `incident_reports` có sẵn (đã có `allocation_id`/`kind`/`description`,
đúng hướng, chỉ thiếu cột `quantity`) + `media_proof` (đã generic, chưa
route nào dùng tới).

- **Schema (additive, đã duyệt riêng)**: `ALTER TABLE incident_reports ADD
  COLUMN quantity INTEGER NOT NULL DEFAULT 0` trong `_migrate()`. Không đổi
  bảng/cột nào khác. `kind` dùng 2 giá trị mới `culled` (Loại)/`cancelled`
  (Hủy), tái dùng cột TEXT tự do có sẵn.
- **`core/repositories/incident_repo.py`** (mới): `create_incident()`,
  `get_incident()`, `list_incidents_for_order()` (JOIN qua
  `sale_allocations`), `delete_incident()` (**không xoá ảnh/`media_proof`
  liên quan** — giữ evidence trail dù bản ghi chính bị xoá).
- **`webapp/routes/incidents.py`** (blueprint mới, tách khỏi `plans.py` đã
  >1000 dòng): `POST /api/orders/<id>/lines/<line_id>/incidents` (multipart,
  validate kind/quantity ≤ line.quantity/ảnh — đuôi file + MIME + magic
  bytes jpg/png/webp + giới hạn 8MB, theo đúng yêu cầu §27 brief — **lần
  đầu app có upload file thật**), `GET /api/orders/<id>/incidents`,
  `DELETE /api/incidents/<id>`, và **`GET /media/<id>`** — route serve ảnh
  có authorization đầu tiên trong app (check quyền xem đơn hàng trước khi
  `send_file()` từ `MEDIA_ROOT`, chưa từng dùng tới trước đây dù đã khai
  báo sẵn trong `extensions.py`). 2 permission key mới:
  `incident.create`/`incident.delete` (`core/permissions.py`).
- **`allocations.html`/`allocation.js`**: modal `#incident-modal` (chọn
  Loại/Hủy, số lượng, `<input type=file capture=environment multiple>`,
  lý do) + khối "Heo loại/hủy" trong `lineHtml()` hiển thị đối chiếu
  **kế hoạch − Σloại − Σhủy** — **không đụng `sale_allocations.
  actual_quantity`** (ghi nhận độc lập, chỉ đối chiếu trực quan; số thực
  tế bán vẫn nhập tay qua "Đánh dấu Đã bán" như cũ, không đổi business
  logic mark-done).
- **Verify**: script Python gọi qua Flask test client (không cần trình
  duyệt/tài khoản thật) trên **dữ liệu thật** — tạo 1 đơn test từ kế hoạch
  `XH1-20260817-01` (id 16, còn 23 con), tạo incident kèm ảnh JPEG giả,
  xác nhận lưu đúng `quantity`/`kind`, `GET /media/<id>` trả đúng bytes cho
  user có quyền và bị chặn (302 redirect, ngoài `/api/`/`/admin/` nên
  không phải 403 JSON — đúng hành vi decorator `permission_required` sẵn
  có) cho role không có quyền; test riêng 6 trường hợp validate ảnh (đuôi
  cấm, nội dung không khớp magic bytes, thiếu ảnh, kind sai, quantity vượt
  giới hạn) — **16/16 pass**. Dọn sạch sau test: xoá đơn/incident/file ảnh/
  media_proof qua đúng API + SQL trực tiếp, xác nhận `remaining_quantity`
  của kế hoạch 16 khôi phục đúng 23.

**2026-08-16, Operational Dashboard / Exception Center (P0, brief §11/§12)**
— Tổng quan (`dashboard.html`/`dashboard.py`) trước đó chỉ có 4 KPI tĩnh,
không trả lời "cần làm gì ngay". Thêm khối "⚠️ Cần xử lý" ngay sau KPI, 4
nhóm tính từ dữ liệu có sẵn (không bảng/cột mới), mỗi nhóm chỉ hiện khi
user có đúng quyền xử lý (khớp cách `PROCESS_STEPS` gate hiển thị):
1. Kế hoạch trại `pending_approval` (cần `plans.review`).
2. Kế hoạch `approved`, quá `planned_date` mà `received_quantity IS NULL`
   (cần `plans.receive`).
3. Đơn `active` chưa gán khách hàng (cần `plans.sale_details`).
4. Đơn `done` chưa `paid_amount` (cần `plans.revenue_details`).

4 hàm repo mới (`sale_plans_repo.list_pending_review()`/
`list_awaiting_receipt()`, `sale_orders_repo.list_awaiting_sale_details()`/
`list_awaiting_revenue()`) tái dùng `_SELECT_VISIBLE`/`_ORDER_SELECT_VISIBLE`
sẵn có, trả `{"total": N, "items": [...]}` — **lưu ý đặt tên**: dict trả về
từ repo dùng key `"items"` (Python thuần, không sao), nhưng dict TRUYỀN VÀO
JINJA để render phải tránh key `"items"`/`"keys"`/`"values"`/`"get"`/... vì
Jinja thử `getattr` trước `__getitem__` — `ex.items` trên 1 dict sẽ trả về
**bound method `dict.items`** (lỗi `TypeError: 'builtin_function_or_method'
object is not iterable` khi `{% for x in ex.items %}`), không phải giá trị
key. Đã đổi key exception dict thành `"entries"` để tránh đụng. **Cân nhắc
quy tắc này cho mọi dict mới truyền vào template sau này.**

Deep-link + highlight (brief §12): mỗi item exception mang sẵn URL
`?highlight=<id>`; `plan.js`/`allocation.js` thêm `highlightFromQuery()`
(gọi 1 lần cuối `init()`) — tìm phần tử `[data-id="<id>"]` đã có sẵn trên
card (nút hành động hoặc `.order-lines-toggle`/`.plan-detail-toggle` — đều
luôn render bất kể quyền), scroll tới + thêm class `.is-highlighted` (CSS
mới, animation `highlight-pulse`, tự gỡ sau 3s).

**Verify**: script Flask test client tạo 1 kế hoạch pending + 1 đơn thiếu
sale-details trên dữ liệu thật, xác nhận cả 2 nhóm xuất hiện đúng cho admin
và **nhóm bị ẩn đúng cho role không có quyền** (farm role) — 12/12 pass.
Phát hiện + dọn 1 lần dữ liệu test còn sót từ 1 lần chạy script bị crash
giữa chừng (trước khi phát hiện lỗi `ex.items`) — nhắc lại tầm quan trọng
của bước "kiểm tra sạch dữ liệu" sau MỌI lần chạy script test, kể cả khi
script đó tự crash giữa chừng (cleanup ở cuối script sẽ không chạy).

**2026-08-16, Data Freeze UX (P1) — Khoá vĩnh viễn đơn hàng.** Cột
`locked_at`/`locked_by` + trigger chặn UPDATE đã có sẵn trên `sale_plans`/
`sale_allocations`/`sale_orders`/`weighing_records` từ đợt xây trước,
nhưng **chưa route nào từng thực sự set `locked_at`** — Data Freeze mới
chỉ là "khung chặn ở DB", chưa có action thật. Đã có sẵn hàm khoá generic
`weighing_repo.lock_record(table, record_id, ...)`; chỉ thêm `"sale_orders"`
vào `LOCKABLE_TABLES` là dùng được ngay, không viết SQL khoá mới. Thêm
`locked_at`/`locked_by` vào `_ORDER_SELECT_VISIBLE`/`_ORDER_SELECT_ALL`
(`sale_orders_repo.py`) — trước đó 2 cột này tồn tại trong DB nhưng
**chưa từng được SELECT**, API/UI không thấy được. Route mới `PATCH
/api/orders/<id>/lock` (chỉ khoá được đơn `status='done'`); route `DELETE
/api/orders/<id>` thêm chặn nếu đã khoá (trigger DB hiện chỉ canh UPDATE,
không canh DELETE — chặn tay ở route, không đổi trigger). Permission mới
`plans.order_lock` (mặc định chỉ admin). Frontend: nút "🔒 Khoá đơn hàng"
(dùng lại `confirmModal()` sẵn có, không tạo modal mới) + banner
`.locked-banner` nổi bật (nền tối, đúng mẫu brief §18) khi đã khoá, ẩn nút
xoá khi đã khoá.

⚠️ **Lỗi thật phát hiện khi verify, đã sửa**: sửa 1 đơn đã khoá →
`sqlite3.IntegrityError: DATA_FROZEN: ...` từ trigger bay thẳng lên thành
lỗi 500 thô (đúng loại lỗi "Internal Server Error" người dùng từng thấy
trên điện thoại khi test thủ công một tính năng khác) — vì trước Data
Freeze UX, chưa ai từng thực sự khoá được gì nên nhánh lỗi này chưa từng
chạy qua HTTP. Sửa bằng 1 `@app.errorhandler(sqlite3.IntegrityError)` tập
trung trong `webapp/app_factory.py` — chỉ nuốt đúng lỗi bắt đầu bằng
`"DATA_FROZEN"` thành `400` sạch, mọi `IntegrityError` khác (VD UNIQUE
constraint) vẫn báo lỗi mặc định như cũ. **Handler này che luôn cho
`sale_plans`/`sale_allocations`/`weighing_records` nếu sau này có action
khoá cho các bảng đó** — không cần lặp lại per-route.

**Verify**: Flask test client trên dữ liệu thật — tạo đơn → chặn khoá khi
`active` → mark-done → khoá thành công → chặn khoá lại lần 2 → sửa
sale-details sau khoá trả `400` sạch (không còn 500) → chặn xoá đơn đã
khoá — 9/9 pass. Dọn dữ liệu test: đơn đã khoá không xoá được qua API
(đúng thiết kế) nên dọn trực tiếp bằng SQL (`DELETE` bỏ qua trigger vì
trigger chỉ canh `UPDATE`) — phát hiện thêm 1 đơn khoá còn sót từ lần
chạy script bị crash trước khi có fix, dọn luôn, xác nhận
`remaining_quantity` kế hoạch 16 về đúng 23.

**2026-08-16, Cải tiến file Excel "Phiếu chào hàng"** (không thuộc UX
brief — task riêng, chỉ đụng `core/services/export_service.py` +
`webapp/routes/plans.py`, không đổi DB/API/RBAC/UI web). File xuất từ nút
"⬇️ Xuất chào hàng" (`/api/orders/quotation.xlsx`) trước đó là
`pandas.DataFrame.to_excel()` thuần — 1 bảng phẳng không style, đúng kiểu
data export chứ không phải tài liệu gửi khách. Viết lại
`export_order_quotation_to_excel()` dựng workbook trực tiếp bằng
`openpyxl` (bỏ qua pandas cho hàm này — 3 hàm export khác giữ nguyên
pandas, không đụng): header (logo `logo-icon.png` có sẵn + tiêu đề) →
khối "Thông tin chào hàng" (chỉ hiện khi xuất đúng 1 đơn) → khối tóm tắt
3 cột Loại heo/Số lượng/Giá chào (nền màu quy đổi từ design token CSS
sang hex vì Excel không đọc CSS variable) → bảng "Chi tiết chào hàng" đầy
đủ style (border/wrap/autosize). Page setup: A4 ngang, fit 1 trang ngang.
Filename đổi từ `chao_hang_<ngày>.xlsx` chung chung sang
`Phieu_chao_hang_<mã_đơn>.xlsx`. **Tuyệt đối không có "Tổng tiền"** — hệ
thống chỉ có số lượng theo con + giá theo kg, không có tổng trọng lượng,
nhân trực tiếp sẽ sai đơn vị. Nhân tiện sửa 1 bug nhỏ: hàm cũ quên áp
`PAYMENT_METHOD_LABEL` nên file chào hàng từng lộ raw giá trị DB (VD
"bank_transfer_immediate") thay vì nhãn tiếng Việt.

**Verify**: Flask test client trên dữ liệu thật — **phát hiện dữ liệu
thật của người dùng đã có trong DB** (đơn `DH20260816-01` từ kế hoạch 16,
người dùng tự tạo khi test app sau lần restart server) → **không đụng
vào**, tạo hẳn 1 kế hoạch + đơn test riêng biệt (note đánh dấu rõ) để
không can thiệp dữ liệu thật. Đọc lại file `.xlsx` trả về bằng
`openpyxl.load_workbook()` xác nhận: đúng dữ liệu, đúng filename, không
field nội bộ/audit nào lọt vào, không có "Tổng tiền"/công thức tính tiền,
page setup đúng (landscape/A4/fit 1 trang) — 26/27 pass (1 "fail" là false
positive do quirk load lại paperSize thành string thay vì int, đã tự xác
minh riêng file ghi ra đúng). Dọn sạch dữ liệu test, xác nhận dữ liệu thật
của người dùng (kế hoạch 16, đơn 13) còn nguyên vẹn.

**2026-08-17, redesign lại "Phiếu chào hàng" lần 2 — ưu tiên ngôn từ &
tính thương mại.** Bản vừa xong ở trên vẫn đọc như "bảng dữ liệu hệ thống
được format đẹp" (3 section đều lặp chữ "CHÀO HÀNG", hiện "Chưa cập nhật"
cho field trống, luôn 3 khối dù chỉ 1 dòng hàng). Viết lại hoàn toàn
`export_order_quotation_to_excel()` theo hướng "thư chào giá" liền mạch:
tiêu đề "BẢNG CHÀO GIÁ / HEO THƯƠNG PHẨM" → Mã chào giá + Ngày lập phiếu
(ngày thật lúc xuất, không phải ngày dự kiến giao) → lời chào "Kính gửi
Quý khách," + câu dẫn → thông tin giao dịch cấp **đơn hàng** (Khách
hàng/Hình thức thanh toán/Khung giờ giao — hiện 1 lần, **chỉ khi có dữ
liệu**, bỏ hẳn field nếu rỗng thay vì hiện "Chưa cập nhật") → thông tin
sản phẩm cấp **dòng hàng**: **layout phiếu label:value khi đơn chỉ 1 dòng
hàng** (Loại heo/Số lượng/Đơn giá/Trang trại/Ngày dự kiến/Ghi chú nếu có),
**chuyển sang bảng khi có ≥2 dòng** (thêm cột Ghi chú chỉ khi ít nhất 1
dòng có ghi chú) → "Trân trọng." kết thúc. Đổi tên field "GIÁ CHÀO" →
"Đơn giá", bỏ hẳn "Chuồng/Lô" (thông tin quản lý trại nội bộ, không cần
với khách). Bỏ toàn bộ fill nền đậm/emoji — màu thương hiệu chỉ làm accent
chữ. Đổi A4 ngang → **A4 dọc** (bảng giờ hẹp hơn nhiều, portrait giống 1
lá thư hơn). Filename `Phieu_chao_hang_` → `Phieu_chao_gia_`, sheet
"Phieu chao hang" → "Bang chao gia". Thêm `_fmt_vi_number()` dùng dấu chấm
ngăn cách hàng nghìn (65.500) khớp `fmtPrice()`/`toLocaleString("vi-VN")`
đã dùng trong JS toàn app — bản trước dùng dấu phẩy kiểu Mỹ, không nhất
quán.

**Verify**: test cả 2 case — đơn 1 dòng hàng (layout phiếu) và đơn 2 dòng
hàng từ 2 kế hoạch trại khác nhau XH1/XH2 (layout bảng, cột Ghi chú chỉ
xuất hiện đúng lúc có dữ liệu) — 35/35 pass, xác nhận không còn "Chưa cập
nhật"/"N/A", không lặp "CHÀO HÀNG", không emoji, đúng số định dạng kiểu
Việt Nam. Lại tạo dữ liệu test riêng biệt (không đụng kế hoạch 16/đơn 13
thật của người dùng), dọn sạch sau khi xong, xác nhận dữ liệu thật còn
nguyên.

**2026-08-17, redesign lại "Bảng chào giá" lần 3 — bố cục/composition,
không phải màu/border/font.** Round 2 đúng ngôn từ nhưng người dùng phản
hồi tiếp: mở ở chế độ in/PDF vẫn "nhìn như bảng dữ liệu hệ thống format
đẹp". Viết lại hoàn toàn cách dựng sheet trong
`export_order_quotation_to_excel()` (cùng file, vẫn không đụng 3 hàm
export pandas khác):
- `ws.sheet_view.showGridLines = False`; canvas nội dung cố định 7 cột
  A–G (`_QUOTATION_CANVAS_COLS`, `_QUOTATION_COL_WIDTHS`), không kéo dài
  theo dữ liệu.
- **1 khối tiêu đề thống nhất**: logo (A1) + "BẢNG CHÀO GIÁ" +
  "HEO THƯƠNG PHẨM" + "Mã chào giá: ... · Ngày: ..." gộp cùng 1 nhóm
  (3 dòng liền, không tách rời như Round 2), đóng bằng 1 đường kẻ mảnh
  (`_set_row_border`, không phải border bao toàn ô kiểu bảng).
- **Khối "tóm tắt thương mại" 3 cột nổi bật** (Loại heo/Số lượng/Đơn giá)
  khi đơn 1 dòng hàng: label nhỏ muted phía trên, giá trị to đậm
  (size 16) phía dưới, viền mảnh CHỈ ở cạnh ngoài + nền rất nhạt
  (`_HEX_SUMMARY_FILL`) bao quanh cả khối — dùng helper mới
  `_set_outer_box()` (viền cạnh ngoài, không kẻ lưới nội bộ, khác hẳn
  `_thin_border()` cũ dùng cho ô đơn lẻ).
- Section phụ đổi tên "THÔNG TIN BỔ SUNG" (thay vì trộn chung
  label:value cấp dòng cũ) — case 1 dòng luôn có Trang trại/Ngày dự
  kiến + field cấp đơn nếu có; case nhiều dòng chỉ còn field cấp đơn
  (Trang trại/Ngày dự kiến đã có trong bảng, không lặp).
- Case ≥2 dòng: bảng thêm cột **STT**, đổi thứ tự cột thành
  `QUOTATION_TABLE_FIELDS` (Loại heo → Trang trại → Số lượng → Đơn giá
  → Ngày dự kiến) khớp cách đọc tự nhiên, vẫn tối đa 7 cột (STT + 5 field
  + Ghi chú điều kiện) — vừa khít canvas, không cần kéo rộng.
- Lời kết đổi thành khối 2 dòng "Trân trọng," + "**XUÂN THIỆN**" (tên
  thương hiệu có sẵn từ `base.html`, không bịa SĐT/email/địa chỉ) sau 1
  đường kẻ mảnh đóng section, thay vì 1 dòng "Trân trọng." đơn độc.
- Bỏ hẳn `QUOTATION_LINE_FIELDS` cũ (không còn dùng, thay bằng
  `QUOTATION_TABLE_FIELDS` cho case bảng + field rời cho case tóm tắt).

**Bug thật phát hiện khi verify bằng PDF** (không phải chỉ đọc cell
`openpyxl`): case bảng nhiều dòng lúc đầu tái sử dụng
`_QUOTATION_COL_WIDTHS` mặc định (cột B rộng chỉ 2, vốn để làm spacer
cho layout phiếu 1 dòng) — cột "Loại heo" trong bảng bị bóp còn ~2 đơn vị
rộng nên Excel wrap từng ký tự xuống 1 dòng riêng ("H/e/o/..." theo chiều
dọc), chỉ thấy được khi render PDF thật, `openpyxl.load_workbook()` đọc
cell value vẫn "đúng" nên không phát hiện ra. Fix: tính lại độ rộng cột
theo nội dung thật (autosize, min 6/max 30) riêng cho nhánh bảng, không
dùng chung với canvas mặc định của layout phiếu 1 dòng.

**Verify — theo đúng yêu cầu đặc biệt của người dùng, không chỉ đọc
`openpyxl`**: cài `pywin32`, dùng `win32com.client.Dispatch('Excel.
Application')` mở thật 2 file `.xlsx` test (case 1 dòng, case 2 dòng) đã
tạo qua Flask test-client với dữ liệu `TEST_` riêng biệt, xuất PDF thật
bằng `Worksheet.ExportAsFixedFormat(0, pdf_path)`, sau đó render PDF ra
PNG bằng `PyMuPDF` (`fitz`, đã có sẵn trong env) để xem trực quan như
khách hàng nhận file (plugin pdf-viewer không có local dir được phép
trong session này nên dùng đường vòng render ảnh). Cả 2 case ra 1 trang
A4 (fit-to-page hoạt động đúng), bố cục đọc như 1 quotation thật — không
còn cảm giác "database export". Dọn sạch file test (`.xlsx`/`.pdf`/`.png`
scratch + dữ liệu `TEST_` trong DB qua API delete), xác nhận kế hoạch
16/đơn `DH20260816-01` (dữ liệu thật) không đổi.

**2026-08-18, Đối soát kế hoạch trại → thực tế bán (kế hoạch 23, bán 20,
còn 3 chưa xử lý).** Trước đây `sale_plans` chỉ có `quantity` (kế hoạch
gốc) + 2 field tính động `allocated_quantity`/`remaining_quantity` (=
đã "nhặt" vào đơn hay chưa) — không có khái niệm "thực tế đã bán" ở cấp
kế hoạch, và không có cơ chế ghi nhận/đóng phần chênh lệch khi bán ít
hơn kế hoạch (heo còn tại trại/tiếp tục bán/chuyển nguồn/loại/khách
hủy/khác). `incident_reports` (tính năng Ghi nhận heo Loại/Hủy đã có)
không dùng lại được cho việc này vì gắn cứng vào `allocation_id` (1 dòng
hàng cụ thể) — phần số lượng CHƯA từng được đưa vào đơn nào (trường hợp
phổ biến nhất) không có `allocation_id` để gắn.

**Schema (additive, bảng mới)**: `sale_plan_reconciliations`
(`core/db.py`) — `sale_plan_id` (gắn thẳng kế hoạch trại, không qua
allocation), `kind` (6 giá trị: `still_at_farm`/`continue_selling`/
`transferred`/`culled`/`cancelled`/`other`), `quantity`, `reason`
(bắt buộc mọi kind), `reported_by/at`. Ảnh bằng chứng bắt buộc với
`culled`/`cancelled` (khớp incident hiện có), tuỳ chọn với 4 kind còn
lại — tái dùng nguyên `media_proof`/`media_repo.save_upload()` sẵn có,
`entity_type='plan_reconciliation'`. Không đổi bảng cũ nào, không đổi
`sale_plans.status` enum (chỉ thêm field tính động, xem dưới).

**3 field tính động mới trên `sale_plans_repo.py`** (cùng khuôn
`_ALLOCATED_SQL` cũ, không lưu cột riêng):
- `actual_sold_quantity` = SUM(`sale_allocations.actual_quantity`) của
  các dòng hàng thuộc đơn đã `status='done'` — số THỰC TẾ bán, khác
  `allocated_quantity` (chỉ là số đã "nhặt" vào đơn, có thể đơn còn
  `active` chưa giao — tránh hiển thị nhầm allocated là "đã bán").
- `reconciled_quantity` = SUM quantity của bản ghi đối soát CHỈ 4 kind
  "chốt" (`transferred`/`culled`/`cancelled`/`other`) — cố ý KHÔNG gồm
  `still_at_farm`/`continue_selling` (2 kind này là ghi nhận/xác nhận
  "vẫn còn, chưa xong", không đóng được kế hoạch).
- `remaining_to_reconcile = quantity - actual_sold_quantity -
  reconciled_quantity` — số CHƯA được giải thích, dùng thống nhất cho cả
  2 tình huống: (a) số chưa từng đưa vào đơn, (b) số đã đưa vào đơn
  (`active`, chưa "Đã bán") hoặc đã "Đã bán" nhưng `actual_quantity`
  thấp hơn `quantity` dòng hàng do cân thực tế lệch.
- `reconciliation_status` (tính ở Python sau khi fetch, chỉ có nghĩa khi
  `status='approved'`): `"reconciled"` (remaining_to_reconcile≤0),
  `"needs_reconciliation"` (còn chênh lệch VÀ đã quá `planned_date`),
  `"in_progress"` (còn chênh lệch nhưng vẫn còn hạn — tránh báo động khi
  vẫn còn thời gian bán bình thường). `reconciliation_breakdown` (1 query
  gộp `GROUP BY sale_plan_id, kind`, tránh N+1) đi kèm để hiện "Đã loại 3
  / Khách hủy..." trên thẻ khi đã đối soát xong.

**Route mới** (`webapp/routes/plans.py`): `POST/GET
/api/plans/<id>/reconciliations`, `DELETE /api/reconciliations/<id>` —
validate `quantity <= remaining_to_reconcile`, chặn nếu plan chưa
`approved` hoặc đã `locked_at` (Data Freeze — cờ này tồn tại sẵn trên
`sale_plans` từ trước nhưng **chưa route nào từng set nó**, phát hiện
khi viết tính năng này). Permission mới `plans.reconcile_create`/
`plans.reconcile_delete`. `GET /media/<id>` (`incidents.py`) sửa nhỏ để
phân nhánh quyền theo `media["entity_type"]` (`incident` vs
`plan_reconciliation`) thay vì gate cứng 1 tập quyền — không đổi hành vi
cũ cho ảnh incident.

**Guard mới trong `update_sale_plan_edit()`** (đã có sẵn, không phải
route mới): chặn sửa trực tiếp `sale_plans.quantity` nếu đã có đơn hàng
(`allocated_quantity > 0`) hoặc đã có bản ghi đối soát — raise
`ValueError` (route bắt, trả 400). Đóng đúng lỗ hổng "23 âm thầm sửa
thành 20" mà brief lo ngại (trước đây `update_sale_plan_edit` sửa
`quantity` tự do, không ràng buộc gì).

**UI** (`plan.js`/`plans.html`): thẻ kế hoạch trại đổi "Tiến độ bán"
dùng `actual_sold_quantity` (không phải `allocated_quantity`) làm % +
dòng "Đã bán"/"Chưa xử lý", cảnh báo `.alert-warning` "⚠ Cần đối soát"
khi `needs_reconciliation`, badge `.badge-success` "✓ Đã đối soát" +
breakdown khi `reconciled`. "Đã phân bổ (đơn hàng)" (số cũ) chuyển xuống
khối "Chi tiết" thay vì bỏ. Nút primary "⚖️ Xử lý chênh lệch" chỉ chiếm
vị trí primary khi `needs_reconciliation` (cấp bách hơn "Ghi nhận đã
xuất chuồng"), còn `in_progress` thì xuống menu ⋮ — tránh 2 primary
tranh chỗ. Modal `#reconcile-modal` (mirror `#incident-modal`) — 6 nút
chọn kind, ảnh bắt buộc/tuỳ chọn đổi động theo kind chọn. Bảng "Nguồn
cung có thể bán" (`allocation.js`/`allocations.html`): đổi nhãn cột
"Đã bán" → "Đã phân bổ" (số hiển thị không đổi, chỉ sửa nhãn cho đúng
bản chất — **cột "Còn lại" vẫn giữ `remaining_quantity`, KHÔNG đổi sang
`remaining_to_reconcile`**, vì mục đích bảng này là "còn bao nhiêu để
phân bổ thêm", khác ý nghĩa "còn bao nhiêu chưa giải trình" — nhận ra
sự khác biệt này khi implement, khác với dự định ban đầu trong plan),
thêm badge `⚠ Cần đối soát` ở cột trạng thái khi cần.

**Bug thật phát hiện khi test**: Case E (kế hoạch bị khoá) lúc đầu trả
201 thay vì bị chặn — do route quên check `plan["locked_at"]` (đã mô tả
trong plan nhưng quên code) VÀ `locked_at`/`locked_by` chưa từng được
SELECT trong `sale_plans_repo.py` (cột có trong bảng nhưng không lộ ra
qua `_SELECT_VISIBLE`/`_SELECT_ALL`) nên dù có check cũng đọc `None`.
Fix: thêm 2 cột vào cả 2 SELECT + check `plan.get("locked_at")` trong
route. Phát hiện qua chính bộ test đã viết (không phải review thủ công)
— minh chứng giá trị của việc viết test case cho từng nhánh nghiệp vụ
trong plan thay vì chỉ test "happy path".

**Verify**: 35/35 assertions qua Flask test-client trên dữ liệu thật —
Case A (needs_reconciliation), B (reconciled), C (còn 1 con chưa xử
lý), D (allocated≠actual_sold), E (locked chặn được, sau fix), F (403
không quyền), + edge case (thiếu ảnh culled → 400, vượt cap → 400,
still_at_farm không giảm remaining_to_reconcile, xoá bản ghi tính lại
đúng, guard sửa quantity). Verify UI qua scratch page (`webapp/static/`,
xoá sau khi xong) với `window.fetch` patch trả sample data 3 trạng thái
— xác nhận đúng cả desktop lẫn mobile (375px, có viewport meta tag).
Dọn sạch dữ liệu/media test, xác nhận dữ liệu thật không đổi. Đã restart
server production (port 5000) sau khi implement xong — tính năng đã lên
thật.

**2026-08-18, Giai đoạn 1 của brief mới: nền dữ liệu "Xuất thực tế"
(`sale_deliveries`).** Brief mới yêu cầu đối soát ĐA CHIỀU (số lượng + cơ
cấu loại heo + trọng lượng + ngày xuất + khách hàng + giá + phiếu cân),
với ví dụ cốt lõi **kế hoạch 100 loại 1 → thực tế 80 loại 1 + 20 loại 2**
(tổng khớp nhưng cơ cấu lệch). Hệ thống cũ **không ghi nhận được**:
`sale_allocations` cố ý không lưu `pig_type_id` riêng (JOIN ngược về kế
hoạch), `mark_order_done()` chỉ ghi `actual_price`/`actual_quantity`,
không có trọng lượng, không có ngày xuất tách khỏi ngày kế hoạch.

Người dùng chốt: "loại 1/loại 2" là **các dòng riêng trong `pig_types`**
(đã có thật) → không cần chiều grade mới; **có** đưa trọng lượng vào (cả
dự kiến lẫn thực tế); làm **nền dữ liệu trước**, dashboard/biểu đồ/báo
cáo sau.

**Bảng mới `sale_deliveries`** (1 dòng hàng → N lần xuất): `allocation_id`,
`pig_type_id` (**loại THỰC TẾ, có thể khác kế hoạch**), `quantity`,
`total_weight_kg`, `unit_price`, `delivered_date` (**độc lập
planned_date**), `weighing_ref`, `note`, `locked_at/by` + trigger
`trg_sale_deliveries_lock_guard`. Đặt trong `_DB_SCHEMA` (không phải
`_migrate()`) vì là bảng mới hoàn toàn có `locked_at` từ đầu — giống tiền
lệ `weighing_records`. **Không** lưu `customer_id` (suy ra qua
`allocation → sale_orders`, tránh nguồn sự thật thứ 2). Thêm
`sale_plans.expected_avg_weight_kg` (kg/con dự kiến) qua ALTER.

**Backfill có cờ một-lần** (`app_meta.backfill_sale_deliveries_v1`): sinh
5 dòng delivery từ `actual_quantity` cũ để đổi nguồn `_ACTUAL_SOLD_SQL`
mà số liệu không đổi (đã đối chiếu trước/sau: 200/600/200/99 y hệt).
**Bắt buộc có cờ** vì `_migrate()` chạy trong `get_connection()` mà mỗi
hàm repo mở 1 kết nối riêng → 1 lần tải trang mở DB hàng chục lần, không
cờ sẽ nhân số liệu lên nhiều lần ngay trong 1 request. **Cố ý KHÔNG dùng
`NOT EXISTS` trên bảng đích**: cách đó idempotent nhưng còn vũ trang mãi
— user xoá 2 delivery (80+20) để nhập lại thì lần mở kết nối kế tiếp hồi
sinh 1 delivery ma 100 con (đã viết test T1b chứng minh).

**Field tính động mới** (`sale_plans_repo.py`): `_ACTUAL_SOLD_SQL` đổi
nguồn sang `sale_deliveries` và **đổi bộ lọc từ `status='done'` sang
`IN ('active','done')`** (trùng `_ALLOCATED_SQL`) — brief yêu cầu "xuất
nhiều lần", tức xuất xảy ra khi đơn còn active; chỉ đếm `done` thì kế
hoạch đã giao thật 80/100 vẫn báo "Cần đối soát" cho cả 100. Hệ quả: nhãn
UI nên đọc là **"Đã xuất/giao"** chứ không phải "Đã bán", và kế hoạch đạt
`reconciled` sớm hơn trước. Thêm `planned_total_weight_kg`/
`actual_total_weight_kg` (**cố ý KHÔNG COALESCE về 0** — NULL = "chưa nhập
cân", 0 = "cân bằng 0"; gộp lại sẽ hiện lệch −100% trên mọi kế hoạch chưa
ai gõ cân), `weight_missing_delivery_count`, `delivery_count`,
`last_delivered_date`, `off_type_quantity`, và `delivery_mix` (1 query
GROUP BY cho cả trang) trả `quantity_matches` / `has_composition_variance`
/ `unconfirmed_composition` — ví dụ của brief ra đúng cặp
`quantity_matches=true` + `has_composition_variance=true`.

**Sửa 1 bug thật của vòng trước**: `_apply_reconciliation_status` cũ là
`if remaining <= 0: "reconciled"` → xuất dư (120/100) cho `remaining=-20`
và hiện **badge xanh "Đã đối soát"** đúng lúc cần cảnh báo nhất. Thêm
`over_delivered` + trạng thái `"over_delivered"`, kiểm trước nhánh `<=0`.

`sale_allocations.actual_quantity/actual_price` **giữ lại nhưng thành
cache dẫn xuất 1 CHIỀU** (export Excel + UI cũ đang đọc), ghi lại từ
deliveries qua `_sync_allocation_actuals()` với **giá bình quân gia
quyền**. Không đồng bộ 2 chiều vì `trg_sale_allocations_lock_guard` chặn
mọi UPDATE khi đã khoá → dual-write chắc chắn phân kỳ đúng trên bản ghi
quan trọng nhất về audit. `mark_order_done()` giữ nguyên signature (route/
JS không phải sửa): dòng chưa có delivery → tạo 1 (luồng nhanh cũ); dòng
đã có → không tạo thêm, chỉ đồng bộ cache.

**Blueprint mới `webapp/routes/deliveries.py`** (tách khỏi `plans.py` đã
>1200 dòng, theo tiền lệ `incidents.py`): POST/GET deliveries theo đơn,
GET theo kế hoạch, DELETE. Quyền mới `plans.delivery_create|delete`,
audit `delivery.create|delete` (icon 🚚). Chặn xuất vượt kế hoạch ở route.

**Vá lỗ hổng phát sinh**: `admin.py` chỉ chặn xoá `pig_types` khi có kế
hoạch dùng — nhưng cả tính năng này sinh ra để delivery mang loại CHƯA
từng có trong kế hoạch, nên loại đó xoá được trong khi đang dùng thật
(`PRAGMA foreign_keys` không bật nên DB không tự chặn) → mất câu trả lời
"lệch sang loại gì". Thêm `count_deliveries_for_pig_type()` vào guard.

**2 gap phát hiện khi test** (test bắt được, không phải review): route
`POST/PATCH /api/plans` chưa truyền `expected_avg_weight_kg` xuống repo
(field ghi-một-lần-không-bao-giờ-set-được), và
`SALE_ORDER_LINE_VISIBLE_COLUMNS` thiếu `locked_at` nên guard Data Freeze
ở tầng dòng hàng đọc ra `None` và không chặn được. Đã sửa cả hai.

**Verify**: T0 (backfill tương đương, chạy trên BẢN COPY trước khi đụng
DB thật), T1/T1b (idempotency 21 lần mở kết nối + test hồi sinh),
T2–T10 → **47/47 pass** trên DB thật với fixture `TEST_`. Xác nhận
row-count parity tuyệt đối với backup sau khi dọn.

**Sự cố trong lúc dọn dữ liệu test — đã khắc phục**: câu lệnh dọn dùng
mệnh đề quá rộng `DELETE FROM sale_orders WHERE id NOT IN (SELECT
order_id FROM sale_allocations)` đã xoá nhầm **2 đơn thật rỗng**
(`DH20260818-01`, `DH20260818-02` — đơn thật không có dòng hàng nào cũng
khớp điều kiện đó). Đã khôi phục nguyên vẹn từ backup timestamp và đối
chiếu lại toàn bộ row-count. **Bài học ghi vào script test: khi dọn chỉ
được liệt kê đúng id do chính test tạo ra, không bao giờ suy luận
"dòng nào không có con thì là rác".**

**2026-08-18, Giai đoạn 2: UI ghi nhận "Xuất giao thực tế" + trọng lượng
dự kiến.** Giai đoạn 1 xây xong nền dữ liệu nhưng chưa có UI nào gọi tới
— giai đoạn này lấp đúng chỗ trống đó, thuần frontend, không đổi
schema/route đã có (trừ 1 bug backend phát hiện khi verify, xem dưới).

- `plans.html`/`plan.js`: thêm ô `#plan-weight` (kg/con dự kiến, tuỳ
  chọn) vào form tạo/sửa kế hoạch trại, wire qua `submitPlan`/
  `startEditPlan`.
- `plan.js`: `planReconcileHtml()` mở rộng hiện khối lượng
  (`actual_total_weight_kg`/`planned_total_weight_kg`, dùng "—" khi
  thiếu — hàm `fmtWeight` mới, đặt trong `common.js` để dùng chung cả 2
  trang thay vì trùng lặp) và cảnh báo "⚠ Lệch cơ cấu: N con khác loại
  kế hoạch" (từ `delivery_mix.has_composition_variance`/
  `off_type_quantity`) — độc lập với cảnh báo "Cần đối soát" cũ (2 khái
  niệm khác nhau: thiếu số lượng vs đúng số lượng nhưng khác loại).
- **Bug thật phát hiện khi mở rộng `planReconcileHtml()`, không phải
  tính năng mới cố ý bỏ sót**: trạng thái `"over_delivered"` (thêm ở
  Giai đoạn 1 để tránh hiện badge xanh sai khi xuất dư) **chưa từng
  được xử lý ở tầng JS** — code cũ chỉ rẽ nhánh `remaining > 0` hoặc
  `isComplete (=== "reconciled")`, nên `remaining < 0` rơi vào khoảng
  trống, không hiện cảnh báo nào cả. Đã thêm nhánh riêng
  `.alert-danger` "⚠ Xuất vượt kế hoạch" kiểm TRƯỚC 2 nhánh kia.
- `allocations.html`/`allocation.js`: modal mới `#delivery-modal` (loại
  heo thực tế — mặc định preselect đúng loại kế hoạch của dòng hàng
  nhưng cho đổi để ghi cơ cấu lệch — số lượng/trọng lượng/đơn giá/ngày
  xuất/phiếu cân/ghi chú), gửi JSON (khác `#incident-modal` gửi
  multipart vì không có ảnh). Khối "Xuất giao thực tế" mới trên mỗi
  dòng hàng (`deliverySectionHtml`, khuôn `incidentSectionHtml`) hiện
  lịch sử các lần xuất + nút xoá từng dòng (quyền
  `plans.delivery_delete` — đây là cơ chế SỬA duy nhất vì backend không
  có PATCH, sửa = xoá + tạo lại). Nút "🚚 Ghi nhận xuất giao" cố ý RỘNG
  hơn điều kiện nút "🐖 Ghi nhận Loại/Hủy" hiện có (`status==='active'`
  only) — cho phép xuất nhiều lần cả khi đơn đã `done`, chỉ chặn khi đã
  khoá (Data Freeze)/huỷ, đúng thiết kế Giai đoạn 1.
- **2 gap khác phát hiện khi verify (không phải review thủ công)**:
  (1) payload dòng hàng (`SALE_ORDER_LINE_VISIBLE_COLUMNS`/`_LINE_SELECT`
  trong `sale_orders_repo.py`) chưa từng expose `pig_type_id` dạng số
  (chỉ có `pig_type`/`pig_type_name` dạng mã/tên hiển thị) — khiến modal
  không preselect được loại heo kế hoạch; đã thêm `sp.pig_type_id AS
  pig_type_id` vào SELECT. (2) nút xoá từng lần xuất
  (`deliveryItemHtml`) chỉ kiểm quyền `CAN_DELETE_DELIVERY`, quên kiểm
  `d.locked_at` — hiện nút xoá cho bản ghi đã Data Freeze (bấm sẽ ra lỗi
  400 từ server) trong khi nút "thêm mới" cùng khối đã tự ẩn đúng theo
  `order.locked_at`; đã thêm điều kiện `!d.locked_at`.
- **Bug backend thật, phát hiện qua chính đợt verify Giai đoạn 2 này
  (không phải review)**: `delete_order()` (đã có sẵn từ trước, chặn xoá
  đơn khi dòng hàng có `weighing_records`/`incident_reports` gắn vào,
  theo đúng nguyên tắc "không cascade bảng audit trail") **chưa từng
  được cập nhật để cũng kiểm `sale_deliveries`** khi bảng này ra đời ở
  Giai đoạn 1 — xoá 1 đơn đã có lần xuất giao ghi nhận trước đó sẽ âm
  thầm để lại delivery mồ côi (không lỗi, không cascade, chỉ đơn giản bỏ
  sót). Phát hiện qua chính test script của mình (dọn dữ liệu test xong,
  đối chiếu row-count với backup thấy lệch 1 dòng `sale_deliveries`).
  Đã thêm `sale_deliveries` vào cùng điều kiện chặn — cascade-xoá sẽ phá
  huỷ đúng audit trail mà cả tính năng Giai đoạn 1 xây ra để giữ lại,
  nên chặn (bắt admin tự xử lý trước) là lựa chọn đúng, khớp cách 2 bảng
  kia đã được xử lý.

**Verify**: 25/25 assertion qua Flask test-client (field trọng lượng
round-trip qua create/edit, NULL≠0, `pig_type_id` lộ đúng trong payload
dòng hàng, ghi nhận xuất giao khác loại kế hoạch, `delivery_mix`/
`off_type_quantity` đúng, xoá tính lại đúng) + verify UI qua scratch
page (`webapp/static/`, xoá sau khi xong) với `window.fetch` patch —
xác nhận: modal mở đúng, preselect đúng loại heo kế hoạch, validate
client-side chặn submit rỗng, submit gửi đúng JSON tới đúng route, nút
thêm/xoá ẩn đúng theo trạng thái khoá, `confirmModal()` xoá hoạt động
đầy đủ (mở → xác nhận → gọi DELETE → đóng), cả desktop lẫn mobile
(375px). Riêng test cascade-xoá-đơn chạy qua Flask test-client trực
tiếp (không qua UI). Dọn dữ liệu test theo đúng id đã tạo, đối chiếu
row-count với backup — khớp tuyệt đối sau khi dọn thêm 1 dòng mồ côi
phát hiện được nhờ chính phép đối chiếu này. Server production đã
restart sau khi xong.

**2026-08-18, Giai đoạn 3 — Dashboard mở rộng: KPI 5 số + biểu đồ xu
hướng/cơ cấu + bảng theo ngày.** Tiếp nối Giai đoạn 1/2 (nền dữ liệu +
UI ghi nhận) — giờ mới có dữ liệu thật để dashboard hiển thị. Trang Tổng
quan (`/`) trước chỉ có 4 KPI thô, không biểu đồ, không bảng theo ngày.
Route mới `GET /api/dashboard/summary?days=N` (không gate permission,
giống route `/` hiện tại — chỉ lọc `farm_ids`) trả 1 lần cả 3 phần dữ
liệu cho trang.

- 4 hàm mới trong `sale_plans_repo.py` (đọc thuần, không ghi):
  `dashboard_summary()` (5 KPI: kế hoạch/đã chốt/đã xuất/chưa xuất/sai
  lệch, theo SỐ CON — khác hẳn `dashboard_stats()` cũ đếm theo ĐƠN, giữ
  nguyên không đụng), `daily_reconciliation_series()` (1 query dùng
  chung cho CẢ bảng theo ngày LẪN biểu đồ xu hướng, tránh 2 query cùng 1
  dữ liệu), `pig_type_composition()` (cơ cấu loại heo THỰC TẾ đã xuất,
  nguồn `sale_deliveries` chứ không phải kế hoạch), `list_needs_reconciliation()`
  (tái dùng `list_sale_plans()` đã có thay vì viết lại điều kiện SQL
  "thế nào là cần đối soát" lần thứ 3).
- Cả 3 hàm đầu dùng chung 1 mốc thời gian duy nhất — `sale_plans.
  planned_date` — cho mọi vế (kế hoạch/chốt/xuất), để 1 ngày trên biểu đồ
  luôn nói về đúng 1 lô hàng dự kiến ngày đó.
- **Bug thật phát hiện ngay khi smoke-test bằng dữ liệu thật (trước khi
  qua browser)**: cửa sổ ngày ban đầu chỉ NHÌN NGƯỢC (`[hôm nay-days, hôm
  nay]`, giống hệt `#days-select` của `gia_heo.html`) — nhưng khác giá
  lịch sử (không bao giờ ở tương lai), kế hoạch trại thường được tạo cho
  vài ngày TỚI. Kiểm bằng dữ liệu thật: 3/4 kế hoạch đang có `planned_date`
  sau "hôm nay" 1-3 ngày, cửa sổ nhìn-ngược bỏ sót hoàn toàn 75% dữ liệu
  thật. Fix: `_dashboard_date_range()` dùng chung, cộng thêm buffer tới
  gần cố định 7 ngày (`_DASHBOARD_FORWARD_BUFFER_DAYS`), không cho chọn —
  dropdown "N ngày" vẫn giữ nguyên nghĩa "nhìn ngược bao xa".
- Khối "Cảnh báo & cần xử lý" thêm loại thứ 5 (kế hoạch cần đối soát),
  gate theo `plans.reconcile_create` — đúng khuôn 4 loại cũ (gate theo
  quyền HÀNH ĐỘNG, không phải quyền xem).
- Frontend: `dashboard.html` giữ nguyên khối "Số liệu chính" (4 KPI +
  doanh thu) cũ, thêm khối "Kế hoạch → Thực tế" mới (5 KPI, màu accent
  CHỈ tái dùng 4 token đã có — primary/warning/success/danger/muted,
  không thêm màu mới) + 2 `chart-section` (Chart.js `line` cho xu hướng,
  lần đầu dùng `doughnut` cho cơ cấu loại heo — cùng thư viện CDN đã có
  tiền lệ ở `gia_heo.html`, không rủi ro mới) + bảng theo ngày (tái dùng
  `.admin-table`, tự lọc bớt ngày toàn-0 ở tầng hiển thị, biểu đồ vẫn
  nhận đủ mọi ngày kể cả 0 để trục liền mạch). File JS mới
  `dashboard.js` (trang này trước không có JS riêng). Thêm 2 utility
  class `.text-danger`/`.text-success` (khác `.plan-up`/`.plan-down` đã
  có — 2 class đó cố ý đảo màu theo "tốt/xấu cho người bán", không tái
  dùng được cho dấu số học trực tiếp).

**Verify**: route mới xác nhận đúng qua Flask test-client trên dữ liệu
thật (số khớp tính tay, gate permission đúng — role không quyền không
thấy exception mới, role farm chưa gán trại trả về 0 sạch không crash),
route hoàn toàn chỉ ĐỌC nên không cần backup/dọn dữ liệu. Verify UI qua
scratch page (dữ liệu mẫu lấy thẳng từ output test-client thật, xoá sau
khi xong): 5 KPI tile, 2 biểu đồ, bảng theo ngày render đúng; dropdown
đổi ngày hoạt động (7 ngày rỗng hiện đúng thông báo "chưa có dữ liệu",
90 ngày kịch bản xuất vượt kế hoạch hiện đúng số dương + `text-success`
xanh); badge "Có sai lệch" chỉ hiện cho ngày ĐÃ QUA, ngày tương lai chưa
xuất hết không bị báo sai lệch nhầm; mobile 375px bảng cuộn ngang gọn
trong khung, không phá layout trang. Đối chiếu row-count DB trước/sau —
không đổi (đúng như dự kiến, route thuần đọc).

**2026-08-19, Giai đoạn 4 — Trang "Đối soát" riêng (triage toàn bộ kế
hoạch cần xử lý chênh lệch).** Trước đây chỉ xem được top-5 kế hoạch cần
đối soát qua khối "Cần xử lý" ở Tổng quan (không lọc/tìm được) hoặc lướt
từng thẻ trên `/ke-hoach`. **Không cần route/schema backend mới** —
`GET /api/plans` (có sẵn từ Giai đoạn 1-3) đã trả đủ mọi field
(`reconciliation_status`, `remaining_to_reconcile`, `reconciliation_breakdown`...).

- Route mới `GET /doi-soat` (`webapp/routes/plans.py`, cùng file với
  `plans_page`/`allocations_page`) — gate theo đúng tập quyền
  `_VIEW_PLAN_RECONCILE_PERMS` đã có (`PLAN_REVIEW`/`PLAN_RECEIVE`/
  `PLAN_EDIT`/`PLAN_RECONCILE_CREATE`, bất kỳ quyền nào). Route đặt SAU
  chỗ định nghĩa `_VIEW_PLAN_RECONCILE_PERMS` trong file (không phải đặt
  cạnh `plans_page`/`allocations_page` ở đầu file như dự định ban đầu) —
  Python decorator chạy lúc load module nên tên phải đã tồn tại trước đó.
- Template mới `doi_soat.html` + JS mới `doi_soat.js` — khuôn 1:1 "Nguồn
  cung có thể bán" (`allocations.html`/`allocation.js:
  applyAvailablePlanFilters`): fetch `/api/plans` 1 lần, lọc client-side
  (trại/loại heo/trạng thái đối soát/khoảng ngày/tìm kiếm), render
  `.admin-table.admin-table-responsive`. Dải tóm tắt 3 số (Cần đối
  soát/Đang trong hạn/Đã đối soát) tái dùng nguyên 3 class màu
  `.kpi-approved/.kpi-pending/.kpi-sold` đã có — không thêm màu mới. Mặc
  định lọc "Cần xử lý" (needs_reconciliation + in_progress), có thể
  chuyển "Tất cả" để xem lịch sử đã đối soát.
- **Quyết định kiến trúc quan trọng**: trang mới KHÔNG nhúng lại modal
  "Xử lý chênh lệch" (đã có ở `plan.js`/`plans.html`) — nút hành động
  link sang `/ke-hoach?highlight=<id>&action=reconcile`, mở đúng modal
  đó từ xa. `plan.js`'s `highlightFromQuery()` (đã có, dùng cho
  `?highlight=` từ khối Cần xử lý ở Tổng quan) mở rộng thêm ~8 dòng đọc
  `?action=reconcile` → gọi `openReconcileModal(id)` nếu có quyền. Lý do
  không nhúng modal: codebase chưa có tiền lệ "module modal dùng chung"
  (incident modal chỉ ở `allocation.js`, reconcile modal chỉ ở
  `plan.js`) — tách modal dùng chung là 1 kiến trúc mới, rủi ro hơn hẳn
  so với thêm 1 query param vào hàm đã có.
- Nav (`base.html`): thêm đúng 1 link "Đối soát" (khuôn `if
  current_user_can(...)` y hệt link "Kế hoạch bán"), **không** phải phần
  đổi nav sang sidebar (vẫn để sau).

**Verify**: Flask test-client xác nhận route/gate đúng (admin 200, role
không quyền 302 redirect, link nav ẩn/hiện đúng theo quyền). Browser
scratch page (dữ liệu mẫu đủ 4 trạng thái + 1 kế hoạch pending_approval
để xác nhận bị lọc bỏ hoàn toàn): 3 số tóm tắt đúng, filter lọc đúng
theo từng tiêu chí, breakdown "Đã loại 3" hiện đúng khi đã đối soát,
link hành động đúng URL. Verify riêng `action=reconcile` bằng scratch
page thứ 2 (dữ liệu mẫu khớp plan 16 thật): modal tự mở đúng kế hoạch
khi có `action=reconcile` + đủ quyền, KHÔNG tự mở khi thiếu `action`
hoặc thiếu quyền (cả 2 trường hợp âm đều xác nhận qua browser thật, không
chỉ đọc code) — không phá hành vi `?highlight=` cũ. Route mới thuần
render (không query DB), không cần backup.

**2026-08-19, Giai đoạn 5 — Trang "Báo cáo" (trung tâm xuất Excel).**
Khoảng trống xác nhận qua grep (không có `bao_cao`/"Báo cáo" ở đâu
trong `webapp/` trước đó): 3 export Excel đã có (Giá heo hơi/Kế hoạch
trại/Kế hoạch bán) nằm rải rác mỗi cái 1 nút nhỏ ở 1 trang không liên
quan, không có nơi liệt kê "có báo cáo gì". Route mới `GET /bao-cao`
(`webapp/routes/plans.py`, cạnh `doi_soat_page`) + template tĩnh
`bao_cao.html` (3 `.card` xếp dọc, mỗi card mô tả ngắn nội dung export +
nút trỏ thẳng route export cũ qua `url_for` — `plans.export_plans_excel`/
`plans.export_orders_excel`/`prices.export_excel`, xác nhận đúng tên
endpoint trước khi dùng, không đoán). **Không gate permission riêng** —
xác nhận cả 3 route export đích từ trước tới giờ cũng không hề gate
(chỉ cần đăng nhập), gate riêng trang hub sẽ tạo ra sự khác biệt vô lý
(thấy link nhưng route đích lại mở được, hoặc ngược lại). Cố ý KHÔNG
thêm báo cáo tổng hợp mới hay filter khoảng ngày cho export — Dashboard
+ trang Đối soát (Giai đoạn 3-4) đã phủ hết nhu cầu xem tổng hợp/xu
hướng, thêm nữa sẽ trùng lặp. 3 nút export tại chỗ ở 3 trang cũ giữ
nguyên, trang Báo cáo là điểm gộp bổ sung chứ không thay thế. Thêm 1
nav link "Báo cáo" (ungated, khớp route) sau link "Đối soát".

**Verify**: Flask test-client — `GET /bao-cao` 200 khi đã đăng nhập, 302
khi chưa (redirect login, khớp hành vi chung của app); trang chứa đúng
3 nút "Xuất Excel" trỏ đúng URL; gọi thật cả 3 route export đích sau khi
thêm trang mới — vẫn 200, không hỏng gì. Trang này thuần Jinja tĩnh
(không JS, không `fetch`) nên phần text-assertion trên đã là xác minh
đầy đủ — không cần thêm bước browser/screenshot (không có hành vi
client-side nào để kiểm ngoài phần đã kiểm qua HTML render).

---

**2026-08-19, Giai đoạn 6 — Sidebar desktop, giữ nguyên mobile (việc
cuối trong brief lớn).** Trước khi làm, phát hiện app **chưa từng có
"chế độ desktop rộng"**: `main`/`.topbar-inner` đều `max-width: 960px`,
`.topbar-nav` mặc định `display:none` ở MỌI kích thước màn hình, chỉ
hiện qua checkbox ☰ — tức bản thân "desktop" trước đây cũng chỉ là
layout mobile 1 cột thu nhỏ. Người dùng xác nhận muốn **2 thiết kế tách
riêng** (không phải bolt-on): desktop dùng sidebar cố định bên trái,
full màn hình; mobile giữ nguyên y hệt hành vi cũ (đã verify kỹ suốt
Giai đoạn 1-5, không muốn động vào).

Giải pháp thuần CSS, chỉ sửa `webapp/static/css/style.css` — 1 khối
`@media (min-width: 1024px)` mới, **không sửa `base.html`/JS/route
nào**: tái dùng nguyên DOM `.topbar-inner` (brand → nav → actions) sẵn
có, chỉ đổi `flex-direction: row → column` + `.topbar{position:fixed;
width:250px}` để biến topbar thành sidebar dọc; `main`/`footer` được
đẩy sang phải qua `margin-left:250px` và nới `max-width` lên 1800px.
Toàn bộ CSS <1024px giữ nguyên tuyệt đối (khối mới chỉ ghi đè thêm ở
màn rộng). Đặt `order: initial` lại cho `.topbar-nav`/`.topbar-actions`
để trả về đúng thứ tự DOM gốc (brand→nav→actions) khi xếp dọc — 2 rule
này vốn có `order: 2`/`order: 3` chỉ để xếp hàng ngang đúng thứ tự trên
mobile, nếu không reset sẽ đảo lộn khi xếp cột.

**Bug thật phát hiện khi verify (không phải chỉ đọc code)**: đặt khối
media-query lần đầu ở TRƯỚC rule gốc `main{margin:0 auto;max-width:960px}`
trong file — cùng specificity (chỉ selector phần tử), rule gốc đứng SAU
trong file thắng cascade bất kể nằm trong media query hay không, khiến
`margin-left`/`max-width` mới bị ghi đè mất, sidebar hiện đúng nhưng
`main` vẫn kẹt ở giữa 960px cũ (đo được qua `getComputedStyle` khi verify
ở viewport 1280px: `marginLeft` ra `152.5px` — giá trị auto-margin cũ —
thay vì `250px`). Fix: chuyển hẳn khối media-query xuống cuối file
(`style.css`) để chắc chắn thắng cascade so với mọi rule base cùng
specificity ở trên, không phải sửa từng thuộc tính riêng lẻ.

**Verify**: dump HTML thật của 5 trang đại diện (Tổng quan/Kế hoạch
trại/Kế hoạch bán/Đối soát/Báo cáo) qua Flask test-client +
`session_transaction()` giả session admin (không đụng mật khẩu thật),
lưu vào `webapp/static/_scratch_*.html` để mở qua chính server đang chạy
thật (xác nhận luôn: server không cần restart để nhận CSS/static mới) —
xoá sạch sau khi xong. Ở 1280px: `getBoundingClientRect()` xác nhận
sidebar (x=0,w=250,h=full viewport) và `main` (x=250) không chồng nhau;
`.plan-form` (grid `auto-fit, minmax(260px,1fr)`) tự co thành 3 cột thay
vì 1 cột dài; bảng ở Kế hoạch bán không tràn ngang; nav active-state
đúng ở cả 5 trang. Ở 768px/375px: `topbar.position` về lại `static`,
`.topbar-nav` về lại `display:none`, `main.marginLeft` về lại `0px` —
xác nhận **y hệt** hành vi trước khi sửa; bấm thử checkbox ☰ qua JS vẫn
mở được menu bình thường. Không cần backup DB (đổi CSS thuần tuý, không
đụng dữ liệu).

---

**2026-08-19, Giai đoạn 7 — Bố trí lại nội dung trang Tổng quan thành 2
cột ở desktop (theo ảnh mẫu người dùng gửi).** Ảnh mẫu dashboard ERP có
biểu đồ xu hướng + biểu đồ cơ cấu nằm cạnh nhau, bảng theo-ngày + khối
cảnh báo nằm cạnh nhau. Trang Tổng quan thật (8 `<section class="card">`
xếp dọc 1 cột trong `main{display:flex;flex-direction:column}`) chưa
làm vậy dù `main` đã rộng ra tới 1800px từ Giai đoạn 6. **Phạm vi cố ý
giữ hẹp — chỉ bố trí lại, không re-skin**: không thêm filter bar
trại/khách hàng/loại heo (cần sửa backend), không đổi topbar (vừa xong
Giai đoạn 6), không redesign kiểu thẻ KPI (icon tròn, tooltip).

Kỹ thuật: bọc 2 cặp section liền kề (biểu đồ; bảng+cảnh báo) trong
`<div class="dashboard-charts-row">`/`<div class="dashboard-lower-row">`
— CSS mặc định `display: contents` (wrapper không tạo box, con thành
flex-item trực tiếp của `main` y hệt trước khi có wrapper, nên <1024px
**không đổi 1 pixel**), chuyển `display: grid` (2fr/1fr và 3fr/2fr, có
`minmax(0,...)` chặn canvas/table đẩy bung track) chỉ ở
`@media(min-width:1024px)`, nối cuối `style.css` sau khối sidebar Giai
đoạn 6 (cùng lý do thắng cascade). Thêm class `kpi-grid-primary` cho
riêng hàng 5 KPI chính ("Kế hoạch → Thực tế") để ép `repeat(5,1fr)` ở
desktop thay vì để `auto-fit,minmax(170px,1fr)` tự quyết (có thể wrap
4+1 tuỳ bề rộng màn hình thật) — khớp đúng "gọn gàng" ảnh mẫu ở mọi độ
rộng. Không sửa `dashboard.js`: đã đọc kỹ, không có code resize/redraw
thủ công nào, Chart.js 4 `responsive:true` tự dùng `ResizeObserver` đọc
container mới và tự vẽ lại — xác nhận qua verify (xem dưới), không phải
suy đoán.

**Cách verify chart khi container đổi bề rộng — lưu ý cho lần sau**:
trang scratch dump qua test-client không có cookie session thật của
trình duyệt, nên `fetch('/api/dashboard/summary')` phía `dashboard.js`
luôn 401 và chart không bao giờ tự vẽ qua luồng thật. Thay vì chấp nhận
giới hạn này (đủ cho việc kiểm layout/markup thuần), lần này gọi thẳng
`renderTrendChart(fakeDaily)`/`renderCompositionChart(fakeComposition)`
(hàm global trong `dashboard.js`, có sẵn sau khi script load) với dữ
liệu giả nhỏ qua `javascript_tool` để ép Chart.js thực sự khởi tạo và
đo `getBoundingClientRect()` của canvas — xác nhận canvas co đúng theo
container mới (570px trong khối 612px rộng; 264px trong khối 306px
hẹp), không chỉ suy luận từ tài liệu Chart.js.

**Verify**: `getBoundingClientRect()` ở 1280px xác nhận 2 wrapper xếp
đúng hàng ngang tỉ lệ ~2:1 và ~3:2, `.kpi-grid-primary` đúng 5 thẻ 1
hàng (5 vị trí x khác nhau cùng y); ở 768px/375px xác nhận cả 2 wrapper
trả về `display:contents` và toàn bộ 8 section vẫn full-width xếp dọc
đúng thứ tự, cùng độ rộng như trước khi sửa (phép kiểm hồi quy quan
trọng nhất). Screenshot xác nhận trực quan khớp bố cục ảnh mẫu ở cả 2
khối ghép cột.

**Cùng ngày, ngay sau đó — xoá section "Số liệu chính"** (người dùng:
"đó là thiết kế cũ"). Grep xác nhận `stats`/`dashboard_stats()` chỉ
phục vụ đúng section này, không nơi nào khác dùng — dọn sạch luôn thay
vì để lại code chết: xoá section trong `dashboard.html`, xoá
`stats=dashboard_stats_locked(...)` khỏi route `dashboard.index()`
(`webapp/routes/dashboard.py`), xoá `dashboard_stats_locked()`
(`webapp/data_access.py`), xoá `dashboard_stats()`
(`core/repositories/sale_plans_repo.py`). CSS accent `.kpi-tile.kpi-
revenue` cũng xoá (chỉ tile này dùng, còn `kpi-pending`/`kpi-approved`/
`kpi-sold` **giữ nguyên** vì `doi_soat.html` đang tái dùng 3 class màu
này cho summary strip riêng của nó — xác nhận qua grep trước khi xoá,
không xoá nhầm CSS còn dùng). Xác nhận qua test-client (`/` vẫn 200) +
browser (section biến mất, 2 khối ghép cột Giai đoạn 7 phía dưới không
đổi vị trí tương đối, chỉ dịch lên do bớt 1 section phía trên).

---

**2026-08-19, redesign "Danh sách kế hoạch trại" + "Danh sách đơn hàng":
card cao → bảng rút gọn + modal "Xem chi tiết".** Người dùng phản hồi bố
trí dạng `.plan-card` (8-14 dòng thông tin luôn hiện/thẻ) "không hợp lý
và chuyên nghiệp", muốn dạng bảng danh sách ERP, chỉ xem chi tiết khi
bấm vào. Yêu cầu cụ thể: bảng chỉ hiện thông tin nhận diện/lọc/trạng
thái/1 hành động chính, còn lại (stepper/dòng hàng/đối soát/doanh thu/
metadata) vào modal chi tiết; mobile tái dùng `.admin-table-responsive`
có sẵn (không xây component riêng); mở chi tiết **chỉ qua nút "Chi
tiết"** (không bấm cả dòng — tránh cản trở copy chữ). Đảo ngược có chủ
đích 1 quyết định cũ (mục "Redesign trang Kế hoạch bán" ở trên: giữ dạng
thẻ cho đơn hàng vì "ép vào 1 hàng bảng sẽ mất thông tin") — modal chi
tiết giải quyết đúng lo ngại đó vì không mất thông tin, chỉ chuyển sang
xem theo yêu cầu. Thuần frontend, không đổi DB/route/API payload.

**`core/modal.js`** (+1 hàm `detailModal({title, bodyHtml, actionsHtml})`,
cạnh `confirmModal`/`promptModal` có sẵn): box rộng hơn
(`min(680px,94vw)`, cuộn dọc), nhận HTML tuỳ ý thay vì 1 đoạn ngắn, có
action bar riêng. Lưu hàm đóng thẳng lên phần tử DOM
(`overlay._detailModalClose`) để 2 trang tự đóng modal từ trong
delegated click handler mà không cần biến state riêng.

**Bug thật phát hiện khi thiết kế (trước khi code, qua review kiến
trúc)**: 6 modal hành động tĩnh sẵn có (`#reconcile-modal`,
`#sale-details-modal`...) nằm trong `<main>`, đứng TRƯỚC modal chi tiết
mới (append cuối `<body>`) trong DOM order — cùng `z-index:100`, nếu mở
modal chi tiết rồi bấm 1 action mở tiếp modal tĩnh, modal tĩnh sẽ bị đè
khuất phía sau. Fix 1 lần duy nhất: đầu `handlePlanListClick`/
`handleOrderListClick` tự đóng modal chi tiết đang mở trước khi dispatch
bất kỳ action nào (không phải sửa từng hàm hành động).

**`plan.js`/`allocation.js`**: `renderPlans()`/`renderOrders()` (render
card) thay bằng `renderPlansTable()`/`renderOrdersTable()` (1 `<tr>`/
hàng: mã/trại/loại heo/ngày/số lượng/trạng thái[+đối soát]/1 nút hành
động chính/nút "Chi tiết") + `planDetailBodyHtml()`/
`orderDetailBodyHtml()` (tái dùng NGUYÊN VẸN `planStepperHtml`/
`planReconcileHtml`/`orderStepperHtml`/`lineHtml`/`deliverySectionHtml`/
`incidentSectionHtml` — chỉ đổi nơi các hàm này được gọi, không đổi nội
dung) cho phần thân modal. **`orderPrimaryAction()` — hàm mới**, khuôn
`planPrimaryAction()` đã có, chọn đúng 1 nút/hàng theo ưu tiên khớp 4
bước stepper (Chốt bán hàng → Đã bán → Ghi nhận doanh thu → Kích hoạt
lại) — trước đó `renderOrders()` render tới 6 nút cùng lúc, không có
khái niệm "1 action chính". "🔒 Khoá đơn hàng" cố ý không bao giờ là
primary (admin-only/hiếm dùng), luôn ở action bar modal. Click-delegation
đổi từ bind vào `#plan-list`/`#order-list` sang `document.body` — để
cùng 1 hàm dispatch xử lý y hệt dù nút nằm trong hàng bảng hay trong
modal chi tiết (modal append vào `document.body`, ngoài 2 container cũ),
không cần viết lại logic action nào. `highlightFromQuery()` (2 trang) đổi
neo từ `.closest(".plan-card")` sang `tr[data-id]`, và **mở luôn modal
chi tiết** thay vì chỉ pulse-highlight khi đến từ `?highlight=<id>` (hàng
rút gọn không còn đủ thông tin như card cũ) — case `?action=reconcile`
(từ `doi_soat.js`) giữ nguyên mở `#reconcile-modal` trực tiếp, không đổi.
2 bảng có sẵn (Nguồn cung/Giỏ nháp ở `allocations.html`, cả bảng ở
`doi_soat.html`) và luồng thêm dòng/tạo đơn không đụng.

**CSS** (`style.css`, nối cuối file theo đúng quy ước cascade đã có):
`.detail-modal*`, `.admin-table-clickable` (hover nhẹ, KHÔNG
`cursor:pointer` cả hàng — chỉ nút "Chi tiết" mở được, đúng lựa chọn
người dùng), `.admin-table-actions`. `tr.is-highlighted` đổi từ
`box-shadow` (không đáng tin cậy trên `<tr>` có `border-collapse`) sang
`background-color` pulse riêng cho ngữ cảnh bảng — `.is-highlighted`
gốc (box-shadow) giữ nguyên cho các `.plan-card` còn lại (dòng hàng
trong modal).

**Verify**: Flask test-client (session giả `role: admin`) — `/ke-hoach`,
`/ke-hoach-ban`, `/doi-soat`, `/`, `/bao-cao` đều 200; `/api/plans`/
`/api/orders` trả dữ liệu thật y hệt trước (không route nào bị đụng).
Browser qua 2 trang tĩnh tạm (`webapp/static/_verify_plans.html`/
`_verify_orders.html`, xoá sau khi xong, dùng `.claude/launch.json` mới
thêm để chạy dev server thật trên port phụ — port 5000 đang là server
production thật, không đụng): đủ 7 trạng thái kế hoạch trại (kể cả
`over_delivered`/`reconciled` có breakdown/lệch cơ cấu) và 6 trạng thái
đơn hàng (active có/chưa sale-details, done có/chưa doanh thu, disabled,
cancelled) — xác nhận đúng primary action từng trường hợp, badge/stepper/
breakdown hiện đúng trong modal, toggle dòng hàng + khối xuất giao/loại-
hủy hoạt động đúng trong modal, action bấm từ modal tự đóng modal trước
(xác nhận fix z-index), `?highlight=<id>` (có/không `action=reconcile`)
mở đúng modal. Xác nhận cơ chế responsive `.admin-table-responsive`
(CSS `@media max-width:640px`, đã có sẵn từ trước — không sửa) áp dụng
đúng lên 2 bảng mới qua kiểm tra `CSSMediaRule` trực tiếp (resize viewport
thật không khả dụng trong phiên trình duyệt này). Thêm mới
`.claude/launch.json` (chạy `webapp/app.py` qua Python có cài `waitress`
— máy có 2 bản Python, chỉ 1 bản cài đủ dependency, đã trỏ đường dẫn
tuyệt đối) để lần sau verify bằng browser không phải dò lại.

**Cùng ngày, ngay sau khi lên thật — sửa gap UX phát hiện qua phản hồi
thật của người dùng: lịch sử đối soát "Còn tại trại"/"Tiếp tục bán" bị
ẩn hoàn toàn.** Người dùng bấm "Xử lý chênh lệch" cho kế hoạch
`XH1-20260817-01` (300 con, đã bán 200, còn 100 chưa xử lý), chọn
"Tiếp tục bán", nhưng trạng thái vẫn "Cần đối soát" — hỏi tại sao. Tra
dữ liệu thật qua `/api/plans` xác nhận đúng thiết kế cũ (`_apply_
reconciliation_status`): `still_at_farm`/`continue_selling` là 2 kind
CỐ Ý không đóng chênh lệch (chỉ là ghi chú "chưa xong"), nên
`remaining_to_reconcile` không đổi — nhưng phát hiện thêm 1 gap thật:
`planReconcileHtml()` (plan.js) chỉ hiện `reconciliation_breakdown` khi
`isComplete` (nhánh "reconciled"), nên với kế hoạch còn "Cần đối soát",
bản ghi "Tiếp tục bán: 300 con" đã lưu **hoàn toàn vô hình** trên UI dù
`reconciliation_breakdown` backend vẫn trả về đầy đủ bất kể trạng thái
— người dùng không có cách nào biết mình đã ghi nhận gì trước đó, dễ
bấm ghi lại nhiều lần trùng lặp.

Fix (thuần frontend, không đổi API/schema): tách phần hiện
`reconciliation_breakdown` ra khỏi nhánh `isComplete`, hiện **không điều
kiện** mỗi khi `breakdown.length > 0` (mục "Đã ghi nhận" trong modal chi
tiết), kèm chú thích "(chưa đóng chênh lệch)" cho 2 kind
`still_at_farm`/`continue_selling` (hằng mới `RECONCILE_NON_CLOSING_
KINDS`) để không gây hiểu nhầm "đã ghi mà sao vẫn báo cần xử lý".
`openReconcileModal()` cũng thêm dòng "Đã ghi nhận trước" vào
`#rc-summary` — hiện ngay lịch sử trước khi người dùng ghi thêm 1 bản
mới, giải quyết đúng lo ngại người dùng nêu ("bấm nhiều lần vào đối
soát do không nhớ đã đối soát rồi"). Verify qua trang tĩnh tạm với đúng
dữ liệu thật của kế hoạch 16 (xoá sau khi xong): cả modal chi tiết lẫn
modal "Xử lý chênh lệch" đều hiện đúng "Tiếp tục bán: 300 con (chưa
đóng chênh lệch)"/"Đã ghi nhận trước".

### 7. Enterprise Refactor — Service Layer (STEP 1/STEP 4, 2026-08-19)

Thực hiện theo `PIG_PRICE_ENTERPRISE_REFACTOR_CONTEXT.md` (lộ trình 12
STEP, không rewrite toàn bộ, không đổi framework, không PostgreSQL, không
microservices). Đã hoàn tất STEP 1 (Database Hardening) + STEP 4
(Transaction Standardization, dưới dạng Service Layer) cho **toàn bộ**
domain ghi dữ liệu của app — kể cả mảng quản trị. Branch
`refactor/enterprise-foundation`.

**Kiến trúc mới — Route → Service → Repository**:
- **Route** (`webapp/routes/*.py`): chỉ còn lo HTTP — đọc `request`/
  `session`, validate input, gọi service, `jsonify`/`redirect`. Không tự
  mở transaction, không tự gọi `log_audit()` cho các hành động đã có
  service (trừ 1 ngoại lệ có ghi chú trong code:
  `plans.py` tạo đối soát kèm ảnh — audit cần biết số ảnh, chỉ biết được
  *sau* khi service đã tạo bản ghi và upload file xong, nên tách audit
  ra ngoài transaction một cách có chủ đích).
- **Service** (`core/services/*_service.py`, mới — trước đây không có
  tầng này): mỗi hành động ghi là 1 hàm gộp đúng **1 lần ghi repo + 1 lần
  `audit_repo.log_action()` vào chung 1 transaction** qua
  `core/db.py::run_in_transaction(db_path, fn)` — đóng lỗ hổng cũ "ghi
  xong nhưng audit lỗi thì mất vết" (route trước đây gọi
  `xxx_locked()` rồi `log_audit()` rời, không atomic). Validate nghiệp vụ
  (trùng mã, quan hệ tham chiếu, tự xoá chính mình, role hệ thống...) vẫn
  ở route layer — service chỉ lo transaction + audit, chưa gánh validate.
- **Repository** (`core/repositories/*_repo.py`): mỗi hàm ghi được thêm
  tham số `conn: sqlite3.Connection | None = None` tuỳ chọn, cùng khuôn
  `own_connection = conn is None` — nếu gọi không kèm `conn` thì tự mở/
  đóng/commit connection riêng như trước (100% tương thích ngược,
  `data_access.py` `*_locked()` gọi thẳng không cần đổi gì); nếu được
  truyền `conn` (từ service) thì dùng chung connection đó, không tự
  commit/close, để nhiều lệnh ghi + audit gộp chung 1 transaction thật.

**`core/db.py`**: thêm `db_lock` (chuyển từ `webapp/extensions.py` sang,
1 `threading.Lock()` toàn app), `transaction(conn)` (contextmanager
`BEGIN`/commit/rollback, no-op nếu `conn.in_transaction` đã `True`), và
`run_in_transaction(db_path, fn)` — mở 1 connection dưới `db_lock`, chạy
`fn(conn)` trong 1 `transaction()`, đóng connection; đây là hàm dùng
chung của **mọi** service (`_write = run_in_transaction` ở đầu mỗi file
service). PRAGMA `foreign_keys` cũng đã bật (STEP 1).

**Domain đã migrate xong** (mỗi domain đều có integration test riêng ở
gốc repo, `test_api_<domain>_tmp.py`, giữ lại làm nền cho `tests/` thật
sau này — STEP 6):
- `plan_service.py` — `sale_plans` + `sale_plan_reconciliations` (tạo/
  duyệt/từ chối/đổi trạng thái/ghi nhận thực nhận/sửa/xoá kế hoạch trại,
  tạo/xoá đối soát).
- `order_service.py` — `sale_allocations` (kế hoạch bán/đơn hàng): tạo
  đơn, thêm/sửa/xoá dòng, đổi trạng thái, khoá, hoàn tất, cập nhật thông
  tin bán hàng/doanh thu.
- `delivery_service.py` — `sale_deliveries` (tạo/xoá bản ghi giao hàng).
- `customer_service.py` — `customers` (tạo/sửa/bật-tắt/xoá).
- `authorization_service.py` — tách phần **đọc** quyền hạn (không phải
  ghi, không dùng `run_in_transaction`) ra khỏi `webapp/routes/auth.py`
  thành hàm thuần (`effective_permissions`/`has_permission`/
  `has_any_permission`/`allowed_farm_ids`, nhận `user: dict | None` thay
  vì đọc thẳng Flask `session`) — `auth.py` giữ nguyên các hàm/decorator
  cũ làm wrapper mỏng gọi vào đây, không đổi API cho 6 file đang import.
- `user_service.py` — quản trị tài khoản: tạo, đổi vai trò, gán trại,
  bật/tắt, đặt lại mật khẩu, xoá.
- `farm_service.py` — danh mục Trang trại/Khu: tạo/sửa/xoá farm, tạo/
  sửa/xoá zone.
- `pig_type_service.py` — danh mục Loại heo bán: tạo/sửa/bật-tắt/xoá.
- `role_service.py` — Vai trò & phân quyền tuỳ biến: tạo/xoá role, cập
  nhật tập quyền của role.

**Lưu ý kỹ thuật khi viết test cho domain mới** (đã gặp 2 lần, tốn thời
gian debug): (1) hàm insert-rồi-đọc-lại trong repo phải đọc lại qua
**cùng** `conn` được truyền vào (không mở connection mới) — SQLite WAL
không thấy được dữ liệu chưa commit từ 1 connection khác dùng chung
transaction; (2) module nào tự `from extensions import DB_PATH` ở top
level (import bởi `app_factory.py` cũng ở top level, không phải lazy
trong `create_app()`) thì test phải patch `DB_PATH` riêng trên module đó
(`routes.admin.DB_PATH = test_db`, không chỉ `extensions.DB_PATH`) — patch
timing, không phải bug thật. `webapp/routes/auth.py` cũng dính lớp bug
này (`current_user_permissions()` dùng `DB_PATH` module-level), nhưng
mãi tới khi viết test cho STEP 3 (farm-scope, dưới đây) mới lộ ra — mọi
test trước luôn dùng session role `admin`, escape hatch hardcode
`admin` = full quyền trong `roles_repo.effective_permissions` không phụ
thuộc DB nên che mất bug.

**STEP 3 — Authorization + Data Scope (2026-08-19)**: rà soát toàn bộ
route ghi trên `sale_plans`/reconciliation/delivery (nơi duy nhất tài
khoản vai trò `farm` thao tác — `sale_allocations`/đơn hàng là domain
sales/accounting, không scope theo farm, xác nhận đúng thiết kế) thì
thấy **6/10 hành động không kiểm tra farm-scope** dù thao tác trên 1 bản
ghi cụ thể có `farm_id`, chỉ dựa vào permission gate
(`@permission_required`) — 1 admin lỡ cấp nhầm 1 trong các quyền
`plans.review`/`plans.delete`/`plans.reconcile_delete`/
`plans.delivery_delete` cho role `farm` qua `/admin/permissions` (chưa
xảy ra trong DB thật, đã xác nhận) sẽ khiến user vai trò farm thao tác
được trên **bất kỳ trại nào**, không chỉ trại được gán. Đã thêm guard
`allowed_farm_ids()` (khuôn có sẵn, lặp lại y hệt) vào
`api_plans_approve`/`api_plans_reject`/`api_plans_update`/
`api_plans_delete`/`api_plan_reconciliation_delete` (`plans.py`) và
`api_delivery_delete` (`deliveries.py`) — thuần route layer, không đổi
service/repository/permission catalog/UI. Verify bằng
`test_api_farm_scope_tmp.py`: cấp tạm 4 quyền trên cho role `farm` trên
DB test, mô phỏng đúng tình huống rủi ro với 2 tài khoản farm (đúng/sai
trại).

### 8. STEP 5 — Security Hardening (2026-08-19)

7 hạng mục P0 theo mục 17 tài liệu refactor. Đã xác nhận với người dùng:
app có cả truy cập LAN trực tiếp (HTTP) lẫn qua Cloudflare Tunnel
(HTTPS) → không thể ép `Secure` cookie vô điều kiện; đồng ý thêm
`flask-wtf`/`flask-limiter`; secret key lưu file cục bộ gitignore.

- **Secret key bền vững**: trước đây `secrets.token_hex(32)` sinh random
  mỗi lần khởi động (mọi phiên mất hiệu lực khi restart) — nay đọc/tạo
  từ `webapp/secret_key.txt` (gitignore, khớp cách `webapp/password.txt`
  đang làm).
- **Session cookie**: `HTTPONLY=True`, `SAMESITE=Lax` (an toàn cả LAN
  lẫn Tunnel); `SECURE` tuỳ biến qua env `SESSION_COOKIE_SECURE=1`, mặc
  định `False` — nếu sau này khẳng định 100% truy cập qua Tunnel HTTPS,
  chỉ cần set biến môi trường, không cần sửa code.
- **CSRF**: `CSRFProtect(app)` (flask-wtf) bảo vệ toàn bộ route ghi tự
  động. Thay vì sửa tay 66+ lệnh `fetch()` rải rác ở 10 file JS
  (`plan.js`/`allocation.js`/`admin_*.js`...), dùng 1 file mới
  `webapp/static/js/core/csrf.js` **monkey-patch `window.fetch` toàn
  cục** (đọc token từ `<meta name="csrf-token">`, tự thêm header
  `X-CSRFToken` cho mọi request same-origin) — nạp trước `core/api.js`
  trong `base.html`, không `defer` (đúng quy ước thứ tự script ở mục
  I.6). Nhờ vậy không cần sửa dòng nào ở 10 file JS domain hiện có. 2
  form HTML thường (`login.html`, form đăng xuất trong `base.html`)
  thêm `{{ csrf_token() }}` hidden field riêng.
- **Login rate limiting**: `flask-limiter` (in-memory, đủ 1 máy),
  `@limiter.limit("10 per minute")` trên route `login()`.
- **Test client**: 9 `test_api_*_tmp.py` phải thêm
  `app.config["WTF_CSRF_ENABLED"] = False` (test client gọi thẳng
  `client.post(json=...)`, không qua `fetch()`/`csrf.js` nên không có
  token).
- **Ngoài phạm vi** (có lý do, xem plan lúc thực hiện): không sửa
  `ProxyFix` (rủi ro còn lại chỉ ảnh hưởng độ chính xác IP trong
  `audit_log`, không bypass auth/permission/data-scope); không thêm
  session timeout (quyết định UX, chưa hỏi); không migrate 66 `fetch()`
  sang dùng `core/api.js` (nằm ngoài phạm vi CSRF).

---

## III. Đề xuất thiết kế mở rộng

### 0. Nguyên tắc xuyên suốt

- **Additive-only**: mọi thay đổi dưới đây là `CREATE TABLE IF NOT EXISTS` mới
  hoặc `ALTER TABLE ADD COLUMN` — không đổi kiểu cột, không xoá cột cũ, không
  bắt buộc dựng lại bảng như đợt tách `sale_plans`/`sale_allocations` (đợt đó
  tự nhận "rủi ro cao" trong code) — **không lặp lại kiểu rủi ro đó** cho
  domain đang chạy ổn định trừ khi thật sự cần.
- **`sale_plans`/`sale_allocations` giữ nguyên cột `status` hardcode hiện
  tại** — không di trú sang state machine generic ngay (lý do ở mục III.2).
- Tất cả bảng mới theo đúng convention dự án: `snake_case`, `created_at/
  created_by/created_ip` + `updated_at/updated_by/updated_ip` khi có sửa,
  `INTEGER PRIMARY KEY AUTOINCREMENT`, seed additive (chỉ insert khi bảng
  rỗng) như `farms`/`roles` đang làm trong `core/db.py: _migrate()`.

### 1. Workflow engine generic (state machine tái sử dụng được)

```sql
-- Định nghĩa 1 loại quy trình duyệt (VD 'kpi_bonus_approval',
-- 'material_request_approval', 'incident_review'...). TEXT key (không
-- AUTOINCREMENT) để code tham chiếu bằng hằng số, giống roles.key.
CREATE TABLE IF NOT EXISTS workflow_definitions (
    key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,      -- dùng chung với audit_log/media_proof, VD 'kpi_bonus'
    initial_state TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    note TEXT,
    created_at TEXT NOT NULL
);

-- Trạng thái hợp lệ của 1 workflow. is_terminal để UI biết khi nào ẩn nút
-- hành động (không còn transition đi tiếp).
CREATE TABLE IF NOT EXISTS workflow_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_key TEXT NOT NULL REFERENCES workflow_definitions(key),
    state_key TEXT NOT NULL,
    name TEXT NOT NULL,
    is_terminal INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    UNIQUE (workflow_key, state_key)
);

-- Transition hợp lệ: from_state -> to_state. permission_key tham chiếu TỰ DO
-- (không FK cứng, vì permissions.py là catalog Python, không phải bảng) tới
-- permission_key trong core/permissions.py — tái dùng RBAC hiện có.
CREATE TABLE IF NOT EXISTS workflow_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_key TEXT NOT NULL REFERENCES workflow_definitions(key),
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    action_key TEXT NOT NULL,          -- 'approve','reject','submit','cancel'... nhãn nút hành động
    permission_key TEXT,               -- NULL = không chặn quyền riêng (hiếm dùng)
    requires_reason INTEGER NOT NULL DEFAULT 0,
    requires_media INTEGER NOT NULL DEFAULT 0,  -- bắt buộc >=1 media_proof mới cho transition (vd sự cố)
    UNIQUE (workflow_key, from_state, action_key)
);

-- "Con trỏ" trạng thái hiện tại — CHỈ dùng cho domain MỚI chưa có sẵn cột
-- status riêng (KPI, vật tư...). sale_plans/sale_allocations KHÔNG dùng bảng
-- này (status vẫn nằm tại chỗ) để tránh 1 nguồn sự thật bị tách 2 nơi.
CREATE TABLE IF NOT EXISTS workflow_instances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_key TEXT NOT NULL REFERENCES workflow_definitions(key),
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    current_state TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (workflow_key, entity_type, entity_id)
);

-- Lịch sử duyệt — generic theo entity_type/entity_id, tương tự audit_log
-- nhưng tập trung cho approval (from_state/to_state/action_key có cấu trúc,
-- không phải free-text detail).
CREATE TABLE IF NOT EXISTS workflow_approval_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_key TEXT NOT NULL REFERENCES workflow_definitions(key),
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    from_state TEXT,
    to_state TEXT NOT NULL,
    action_key TEXT NOT NULL,
    actor_username TEXT,
    reason TEXT,
    at TEXT NOT NULL,
    ip TEXT
);
CREATE INDEX IF NOT EXISTS idx_wf_history_entity ON workflow_approval_history(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_wf_history_workflow ON workflow_approval_history(workflow_key);
```

**Vì sao 5 bảng thay vì 1 bảng đơn giản hơn?** Có thể bỏ `workflow_states` và
coi state là chuỗi tự do — đỡ 1 bảng. Nhưng giữ lại vì rẻ (không tốn gì thêm)
và cho phép dựng màn `/admin/workflows` sau này (dropdown trạng thái hợp lệ,
nhãn tiếng Việt, `is_terminal` để ẩn nút) mà không phải hardcode trong
template — cùng triết lý với `roles`/`role_permissions` (dữ liệu thay vì
hardcode).

### 2. Chiến lược áp dụng cho `sale_plans` / `sale_allocations`: KHÔNG di trú ngay

Giữ nguyên `status` hardcode. Lý do:

1. Logic duyệt hiện tại (`approve_sale_plan`, `reject_sale_plan`,
   `update_allocation_status`) gắn chặt với nghiệp vụ cụ thể (scoping theo
   trại, `rejected_reason` bắt buộc, `received_quantity`...) — không phải
   state machine thuần tuý. Ép vào engine generic ngay bây giờ sẽ làm engine
   phình đầy case đặc thù, mất tính "generic".
2. Domain KPI/vật tư là **domain mới, chưa có cột `status`** — chính là nơi
   thử nghiệm engine trước, ít rủi ro nhất, đúng tinh thần additive.
3. Muốn có lịch sử duyệt thống nhất mà không migrate: khi
   `approve_sale_plan()`/`reject_sale_plan()`/`update_allocation_status()`
   chạy, gọi thêm 1 hàm ghi `workflow_approval_history` (dùng
   `workflow_key='sale_plan_approval'` chỉ để làm nhãn hiển thị/thống kê,
   không có `workflow_transitions` nào enforce lên đường đi cũ). Optional,
   không chặn phần còn lại.

Chỉ nên xem lại việc di trú sau khi engine đã chạy ổn với 1-2 domain mới, và
chỉ nếu phát sinh nhu cầu thật (nhiều bước duyệt hơn, chuỗi duyệt cấu hình được).

### 3. `media_proof` — ảnh/video bằng chứng generic

```sql
-- entity_type/entity_id tham chiếu tự do (giống audit_log) tới bất kỳ bảng
-- nghiệp vụ nào: 'sale_allocation' (ảnh cân), 'incident_report' (ảnh/video
-- sự cố), 'logistics_handover' (ảnh biên bản BM04 chụp lại)...
CREATE TABLE IF NOT EXISTS media_proof (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    kind TEXT NOT NULL,           -- 'weigh_tare_photo','weigh_gross_photo','handover_photo','incident_photo','incident_video',...
    file_path TEXT NOT NULL,      -- đường dẫn TƯƠNG ĐỐI tính từ MEDIA_ROOT
    file_size INTEGER,
    mime_type TEXT,
    checksum_sha256 TEXT,         -- phát hiện tái sử dụng 1 file ảnh cho nhiều lần cân khác nhau
    note TEXT,
    uploaded_by TEXT,
    uploaded_at TEXT NOT NULL,    -- LUÔN lấy giờ SERVER, không nhận timestamp client gửi lên
    uploaded_ip TEXT
);
CREATE INDEX IF NOT EXISTS idx_media_proof_entity ON media_proof(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_media_proof_kind ON media_proof(kind);
CREATE INDEX IF NOT EXISTS idx_media_proof_checksum ON media_proof(checksum_sha256);
```

**Lưu file ở đâu?** — đã xác nhận: **lưu đĩa cứng local**
(`BASE_DIR / "data" / "media" / <entity_type> / <entity_id> / <uuid4>_<kind>.<ext>`),
cùng gốc `data/` với `gia_heo_hoi.db` hiện tại (`webapp/extensions.py:
DB_PATH = BASE_DIR / "data" / "gia_heo_hoi.db"`) — thêm hằng số
`MEDIA_ROOT = BASE_DIR / "data" / "media"` cạnh đó. Serve qua route Flask có
kiểm tra quyền (`send_from_directory`), **không** để trong `webapp/static/`
(static không có gate đăng nhập). Tên file dùng UUID, không dùng tên gốc
người dùng upload (tránh path traversal / trùng tên). Không cần trừu tượng
hoá cho cloud storage — giữ đơn giản đúng tinh thần dự án (không premature
abstraction). **Đánh đổi**: script backup thủ công phải backup thêm thư mục
`data/media/`, không chỉ file `.db`.

### 4. `audit_log`: giữ nguyên schema, chỉ thêm action constants

`audit_log` đã đủ generic (`entity_type/entity_id/old_value/new_value`) —
**không cần ALTER thêm cột**. Chỉ thêm hằng số trong `core/audit_actions.py`,
đúng pattern đã có:

```python
DATA_LOCK = "data.lock"              # khoá vĩnh viễn — không có "unlock" (vĩnh viễn = không mở lại)
WEIGHING_TARE_RECORDED = "weighing.tare_recorded"
WEIGHING_GROSS_RECORDED = "weighing.gross_recorded"
WEIGHING_CONFIRMED = "weighing.confirmed"
LOGISTICS_HANDOVER_CONFIRM = "logistics_handover.confirm"
INCIDENT_CREATE = "incident.create"
INCIDENT_RESOLVE = "incident.resolve"
```

`workflow_approval_history` **không thay thế** `audit_log` — hàm
`transition()` của engine generic (mục 6) gọi cả hai: ghi
`workflow_approval_history` (chi tiết có cấu trúc cho riêng approval) **và**
gọi `audit_repo.log_action()` sẵn có (sổ chung). Tránh 2 nguồn sự thật:
`audit_log` = nhật ký mọi hành động; `workflow_approval_history` = chỉ mục
chuyên biệt cho chuyển trạng thái.

### 5. Khoá vĩnh viễn (Data Freeze)

Thêm cột + **trigger DB** (không chỉ check ở tầng Python — SQLite hỗ trợ
trigger, tận dụng để có 1 lớp chặn không thể quên bỏ sót ở repo function nào đó):

```sql
ALTER TABLE sale_plans ADD COLUMN locked_at TEXT;
ALTER TABLE sale_plans ADD COLUMN locked_by TEXT;
ALTER TABLE sale_allocations ADD COLUMN locked_at TEXT;
ALTER TABLE sale_allocations ADD COLUMN locked_by TEXT;

-- Chặn MỌI UPDATE trên dòng đã khoá — trigger chỉ fire khi dòng ĐÃ khoá từ
-- trước (OLD.locked_at IS NOT NULL), nên hành động khoá (NULL -> giá trị)
-- vẫn UPDATE được bình thường; sau khi khoá thì không sửa được nữa.
CREATE TRIGGER IF NOT EXISTS trg_sale_plans_lock_guard
BEFORE UPDATE ON sale_plans
FOR EACH ROW WHEN OLD.locked_at IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'DATA_FROZEN: sale_plans đã khoá vĩnh viễn, không thể sửa');
END;

CREATE TRIGGER IF NOT EXISTS trg_sale_allocations_lock_guard
BEFORE UPDATE ON sale_allocations
FOR EACH ROW WHEN OLD.locked_at IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'DATA_FROZEN: sale_allocations đã khoá vĩnh viễn, không thể sửa');
END;
```

Tầng repository/route bắt `sqlite3.DatabaseError`, nếu message chứa
`"DATA_FROZEN"` thì trả lỗi tiếng Việt thân thiện thay vì lỗi SQL thô. Cách
này mạnh hơn chỉ kiểm tra trong Python vì áp dụng ở tầng DB — không ai (kể cả
code mới viết sau này quên check) vượt qua được.

Hàm khoá (`lock_repo.py`, whitelist tên bảng để tránh SQL injection qua tên bảng):

```python
LOCKABLE_TABLES = {"sale_plans", "sale_allocations", "weighing_records"}

def lock_record(table: str, record_id: int, db_path, ip, username) -> None:
    assert table in LOCKABLE_TABLES
    conn.execute(f"UPDATE {table} SET locked_at = ?, locked_by = ? WHERE id = ? AND locked_at IS NULL",
                 (now, username, record_id))
```

Permission mới: `admin.data_lock.manage` — mặc định chỉ gán role `admin`.

### 6. `incident_reports` — Báo cáo sự cố nhanh

```sql
CREATE TABLE IF NOT EXISTS incident_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_code TEXT,
    allocation_id INTEGER REFERENCES sale_allocations(id),
    weighing_record_id INTEGER REFERENCES weighing_records(id),  -- optional, gắn đúng lần cân nếu sự cố là tranh chấp cân
    farm_id INTEGER REFERENCES farms(id),
    kind TEXT NOT NULL,                -- 'price_reduction','pig_return','weighing_dispute','other'
    description TEXT NOT NULL,
    compensation_amount INTEGER,       -- quy đổi tiền của khoản bù đắp/giảm giá (nếu có)
    status TEXT NOT NULL DEFAULT 'reported',  -- domain MỚI -> dùng workflow_approval_history để log chuyển trạng thái thay vì tự thêm approved_by/at riêng
    reported_by TEXT,
    reported_at TEXT NOT NULL,
    resolved_by TEXT,
    resolved_at TEXT,
    resolution_note TEXT,
    created_at TEXT NOT NULL,
    created_ip TEXT,
    updated_at TEXT NOT NULL,
    updated_ip TEXT
);
CREATE INDEX IF NOT EXISTS idx_incident_reports_allocation ON incident_reports(allocation_id);
CREATE INDEX IF NOT EXISTS idx_incident_reports_status ON incident_reports(status);
```

Ràng buộc "bắt buộc ≥1 ảnh/video" thực hiện ở **tầng ứng dụng** (SQLite không
ép được điều kiện liên bảng tại INSERT đơn): route tạo `incident_reports`
phải nhận kèm ≥1 file trong cùng request, tạo `incident_reports` +
`media_proof` trong 1 transaction, rollback nếu thiếu file.

### 7. Hậu cần — role thật (đã xác nhận có smartphone) + bảng bàn giao riêng

**Đã xác nhận: Hậu cần có dùng smartphone/app** → thiết kế cho phép thêm role
Hậu cần thật trong RBAC (bảng `roles`/`role_permissions` đã động — chỉ cần
tạo role qua `/admin/permissions`, **không cần đổi schema**), gán permission
mới `logistics.handover_confirm`, cho phép họ tự xác nhận bước bàn giao trực
tiếp trên app (không phải Sales/Trại nhập hộ).

Về việc dùng bảng riêng hay chỉ thêm cột vào `sale_allocations`: BM04 là
**1 sự kiện bàn giao vật lý tại khu giao nhận** (3 bên ký), có thể gộp nhiều
kế hoạch bán/lô cùng lúc — không phải thuộc tính 1-1 của 1 đơn hàng. Nhét cột
vào `sale_allocations` (đã 30 cột) sẽ sai ý nghĩa (1 bàn giao ≠ 1 allocation)
và không thể hiện được "gộp nhiều lô cùng khu, cùng ngày". Vì vậy dùng bảng
riêng + bảng dòng chi tiết (N-N):

```sql
CREATE TABLE IF NOT EXISTS logistics_handovers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    handover_code TEXT,
    farm_id INTEGER NOT NULL REFERENCES farms(id),
    handover_date TEXT NOT NULL,
    farm_confirmed_by TEXT,               -- username tài khoản Trại
    farm_confirmed_at TEXT,
    logistics_confirmed_by_user_id INTEGER REFERENCES users(id),  -- tài khoản Hậu cần thật (đã xác nhận có app)
    logistics_confirmed_at TEXT,
    sales_confirmed_by TEXT,              -- username tài khoản Phòng bán hàng
    sales_confirmed_at TEXT,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending' -> 'confirmed' (đủ 3 bên) / 'disputed'
    created_at TEXT NOT NULL,
    created_ip TEXT,
    created_by TEXT,
    updated_at TEXT NOT NULL,
    updated_ip TEXT,
    updated_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_logistics_handovers_farm_date ON logistics_handovers(farm_id, handover_date);

CREATE TABLE IF NOT EXISTS logistics_handover_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    handover_id INTEGER NOT NULL REFERENCES logistics_handovers(id),
    sale_plan_id INTEGER REFERENCES sale_plans(id),
    sale_allocation_id INTEGER REFERENCES sale_allocations(id),
    quantity INTEGER NOT NULL,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_logistics_handover_items_handover ON logistics_handover_items(handover_id);
```

Ảnh biên bản giấy BM04 chụp lại → `media_proof(entity_type='logistics_handover',
entity_id=handover.id, kind='handover_photo')`.

> **Điểm còn mở** (xem mục IV): nếu thực tế vận hành cho thấy 1 bàn giao luôn
> khớp đúng 1 allocation (không gộp lô), có thể đơn giản hoá bằng cách bỏ
> `logistics_handover_items` và thêm thẳng `sale_allocation_id` vào
> `logistics_handovers`.

### 8. `weighing_records` — nền tảng cho UX cân heo (mục IV)

```sql
-- 1 sale_allocation có thể có NHIỀU lần cân (nhiều chuyến xe/ngày) nên tách
-- bảng riêng thay vì thêm cột đơn vào sale_allocations.
CREATE TABLE IF NOT EXISTS weighing_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_allocation_id INTEGER NOT NULL REFERENCES sale_allocations(id),
    farm_id INTEGER NOT NULL REFERENCES farms(id),
    vehicle_plate TEXT,
    tare_weight_kg INTEGER,
    tare_ticket_code TEXT,
    tare_photo_media_id INTEGER REFERENCES media_proof(id),
    tare_recorded_by TEXT,
    tare_recorded_at TEXT,             -- giờ SERVER
    gross_weight_kg INTEGER,
    gross_ticket_code TEXT,
    gross_photo_media_id INTEGER REFERENCES media_proof(id),
    gross_recorded_by TEXT,
    gross_recorded_at TEXT,            -- giờ SERVER
    net_weight_kg INTEGER,             -- gross - tare, tính khi chốt (không dùng cột GENERATED để còn sửa được khi có biên bản sự cố kèm theo TRƯỚC khi khoá)
    status TEXT NOT NULL DEFAULT 'awaiting_tare',
    -- 'awaiting_tare' -> 'tare_done' -> 'gross_done' -> 'confirmed' | 'disputed'
    locked_at TEXT,
    locked_by TEXT,
    created_at TEXT NOT NULL,
    created_ip TEXT,
    created_by TEXT,
    updated_at TEXT NOT NULL,
    updated_ip TEXT,
    updated_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_weighing_records_allocation ON weighing_records(sale_allocation_id);
CREATE INDEX IF NOT EXISTS idx_weighing_records_farm_status ON weighing_records(farm_id, status);

CREATE TRIGGER IF NOT EXISTS trg_weighing_records_lock_guard
BEFORE UPDATE ON weighing_records
FOR EACH ROW WHEN OLD.locked_at IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'DATA_FROZEN: weighing_records đã khoá vĩnh viễn, không thể sửa');
END;
```

Sau khi `confirmed`, giá trị `actual_quantity`/`actual_price`/`weighing_ref`
trên `sale_allocations` được set qua hàm hiện có tương tự
`update_allocation_revenue_details`.

### 9. Permission mới cần thêm vào `core/permissions.py`

| key | Nhãn | Nhóm |
|---|---|---|
| `plans.weighing_record` | Cân xe không tải + cân heo tại khu giao nhận | Cân & giao nhận |
| `logistics.handover_confirm` | Xác nhận biên bản bàn giao heo (BM04) | Cân & giao nhận |
| `incidents.report_create` | Tạo báo cáo sự cố nhanh | Sự cố |
| `incidents.report_manage` | Xử lý / đóng báo cáo sự cố | Sự cố |
| `admin.data_lock.manage` | Khoá vĩnh viễn dữ liệu (Data Freeze) | Quản trị |

Không tạo permission riêng cho `media_proof` — quyền xem/tải ảnh bằng chứng
**kế thừa quyền của entity gốc** (VD ảnh cân của 1 allocation dùng lại
`plans.sale_details`/`plans.revenue_details`), tránh nở permission tràn lan.

---

## IV. System Architecture: Core generic vs Feature module

```
core/
  db.py                     # + CREATE TABLE mới (mục III) + seed workflow_definitions mặc định trong _migrate()
  permissions.py            # + 5 permission key (III.9)
  audit_actions.py          # + action constants (III.4)
  repositories/
    workflow_repo.py        # CRUD workflow_definitions/states/transitions/instances/approval_history — cùng style roles_repo.py
    media_repo.py            # insert/list media_proof (chỉ ghi DB, KHÔNG đụng filesystem)
    lock_repo.py             # ensure_not_locked()/lock_record() dùng chung cho mọi bảng "lockable"
    incident_reports_repo.py
    logistics_handovers_repo.py
    weighing_records_repo.py
  services/
    workflow_service.py      # transition(workflow_key, entity_type, entity_id, action_key, actor, reason=None):
                              #   1) kiểm tra workflow_transitions hợp lệ từ current_state
                              #   2) kiểm tra permission_key (dùng lại permission_required/current_user_can)
                              #   3) ghi workflow_approval_history + audit_repo.log_action()
                              #   4) nếu entity dùng workflow_instances (domain mới) -> update current_state
    media_service.py         # save_upload(file, entity_type, entity_id, kind, uploader) -> lưu đĩa dưới MEDIA_ROOT, tính checksum, insert media_proof; get_file_path(media_id) cho route serve
webapp/
  routes/
    weighing.py    (NEW blueprint)  # /can-heo, /api/weighing/*
    logistics.py    (NEW blueprint)  # /api/handovers/*
    incidents.py    (NEW blueprint)  # /api/incidents/*
    media.py         (NEW blueprint)  # GET /media/<id> — kiểm quyền theo entity_type rồi send_from_directory
    admin.py                          # + /admin/data-lock (tìm & khoá vĩnh viễn), + /admin/workflows (xem lịch sử, tuỳ chọn V2)
    plans.py                          # KHÔNG đổi cấu trúc, chỉ gọi thêm workflow_service ghi lịch sử "mềm" nếu muốn
```

Vì sao tách blueprint riêng thay vì nhét vào `plans.py`: `plans.py` đã ~760
dòng — thêm cân/hậu cần/sự cố vào sẽ vượt quá 1000 dòng, khó bảo trì. Tách
theo domain giữ đúng convention hiện tại (`admin.py`/`auth.py`/`prices.py`/
`plans.py` — 1 blueprint/domain), đăng ký thêm trong `app_factory.py`.

**Cách 1 feature module MỚI (VD KPI thưởng) "cắm" vào core:**

1. Seed 1 dòng `workflow_definitions` (`key='kpi_bonus_approval'`) + các dòng
   `workflow_states`/`workflow_transitions` tương ứng — trong khối seed
   additive của `_migrate()` (giống cách `roles`/`default_role_permissions`
   đang seed), không cần màn hình admin ngay ở V1.
2. Thêm permission key mới vào `core/permissions.py` + gán mặc định cho role
   liên quan trong `default_role_permissions`.
3. Tạo `core/repositories/kpi_bonus_repo.py` (CRUD phần dữ liệu riêng của
   KPI — không có cột status, không có `approved_by`/`rejected_by` riêng vì
   đã dùng `workflow_instances`).
4. Tạo `webapp/routes/kpi.py`, gọi `workflow_service.transition(...)` cho mọi
   hành động duyệt/từ chối thay vì tự viết `approve_kpi()`/`reject_kpi()`
   riêng — đây chính là điểm khác biệt so với `sale_plans` (đã có sẵn hàm
   bespoke, không đổi).
5. Nếu cần ảnh/video kèm theo (VD chứng từ vật tư), gọi
   `media_service.save_upload(entity_type='kpi_bonus', ...)` — dùng lại
   nguyên hàm, không viết upload riêng cho từng domain.

Kết quả: domain mới chỉ cần ~2 file mới (repo + route) + vài dòng seed, không
đụng vào `core/db.py` phần bảng đã có, không đụng `sale_plans`/`sale_allocations`.

---

## V. Mobile UX/UI Flow: Cân xe không tải → Cân heo → Chốt giao khách hàng

**Stack**: giữ nguyên Jinja + vanilla JS (`webapp/static/js/*.js`) + CSS đã có
breakpoint mobile (`@media max-width: 720/640/420px` trong `style.css`) —
không cần thêm framework. Camera dùng
`<input type="file" accept="image/*" capture="environment">` (mở thẳng
camera sau, không cần app riêng). Nhập số dùng `inputmode="numeric"` + nút
bước nhảy lớn để hạn chế gõ chữ.

### Bước 0 — Danh sách hôm nay

`GET /can-heo`: danh sách thẻ lớn (card), lọc theo `allowed_farm_ids()` (dùng
lại helper `routes/auth.py`), mỗi thẻ = 1 `sale_allocation` có `planned_date`
hôm nay + `status='active'`. Hiển thị: mã đơn, khách hàng, số lượng dự kiến,
trạng thái cân (chưa cân / đang cân / đã chốt). Không có ô nhập chữ nào ở màn
này — chỉ chạm để mở.

### Bước 1 — Cân bì (Cân xe KHÔNG TẢI) — bắt buộc trước, đặc biệt XH2/XH3

- Tiêu đề lớn "Bước 1/2 — Cân xe KHÔNG TẢI".
- Nút to **"📷 Chụp ảnh màn hình cân bì"** → mở camera trực tiếp (đã xác nhận
  Sales luôn đứng tại bàn cân → **không có nút "tải ảnh có sẵn"**, chỉ có
  camera in-app, chống gian lận tối đa).
- Biển số xe: chip chọn nhanh từ danh sách gần đây
  (`GET /api/weighing/recent-plates?farm_id=`) — chạm để chọn, chỉ gõ tay khi
  xe mới.
- Số cân bì: bàn phím số lớn (`inputmode="numeric"`) hoặc nút +/- theo bước 10kg.
- Nút "Xác nhận cân bì" **chỉ bật** khi đã có ảnh + số cân.
- Submit → `POST /api/weighing/<id>/tare` (multipart) → server tạo/cập nhật
  `weighing_records` (`status='tare_done'`, `tare_recorded_at`=giờ server,
  `tare_recorded_by`=user hiện tại) + lưu `media_proof(kind='weigh_tare_photo')`.
- Sau khi xác nhận: **form Bước 1 khoá lại ngay trên UI** (chỉ hiển thị dạng
  đọc: "Đã cân bì lúc 14:32 bởi Nguyễn Văn A" + ảnh thumbnail) — route Bước 1
  cũng từ chối nếu `status != 'awaiting_tare'` (chặn ở server, không chỉ JS).

### Bước 2 — Cân heo (Cân xe CÓ TẢI) — chỉ mở khi Bước 1 đã `tare_done`

- Y hệt layout Bước 1: "Bước 2/2 — Cân xe CÓ HEO", nút chụp ảnh (camera
  in-app, không có tải ảnh có sẵn), số cân.
- Sau khi nhập, app tự tính và hiển thị to: **"Heo net: 1.245 kg"** ngay tại
  chỗ để Phòng bán hàng đối chiếu cảm quan với số lượng/đầu heo dự kiến.
- Cảnh báo mềm (không chặn) nếu số net lệch bất thường so với ước tính
  (VD > ±15% so với số lượng × trọng lượng bình quân/con cấu hình sẵn).
- Submit → `POST /api/weighing/<id>/gross` → `status='gross_done'`, lưu
  `media_proof(kind='weigh_gross_photo')`.

### Bước 3 — Chốt giao khách hàng

- Màn tổng hợp: 2 ảnh (bì/heo) đặt cạnh nhau để mắt thường so sánh, số cân
  bì/cân heo/net, biển số, **thời gian giữa 2 lần cân** (cảnh báo nếu quá
  ngắn — nghi ngờ chưa thật sự lái xe đi cân — hoặc quá dài — nghi ngờ ảnh
  cân bì cũ bị tái sử dụng).
- 1 checkbox to "Tôi xác nhận số liệu này đúng thực tế hiện trường" + nút to
  "XÁC NHẬN CHỐT CÂN" — không cần gõ chữ.
- Submit → `POST /api/weighing/<id>/confirm`: `status='confirmed'`,
  **`locked_at`/`locked_by` được set ngay lập tức** (kích hoạt trigger DB ở
  mục III.5 — từ giờ không sửa được nữa), đồng thời ghi
  `actual_quantity`/`actual_price`/`weighing_ref` vào `sale_allocations`.
- Nếu phát hiện sai SAU khi đã chốt: **không cho sửa trực tiếp** — bắt buộc
  vào "Báo cáo sự cố" (`incident_reports`, `kind='weighing_dispute'`, bắt
  buộc kèm ảnh/video mới) tham chiếu `weighing_record_id` — đúng nguyên tắc
  "cấm tự sửa sau khi cân, mọi thay đổi phải có biên bản".

### Cơ chế chống gian lận (khi CHƯA có API trạm cân)

1. **Ép thứ tự tại server**: route Bước 2 kiểm tra
   `weighing_records.status == 'tare_done'` trước khi nhận request — không
   chỉ ẩn/hiện bằng JS.
2. **Ảnh bắt buộc + timestamp server**: `uploaded_at`/`tare_recorded_at`/
   `gross_recorded_at` luôn lấy giờ server, không nhận timestamp client gửi
   lên (chống chỉnh giờ máy điện thoại).
3. **So sánh trực quan 2 ảnh cạnh nhau** ở Bước 3 — con người review bằng mắt
   (chưa có OCR đọc số trên ảnh cân để đối chiếu tự động với số nhập tay —
   hạn chế đã biết, đề xuất bổ sung OCR khi có ngân sách/API).
4. **Phát hiện tái sử dụng ảnh**: `media_service.save_upload()` tính
   `checksum_sha256`, kiểm tra trùng với ảnh `kind` tương tự đã dùng cho
   `weighing_record` khác → cảnh báo "ảnh này đã dùng cho lần cân khác".
5. **Cảnh báo khoảng thời gian giữa 2 lần cân** bất thường (mục Bước 3).
6. **Khoá vĩnh viễn ngay khi chốt** (trigger DB) — không ai sửa lại được kể
   cả admin thao tác nhầm; muốn điều chỉnh phải qua `incident_reports` có
   căn cứ.
7. **Permission riêng** `plans.weighing_record` — chỉ Phòng bán hàng tại hiện
   trường thấy/thao tác được màn này, vai trò `farm` không truy cập.
8. *(V2, không bắt buộc ngay)*: gắn mã QR theo `sale_allocation`/lô để quét
   mở đúng phiếu cân thay vì chọn tay từ danh sách — giảm nhầm gán sai đơn.

---

## VI. Thứ tự triển khai đề xuất (nếu quyết định code)

1. `media_proof` + `media_service` (nền tảng, không phụ thuộc gì khác).
2. `weighing_records` + UX Bước 0-3 (giá trị nghiệp vụ cao nhất, giải quyết
   đúng pain point "chưa có API trạm cân").
3. Data Freeze (`locked_at`/`locked_by` + trigger) — áp cho `weighing_records`
   trước (mới, rủi ro thấp), sau đó cân nhắc áp cho `sale_plans`/`sale_allocations`.
4. `incident_reports` (phụ thuộc `media_proof`).
5. Workflow engine generic (`workflow_*`) — làm nền cho domain KPI/vật tư
   tương lai, **không** vội áp vào `sale_plans`/`sale_allocations`.
6. `logistics_handovers` — xác nhận lại với nghiệp vụ thực tế (mục VII) trước
   khi code, vì đây là điểm thiết kế còn mở.

---

## VII. Điểm còn mở cần xác nhận thêm với nghiệp vụ thực tế

1. **`logistics_handovers` có thực sự gộp nhiều lô/allocation trong 1 lần bàn
   giao, hay luôn 1-1?** Nếu thực tế luôn 1-1, có thể bỏ bảng
   `logistics_handover_items` và thêm thẳng `sale_allocation_id` vào
   `logistics_handovers` — đơn giản hơn. Cần hỏi Phòng bán hàng/Hậu cần thực
   tế trước khi code.
2. **Thứ tự triển khai** ở mục VI là đề xuất dựa trên giá trị nghiệp vụ +
   rủi ro kỹ thuật — có thể đổi nếu công ty có ưu tiên khác (VD nếu KPI
   thưởng cần làm gấp hơn cân heo, nên đảo bước 5 lên sớm hơn).
3. **OCR đọc số cân tự động** — hiện chưa thiết kế (ghi nhận là hạn chế đã
   biết ở mục V, cơ chế chống gian lận #3) — cần đánh giá chi phí API OCR
   nếu muốn giảm phụ thuộc vào việc con người tự so sánh ảnh bằng mắt.

---

## VIII. So sánh với góp ý của Gemini

*Chưa có nội dung — người dùng chưa cung cấp góp ý của Gemini trong phiên làm
việc tạo tài liệu này. Bổ sung mục này khi có nội dung để đối chiếu điểm nào
Gemini đề xuất trùng/khác với thiết kế trên.*
