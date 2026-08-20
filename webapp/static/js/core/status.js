// STATUS_CONFIG — nguồn tập trung cho label tiếng Việt + loại badge của các
// trạng thái đang dùng rải rác trong plan.js/allocation.js (planBadge() v.v.).
// Phase 0: chỉ khai báo hạ tầng dùng chung, chưa thay các hàm badge hiện có
// của từng trang — việc đó làm dần khi trang đó được đụng tới ở phase sau.
const STATUS_CONFIG = {
  pending_approval: { label: "⏳ Chờ duyệt", type: "info" },
  approved: { label: "Đã duyệt", type: "success" },
  rejected: { label: "❌ Bị từ chối", type: "danger" },
  reached: { label: "Đã đạt", type: "success" },
  overdue: { label: "Quá hạn", type: "danger" },
  today: { label: "Hôm nay", type: "info" },
  // "done" dùng cho đơn hàng (sale_orders.status) — khớp màu trung tính
  // của .plan-badge.done cũ (surface-muted/muted), không phải màu nổi bật.
  done: { label: "Đã bán", type: "" },
  // "active" = đơn hàng đang xử lý (chưa mark-done/huỷ) — khớp màu trung
  // tính của badge mặc định (không class) cũ trong orderStatusBadge().
  active: { label: "Đang xử lý", type: "" },
  cancelled: { label: "Đã hủy", type: "" },
  disabled: { label: "🚫 Đã vô hiệu hoá", type: "danger" },
  locked: { label: "Đã khóa", type: "dark" },
  // Trạng thái đối soát kế hoạch trại (reconciliation_status, sale_plans_repo.py)
  // — dùng ở doi_soat.js, gộp vào đây thay vì hàm dsStatusBadge() cục bộ trùng
  // lặp (STEP 8 Phase 4).
  needs_reconciliation: { label: "⚠ Cần đối soát", type: "warning" },
  in_progress: { label: "Đang trong hạn", type: "" },
  reconciled: { label: "✓ Đã đối soát", type: "success" },
  over_delivered: { label: "⚠ Vượt kế hoạch", type: "danger" },
};

function renderBadge(status) {
  const cfg = STATUS_CONFIG[status] || { label: status, type: "" };
  const cls = cfg.type ? `badge badge-${cfg.type}` : "badge";
  return `<span class="${cls}">${cfg.label}</span>`;
}
