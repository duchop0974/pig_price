// Trang "Đối soát" — triage toàn bộ kế hoạch trại theo trạng thái đối
// soát. Thuần đọc: 1 fetch /api/plans (đã có sẵn mọi field cần, tính bởi
// Giai đoạn 1-3), lọc client-side (khuôn applyAvailablePlanFilters ở
// allocation.js — quy mô dữ liệu nhỏ, không cần filter server-side).
// Hành động "Xử lý chênh lệch" KHÔNG nhúng modal ở đây — link sang
// /ke-hoach?highlight=<id>&action=reconcile để mở đúng modal đã có ở
// plan.js, tránh nhân đôi ~200 dòng HTML/JS modal.

const CAN_RECONCILE = (window.CURRENT_USER_PERMISSIONS || []).includes("plans.reconcile_create");

const RECONCILE_KIND_LABELS_DS = {
  still_at_farm: "Còn tại trại",
  continue_selling: "Tiếp tục bán",
  transferred: "Chuyển nguồn khác",
  culled: "Đã loại",
  cancelled: "Khách hủy",
  other: "Khác",
};

let allApprovedPlans = [];

function fillDsFilterOptions(plans) {
  const farmSelect = el("ds-filter-farm");
  const typeSelect = el("ds-filter-pig-type");
  const farms = [...new Set(plans.map((p) => p.farm).filter(Boolean))].sort();
  const types = [...new Set(plans.map((p) => p.pig_type_name).filter(Boolean))].sort();
  const curFarm = farmSelect.value;
  const curType = typeSelect.value;
  farmSelect.innerHTML = `<option value="">Tất cả trại</option>` + farms.map((f) => `<option value="${f}">${f}</option>`).join("");
  typeSelect.innerHTML = `<option value="">Tất cả loại heo</option>` + types.map((t) => `<option value="${t}">${t}</option>`).join("");
  if (farms.includes(curFarm)) farmSelect.value = curFarm;
  if (types.includes(curType)) typeSelect.value = curType;
}

function renderSummary(plans) {
  const needs = plans.filter((p) => p.reconciliation_status === "needs_reconciliation").length;
  const progress = plans.filter((p) => p.reconciliation_status === "in_progress").length;
  const done = plans.filter((p) => p.reconciliation_status === "reconciled" || p.reconciliation_status === "over_delivered").length;
  el("ds-count-needs").innerHTML = `${needs}<span class="unit">kế hoạch</span>`;
  el("ds-count-progress").innerHTML = `${progress}<span class="unit">kế hoạch</span>`;
  el("ds-count-done").innerHTML = `${done}<span class="unit">kế hoạch</span>`;
}

function applyDsFilters(plans) {
  const farm = el("ds-filter-farm").value;
  const pigType = el("ds-filter-pig-type").value;
  const dateFrom = el("ds-filter-date-from").value;
  const dateTo = el("ds-filter-date-to").value;
  const status = el("ds-filter-status").value;
  const q = el("ds-filter-search").value.trim().toLowerCase();
  return plans.filter((p) => {
    if (farm && p.farm !== farm) return false;
    if (pigType && p.pig_type_name !== pigType) return false;
    if (dateFrom && p.planned_date && p.planned_date < dateFrom) return false;
    if (dateTo && p.planned_date && p.planned_date > dateTo) return false;
    if (status === "open" && !["needs_reconciliation", "in_progress"].includes(p.reconciliation_status)) return false;
    if (status !== "open" && status !== "all" && p.reconciliation_status !== status) return false;
    if (q) {
      const hay = `${p.farm || ""} ${p.zone || ""} ${p.plan_code || ""} ${p.note || ""} ${p.pig_type_name || ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

function dsBreakdownText(breakdown) {
  if (!breakdown || !breakdown.length) return "";
  return breakdown.map((b) => `${RECONCILE_KIND_LABELS_DS[b.kind] || b.kind} ${b.quantity}`).join(", ");
}

// Cơ cấu loại heo + trọng lượng — 2 chiều đối soát đã tính sẵn ở backend
// (sale_plans_repo.py: delivery_mix/off_type_quantity, planned_total_weight_kg/
// actual_total_weight_kg) nhưng trước STEP đối soát đa chiều chỉ hiện ở
// trang Kế hoạch (plan.js:planReconcileHtml) — tái dùng đúng text/điều
// kiện ở đây, không tính lại.
function dsExtraBadges(p) {
  const parts = [];
  if (p.delivery_mix && p.delivery_mix.has_composition_variance) {
    parts.push(`<span class="badge badge-warning">Lệch cơ cấu: ${p.off_type_quantity} con khác loại</span>`);
  }
  const hasWeight =
    (p.planned_total_weight_kg !== null && p.planned_total_weight_kg !== undefined) ||
    (p.actual_total_weight_kg !== null && p.actual_total_weight_kg !== undefined);
  if (hasWeight) {
    parts.push(`<span class="badge">Khối lượng: ${fmtWeight(p.actual_total_weight_kg)} / ${fmtWeight(p.planned_total_weight_kg)} kg</span>`);
  }
  return parts.join(" ");
}

// Đối soát đa chiều (Phase 2): Khách hàng/Giá/Phiếu cân không rút gọn về 1
// cột được (1 kế hoạch có thể tách nhiều đơn/khách/giá) — hiện dạng bảng
// nhỏ trong detailModal() (core/modal.js, đã load sẵn qua base.html, đúng
// pattern plan.js/allocation.js đang dùng cho chi tiết đơn hàng).
async function showSaleBreakdown(planId, planCode) {
  const res = await fetch(`/api/plans/${planId}/sale-breakdown`);
  if (!res.ok) {
    showToast("Không tải được chi tiết bán hàng.", "error");
    return;
  }
  const lines = await res.json();
  const bodyHtml = !lines.length
    ? `<p class="msg">Kế hoạch này chưa có dòng hàng nào.</p>`
    : `<table class="admin-table">
        <thead><tr><th>Đơn hàng</th><th>Khách hàng</th><th>Số lượng</th><th>Giá chốt</th><th>Giá thực tế</th><th>Phiếu cân</th></tr></thead>
        <tbody>
          ${lines
            .map(
              (l) => `<tr>
                <td>${l.order_code}${renderBadge(l.order_status)}</td>
                <td>${l.customer_name || "—"}</td>
                <td>${fmtPrice(l.quantity)} con</td>
                <td>${l.selling_price !== null ? fmtPrice(l.selling_price) + "đ" : "—"}</td>
                <td>${l.actual_price !== null ? fmtPrice(l.actual_price) + "đ" : "—"}</td>
                <td>${l.weighing_refs.length ? l.weighing_refs.join(", ") : "—"}</td>
              </tr>`
            )
            .join("")}
        </tbody>
      </table>`;
  detailModal({ title: `Chi tiết bán hàng — ${planCode}`, bodyHtml });
}

function planRowHtml(p) {
  const canAct = p.remaining_to_reconcile !== 0 && CAN_RECONCILE;
  const actionHtml = canAct
    ? `<a class="btn btn-ghost btn-sm" href="/ke-hoach?highlight=${p.id}&action=reconcile">Xử lý chênh lệch →</a>`
    : "";
  const remainingCls = p.remaining_to_reconcile < 0 ? "text-success" : p.remaining_to_reconcile > 0 ? "text-danger" : "";
  const noteHtml = [dsBreakdownText(p.reconciliation_breakdown), dsExtraBadges(p)].filter(Boolean).join(" ");
  const planCodeSafe = (p.plan_code || "#" + p.id).replace(/'/g, "\\'");
  return `<tr>
    <td data-label="Mã kế hoạch"><button type="button" class="btn btn-ghost btn-sm" onclick="showSaleBreakdown(${p.id}, '${planCodeSafe}')">${p.plan_code || "#" + p.id}</button></td>
    <td data-label="Trại">${p.farm}${p.zone ? " · " + p.zone : ""}</td>
    <td data-label="Loại heo">${p.pig_type_name || "—"}</td>
    <td data-label="Ngày dự kiến">${fmtIsoDate(p.planned_date)}</td>
    <td data-label="Ngày xuất thực tế">${p.last_delivered_date ? fmtIsoDate(p.last_delivered_date) : "—"}</td>
    <td data-label="Kế hoạch">${fmtPrice(p.quantity)} con</td>
    <td data-label="Chốt">${fmtPrice(p.allocated_quantity)} con</td>
    <td data-label="Thực tế">${fmtPrice(p.actual_sold_quantity)} con</td>
    <td data-label="Chênh lệch" class="${remainingCls}">${fmtPrice(p.remaining_to_reconcile)} con</td>
    <td data-label="Trạng thái">${renderBadge(p.reconciliation_status)}</td>
    <td data-label="Ghi chú">${noteHtml}</td>
    <td>${actionHtml}</td>
  </tr>`;
}

function renderDsTable() {
  const filtered = applyDsFilters(allApprovedPlans);
  const body = el("doi-soat-list");
  const emptyMsg = el("doi-soat-empty");
  if (!filtered.length) {
    body.innerHTML = "";
    emptyMsg.classList.remove("hidden");
    return;
  }
  emptyMsg.classList.add("hidden");
  body.innerHTML = filtered
    .slice()
    .sort((a, b) => (a.planned_date < b.planned_date ? -1 : a.planned_date > b.planned_date ? 1 : 0))
    .map(planRowHtml)
    .join("");
}

async function loadDsPlans() {
  const res = await fetch("/api/plans");
  const plans = await res.json();
  // reconciliation_status chỉ có ý nghĩa với kế hoạch đã duyệt (xem
  // _apply_reconciliation_status ở sale_plans_repo.py) — trang này chỉ
  // quan tâm các kế hoạch đó.
  allApprovedPlans = (plans || []).filter((p) => p.status === "approved");
  fillDsFilterOptions(allApprovedPlans);
  renderSummary(allApprovedPlans);
  renderDsTable();
}

["ds-filter-farm", "ds-filter-pig-type", "ds-filter-date-from", "ds-filter-date-to", "ds-filter-status"].forEach((id) => {
  if (el(id)) el(id).addEventListener("change", renderDsTable);
});
if (el("ds-filter-search")) el("ds-filter-search").addEventListener("input", renderDsTable);

if (el("doi-soat-list")) loadDsPlans();
