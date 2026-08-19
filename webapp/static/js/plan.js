async function loadFarms(selectId) {
  const select = el("plan-farm");
  if (!select) return; // vai trò không có quyền tạo kế hoạch trại
  const res = await fetch("/api/farms");
  const farms = await res.json();
  const current = selectId || select.value;
  if (!farms.length) {
    const emptyMsg =
      window.CURRENT_USER_ROLE === "farm"
        ? "Bạn chưa được gán trại nào — liên hệ admin"
        : "Chưa có trang trại — liên hệ admin";
    select.innerHTML = `<option value="" disabled selected>${emptyMsg}</option>`;
    await loadZones();
    return;
  }
  select.innerHTML = farms
    .map((f) => `<option value="${f.id}">${f.code}${f.province ? " · " + f.province : ""}</option>`)
    .join("");
  if ([...select.options].some((o) => o.value === String(current))) select.value = current;
  await loadZones();
}

async function loadZones(selectId) {
  const farmSelect = el("plan-farm");
  const select = el("plan-zone");
  if (!farmSelect || !select) return;
  const farmId = farmSelect.value;
  if (!farmId) {
    select.innerHTML = `<option value="" disabled selected>Chọn trang trại trước</option>`;
    return;
  }
  const res = await fetch(`/api/zones?farm_id=${encodeURIComponent(farmId)}`);
  const zones = await res.json();
  const current = selectId || select.value;
  if (!zones.length) {
    select.innerHTML = `<option value="" disabled selected>Trang trại chưa có khu — liên hệ admin</option>`;
    return;
  }
  select.innerHTML = zones.map((z) => `<option value="${z.id}">${z.code}</option>`).join("");
  if ([...select.options].some((o) => o.value === String(current))) select.value = current;
}

async function loadPigTypes() {
  const select = el("plan-pig-type");
  if (!select) return;
  const res = await fetch("/api/pig-types");
  const pigTypes = await res.json();
  if (!pigTypes.length) {
    select.innerHTML = `<option value="" disabled selected>Chưa có danh mục loại heo — liên hệ admin</option>`;
    return;
  }
  select.innerHTML = pigTypes.map((pt) => `<option value="${pt.id}">${pt.name}</option>`).join("");
}

// Badge đếm ngày (góc phải header card) — độc lập với trạng thái quy trình
// (dòng trạng thái nổi bật dùng renderBadge(plan.status) riêng), vì
// `days_left` server trả về cho MỌI status (webapp/routes/plans.py), không
// chỉ "approved".
function planDeadlineBadge(plan) {
  if (plan.days_left === null || plan.days_left === undefined) return "";
  if (plan.days_left < 0) return `<span class="badge badge-danger">Quá hạn ${Math.abs(plan.days_left)} ngày</span>`;
  if (plan.days_left === 0) return renderBadge("today");
  return `<span class="badge">Còn ${plan.days_left} ngày</span>`;
}

// Mini workflow stepper cho vòng đời kế hoạch trại: Chờ duyệt → Đã duyệt →
// Đã nhận. rejected/cancelled/disabled hiển thị is-exception thay vì tiếp
// tục chuỗi (dùng .stepper CSS có sẵn từ Phase 0, chưa nơi nào dùng).
const STEPPER_STATE_CLASS = { done: "is-done", current: "is-current", pending: "", exception: "is-exception", locked: "is-locked" };
const STEPPER_MARKER = { done: "✓", current: "●", pending: "○", exception: "!", locked: "🔒" };

function planStepperHtml(plan) {
  const labels = ["Chờ duyệt", "Đã duyệt", "Đã nhận"];
  let states;
  if (plan.status === "pending_approval") {
    states = ["current", "pending", "pending"];
  } else if (plan.status === "rejected" || plan.status === "cancelled") {
    states = ["exception", "locked", "locked"];
  } else if (plan.status === "disabled") {
    states = ["done", "exception", "locked"];
  } else if (plan.status === "approved") {
    const received = plan.received_quantity !== null && plan.received_quantity !== undefined;
    states = ["done", received ? "done" : "current", received ? "done" : "pending"];
  } else {
    return "";
  }
  return `<div class="stepper">${labels
    .map((label, i) => {
      const s = states[i];
      const connector = i < labels.length - 1 ? `<span class="stepper-connector"></span>` : "";
      return `<span class="stepper-step ${STEPPER_STATE_CLASS[s]}"><span class="stepper-step-marker">${STEPPER_MARKER[s]}</span><span class="stepper-step-label">${label}</span></span>${connector}`;
    })
    .join("")}</div>`;
}

// Khối "Tiến độ bán" trên thẻ kế hoạch (chỉ khi status==='approved'): dùng
// actual_sold_quantity (thực tế bán, KHÔNG phải allocated_quantity — §14,
// tránh hiện "đã bán" cho số mới chỉ "nhặt" vào đơn chưa giao) làm % thanh
// tiến độ; hiện cảnh báo "Cần đối soát" khi còn chênh lệch và đã quá hạn,
// hoặc breakdown (Đã loại/Khách hủy/...) khi đã đối soát xong.
// allocated_quantity vẫn còn (chuyển xuống khối "Chi tiết" — xem renderPlans).
function planReconcileHtml(p) {
  if (p.status !== "approved") return "";
  const qty = p.quantity || 0;
  const actualSold = p.actual_sold_quantity || 0;
  const remaining = p.remaining_to_reconcile || 0;
  const isComplete = p.reconciliation_status === "reconciled";
  const isOverDelivered = p.reconciliation_status === "over_delivered";
  const pct = qty ? Math.min(100, Math.round((actualSold / qty) * 100)) : 0;

  const rows = [`<div class="plan-row"><span>Đã bán</span><strong>${actualSold} / ${qty} con</strong></div>`];

  // Khối lượng — chỉ hiện khi có ít nhất 1 phía (dự kiến hoặc thực tế) có số,
  // "—" cho phía còn thiếu (không phải 0, xem fmtWeight).
  if (p.planned_total_weight_kg !== null && p.planned_total_weight_kg !== undefined || p.actual_total_weight_kg !== null && p.actual_total_weight_kg !== undefined) {
    rows.push(
      `<div class="plan-row"><span>Khối lượng</span><strong>${fmtWeight(p.actual_total_weight_kg)} / ${fmtWeight(p.planned_total_weight_kg)} kg</strong></div>`
    );
  }

  let statusHtml = "";
  if (isOverDelivered) {
    // Xuất DƯ so với kế hoạch — cảnh báo riêng, KHÔNG được lẫn vào nhánh
    // "Cần đối soát" (thiếu) hay "reconciled" (đủ/đúng) — đây là tình huống
    // cần chú ý nhất, badge phải khác hẳn 2 badge kia.
    rows.push(
      `<div class="plan-row"><span>Vượt kế hoạch</span><strong class="plan-down">+${Math.abs(remaining)} con</strong></div>`
    );
    statusHtml = `<div class="alert alert-danger"><span class="alert-icon">⚠</span> Xuất vượt kế hoạch</div>`;
  } else if (remaining > 0) {
    rows.push(`<div class="plan-row"><span>Chưa xử lý</span><strong>${remaining} con</strong></div>`);
    if (p.reconciliation_status === "needs_reconciliation") {
      statusHtml = `<div class="alert alert-warning"><span class="alert-icon">⚠</span> Cần đối soát</div>`;
    }
  } else if (isComplete) {
    const breakdown = p.reconciliation_breakdown || [];
    statusHtml = `<span class="badge badge-success">${breakdown.length ? "✓ Đã đối soát" : "✓ Đã bán hết"}</span>`;
  }

  // Lịch sử ghi nhận đối soát — LUÔN hiện nếu có bản ghi, không chỉ khi đã
  // đối soát xong (trước đây chỉ hiện trong nhánh isComplete, nên 1 kế
  // hoạch đã ghi "Còn tại trại"/"Tiếp tục bán" mà vẫn "Cần đối soát" (2
  // kind này KHÔNG đóng chênh lệch — backend cố ý loại khỏi
  // reconciled_quantity, xem RECONCILE_NON_CLOSING_KINDS) sẽ KHÔNG thấy
  // được là mình đã ghi nhận gì trước đó → dễ bấm "Xử lý chênh lệch" ghi
  // lại nhiều lần vì tưởng chưa làm gì).
  const breakdown = p.reconciliation_breakdown || [];
  const breakdownHtml = breakdown.length
    ? `<div class="plan-card-section-label">Đã ghi nhận</div>` +
      breakdown
        .map(
          (b) =>
            `<div class="plan-row"><span>${RECONCILE_KIND_LABELS[b.kind] || b.kind}${
              RECONCILE_NON_CLOSING_KINDS.has(b.kind) ? " (chưa đóng chênh lệch)" : ""
            }</span><strong>${b.quantity} con</strong></div>`
        )
        .join("")
    : "";

  // Lệch cơ cấu loại heo (VD kế hoạch 100 loại 1, thực tế 80 loại 1 + 20
  // loại 2) — KHÁC hẳn "Cần đối soát" (thiếu số lượng): ở đây tổng số CÓ
  // THỂ đã khớp, chỉ khác loại. Hiện độc lập, không thay thế statusHtml.
  const mixWarning =
    p.delivery_mix && p.delivery_mix.has_composition_variance
      ? `<div class="alert alert-warning"><span class="alert-icon">⚠</span> Lệch cơ cấu: ${p.off_type_quantity} con khác loại kế hoạch</div>`
      : "";

  return `<div class="plan-card-section">
      ${rows.join("")}
      <div class="progress-bar" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100">
        <div class="progress-bar-fill ${isComplete ? "is-complete" : ""}" style="width:${pct}%"></div>
      </div>
      ${statusHtml}
      ${breakdownHtml}
      ${mixWarning}
    </div>`;
}

// Ai duyệt/từ chối được kế hoạch trại — khớp @permission_required(perm.PLAN_REVIEW) ở server.
const CAN_REVIEW_PLANS = (window.CURRENT_USER_PERMISSIONS || []).includes("plans.review");
// Ai ghi nhận số lượng thực nhận — khớp @permission_required(perm.PLAN_RECEIVE) ở server.
const CAN_RECEIVE_PLANS = (window.CURRENT_USER_PERMISSIONS || []).includes("plans.receive");
// Sửa nội dung kế hoạch trại (trường hợp nhập nhầm) — mặc định chỉ admin có
// quyền này, khớp @permission_required(perm.PLAN_EDIT) trên route
// /api/plans/<id>/edit. Từ Giai đoạn 9 không còn giới hạn theo status/
// allocated_quantity — admin sửa được bất kể trạng thái.
const CAN_EDIT_PLANS = (window.CURRENT_USER_PERMISSIONS || []).includes("plans.edit");
// Xoá vĩnh viễn kế hoạch trại — mặc định chỉ admin có quyền này (Giai đoạn 9),
// khớp @permission_required(perm.PLAN_DELETE) trên route DELETE /api/plans/<id>.
const CAN_DELETE_PLANS = (window.CURRENT_USER_PERMISSIONS || []).includes("plans.delete");
// Xử lý chênh lệch kế hoạch trại (đối soát) — khớp
// @permission_required(perm.PLAN_RECONCILE_CREATE) trên route POST
// /api/plans/<id>/reconciliations.
const CAN_RECONCILE_PLANS = (window.CURRENT_USER_PERMISSIONS || []).includes("plans.reconcile_create");

// Nhãn hiển thị cho từng kind đối soát — khớp VALID_KINDS ở
// core/repositories/plan_reconciliation_repo.py.
const RECONCILE_KIND_LABELS = {
  still_at_farm: "Còn tại trại",
  continue_selling: "Tiếp tục bán",
  transferred: "Chuyển nguồn khác",
  culled: "Đã loại",
  cancelled: "Khách hủy",
  other: "Khác",
};

// 2 kind KHÔNG đóng chênh lệch (chỉ là ghi chú "vẫn còn/vẫn đang bán tiếp",
// backend cố ý loại khỏi reconciled_quantity — xem core/repositories/
// sale_plans_repo.py) — khác 4 kind còn lại thực sự "chốt" và làm giảm
// remaining_to_reconcile. Dùng để chú thích trong lịch sử ghi nhận, tránh
// hiểu nhầm "đã ghi nhận rồi mà sao vẫn Cần đối soát".
const RECONCILE_NON_CLOSING_KINDS = new Set(["still_at_farm", "continue_selling"]);

// Danh sách kế hoạch trại đang hiển thị — dùng nội bộ cho recordReceived()/startEditPlan().
let currentPlans = [];
// id kế hoạch đang sửa (null = form ở chế độ tạo mới).
let editingPlanId = null;

// 1 primary action duy nhất/card — ưu tiên theo bước tiếp theo hợp lý nhất
// của quy trình, đúng permission-gate cũ (chỉ đổi cách hiển thị, không đổi
// điều kiện).
function planPrimaryAction(p) {
  if (p.status === "pending_approval" && CAN_REVIEW_PLANS) {
    return { label: "✅ Duyệt", cls: "plan-btn-approve" };
  }
  // Chênh lệch đã quá hạn (needs_reconciliation) là việc cấp bách hơn ghi
  // nhận xuất chuồng — ưu tiên làm primary. Còn hạn (in_progress) thì vẫn
  // để "Ghi nhận đã xuất chuồng" làm primary, "Xử lý chênh lệch" xuống menu
  // ⋮ (xem planMenuActions) — tránh 2 primary tranh chỗ trên cùng 1 thẻ.
  if (p.status === "approved" && p.reconciliation_status === "needs_reconciliation" && CAN_RECONCILE_PLANS) {
    return { label: "⚖️ Xử lý chênh lệch", cls: "plan-btn-reconcile" };
  }
  if (p.status === "approved" && CAN_RECEIVE_PLANS) {
    return { label: "📦 Ghi nhận đã xuất chuồng", cls: "plan-btn-received" };
  }
  if (p.status === "disabled" && CAN_REVIEW_PLANS) {
    return { label: "▶️ Kích hoạt lại", cls: "plan-btn-enable" };
  }
  return null;
}

// Các action còn lại (không trùng với primary) — vào menu ⋮.
function planMenuActions(p) {
  const items = [];
  if (p.status === "pending_approval" && CAN_REVIEW_PLANS) {
    items.push({ label: "❌ Từ chối", cls: "plan-btn-reject" });
  }
  if (p.status === "approved" && CAN_REVIEW_PLANS) {
    items.push({ label: "🚫 Vô hiệu hoá", cls: "plan-btn-disable" });
  }
  if (
    p.status === "approved" &&
    p.remaining_to_reconcile > 0 &&
    p.reconciliation_status !== "needs_reconciliation" &&
    CAN_RECONCILE_PLANS
  ) {
    items.push({ label: "⚖️ Xử lý chênh lệch", cls: "plan-btn-reconcile" });
  }
  if (CAN_EDIT_PLANS) {
    items.push({ label: "✏️ Sửa", cls: "plan-btn-edit" });
  }
  if (CAN_DELETE_PLANS && p.allocated_quantity === 0) {
    items.push({ label: "🗑️ Xoá vĩnh viễn", cls: "plan-btn-delete", danger: true });
  }
  return items;
}

// Badge đối soát nhỏ cho cột riêng trong bảng (chỉ có nghĩa khi approved).
function planReconcileBadge(p) {
  if (p.status !== "approved") return "";
  if (p.reconciliation_status === "needs_reconciliation") return `<span class="badge badge-warning">⚠ Cần đối soát</span>`;
  if (p.reconciliation_status === "in_progress") return `<span class="badge">Đang trong hạn</span>`;
  if (p.reconciliation_status === "reconciled") return `<span class="badge badge-success">✓ Đã đối soát</span>`;
  if (p.reconciliation_status === "over_delivered") return `<span class="badge badge-danger">⚠ Vượt kế hoạch</span>`;
  return "";
}

// Đổ option Trại/Loại heo cho filter bar — khuôn fillDsFilterOptions (doi_soat.js).
function fillPlanFilterOptions(plans) {
  const farmSelect = el("plan-filter-farm");
  const typeSelect = el("plan-filter-pig-type");
  if (!farmSelect || !typeSelect) return;
  const farms = [...new Set(plans.map((p) => p.farm).filter(Boolean))].sort();
  const types = [...new Set(plans.map((p) => p.pig_type_name).filter(Boolean))].sort();
  const curFarm = farmSelect.value;
  const curType = typeSelect.value;
  farmSelect.innerHTML = `<option value="">Tất cả trại</option>` + farms.map((f) => `<option value="${f}">${f}</option>`).join("");
  typeSelect.innerHTML = `<option value="">Tất cả loại heo</option>` + types.map((t) => `<option value="${t}">${t}</option>`).join("");
  if (farms.includes(curFarm)) farmSelect.value = curFarm;
  if (types.includes(curType)) typeSelect.value = curType;
}

// Lọc thuần client-side — khuôn applyDsFilters (doi_soat.js). Mọi option
// "Tất cả..." PHẢI là mặc định: trang này là đích của ?highlight=<id> từ
// Tổng quan, filter mặc định thu hẹp sẽ khiến record cần highlight bị lọc
// mất ngay từ lần render đầu tiên.
function applyPlanFilters(plans) {
  const farm = el("plan-filter-farm").value;
  const pigType = el("plan-filter-pig-type").value;
  const dateFrom = el("plan-filter-date-from").value;
  const dateTo = el("plan-filter-date-to").value;
  const status = el("plan-filter-status").value;
  const reconcile = el("plan-filter-reconcile").value;
  const q = el("plan-filter-search").value.trim().toLowerCase();
  return plans.filter((p) => {
    if (farm && p.farm !== farm) return false;
    if (pigType && p.pig_type_name !== pigType) return false;
    if (dateFrom && p.planned_date && p.planned_date < dateFrom) return false;
    if (dateTo && p.planned_date && p.planned_date > dateTo) return false;
    if (status && p.status !== status) return false;
    if (reconcile && p.reconciliation_status !== reconcile) return false;
    if (q) {
      const hay = `${p.farm || ""} ${p.zone || ""} ${p.plan_code || ""} ${p.note || ""} ${p.pig_type_name || ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

function planRowHtml(p) {
  const primary = planPrimaryAction(p);
  const primaryHtml = primary
    ? `<button type="button" class="btn btn-primary btn-sm ${primary.cls}" data-id="${p.id}">${primary.label}</button>`
    : "";
  const rowCls = p.status === "disabled" ? "plan-card-disabled" : "";
  return `<tr class="${rowCls}" data-id="${p.id}">
    <td data-label="Mã kế hoạch">${p.plan_code || "#" + p.id}</td>
    <td data-label="Trại">${p.farm}${p.zone ? " · " + p.zone : ""}</td>
    <td data-label="Loại heo">${p.pig_type_name || "—"}</td>
    <td data-label="Ngày dự kiến">${fmtIsoDate(p.planned_date)} ${planDeadlineBadge(p)}</td>
    <td data-label="Số lượng">${p.quantity} con</td>
    <td data-label="Trạng thái">${renderBadge(p.status)}</td>
    <td data-label="Đối soát">${planReconcileBadge(p)}</td>
    <td class="admin-table-actions">
      ${primaryHtml}
      <button type="button" class="btn btn-ghost btn-sm plan-btn-detail" data-id="${p.id}">Chi tiết</button>
    </td>
  </tr>`;
}

function renderPlansTable(plans) {
  const tbody = el("plan-list");
  const emptyMsg = el("plan-list-empty");
  if (!tbody) return;
  if (!plans.length) {
    tbody.innerHTML = "";
    if (emptyMsg) emptyMsg.classList.remove("hidden");
    return;
  }
  if (emptyMsg) emptyMsg.classList.add("hidden");
  tbody.innerHTML = plans.map(planRowHtml).join("");
}

function refreshPlansView() {
  renderPlansTable(applyPlanFilters(currentPlans));
}

// Body modal chi tiết — tái dùng nguyên planStepperHtml/planReconcileHtml/
// planDeadlineBadge/renderBadge, gộp lại đúng nội dung từng nằm trong card +
// khối "Chi tiết" (allocatedHtml/shedLotHtml/receivedHtml) của renderPlans()
// cũ thành 1 khối duy nhất, không còn ẩn sau nút toggle.
function planDetailBodyHtml(p) {
  const allocatedHtml =
    p.status === "approved"
      ? `<div class="plan-row"><span>Đã phân bổ (đơn hàng)</span><strong>${p.allocated_quantity} / ${p.quantity} con</strong></div>`
      : "";
  const shedLotHtml =
    p.shed || p.lot
      ? `<div class="plan-row"><span>Chuồng/Lô</span><strong>${p.shed || "—"}${p.lot ? " · " + p.lot : ""}</strong></div>`
      : "";
  const receivedHtml =
    p.received_quantity !== null && p.received_quantity !== undefined
      ? `<div class="plan-row"><span>Thực nhận</span><strong>${p.received_quantity} / ${p.quantity} con${p.received_by ? " · " + p.received_by : ""}</strong></div>`
      : "";
  const rejectedHtml =
    p.status === "rejected" && p.rejected_reason
      ? `<div class="plan-note plan-note-danger">Lý do từ chối (${p.rejected_by || "—"}): ${p.rejected_reason}</div>`
      : "";
  const footerParts = [];
  if (p.created_by) footerParts.push(`Tạo bởi ${p.created_by}`);
  if (p.approved_by) footerParts.push(`Duyệt bởi ${p.approved_by}`);

  return `
    <div class="plan-card-top">
      <strong>${p.farm}${p.zone ? " · " + p.zone : ""}</strong>
      ${planDeadlineBadge(p)}
    </div>
    <div class="plan-card-status-line">${renderBadge(p.status)}</div>
    <div class="plan-card-title">${p.pig_type_name || "—"}</div>
    ${p.plan_code ? `<div class="plan-code">${p.plan_code}</div>` : ""}
    ${planStepperHtml(p)}
    <div class="plan-meta-grid">
      <div class="plan-row"><span>Ngày dự kiến</span><strong>${fmtIsoDate(p.planned_date)}</strong></div>
      <div class="plan-row"><span>Số lượng kế hoạch</span><strong>${p.quantity} con</strong></div>
      ${allocatedHtml}${shedLotHtml}${receivedHtml}
    </div>
    ${planReconcileHtml(p)}
    ${p.note ? `<div class="plan-note">${p.note}</div>` : ""}
    ${rejectedHtml}
    ${footerParts.length ? `<div class="plan-card-footer"><span>${footerParts.join(" · ")}</span></div>` : ""}
  `;
}

// Action bar modal — tái dùng nguyên planPrimaryAction/planMenuActions, chỉ
// đổi khuôn render từ nút full-width + kebab-⋮ sang 1 hàng nút phẳng. Class
// hành động (.plan-btn-*) giữ nguyên 100% nên handlePlanListClick nhận diện
// y hệt trước đây.
function planDetailActionsHtml(p) {
  const primary = planPrimaryAction(p);
  const menu = planMenuActions(p);
  const all = [...(primary ? [primary] : []), ...menu];
  if (!all.length) return "";
  return all
    .map((it) => {
      const cls = it.danger ? "btn-danger" : primary && it.cls === primary.cls ? "btn-primary" : "btn-ghost";
      return `<button type="button" class="btn ${cls} ${it.cls}" data-id="${p.id}">${it.label}</button>`;
    })
    .join("");
}

function openPlanDetailModal(planId) {
  const p = currentPlans.find((x) => String(x.id) === String(planId));
  if (!p) return;
  detailModal({
    title: `${p.plan_code || "#" + p.id} — ${p.farm}${p.zone ? " · " + p.zone : ""}`,
    bodyHtml: planDetailBodyHtml(p),
    actionsHtml: planDetailActionsHtml(p),
  });
}

async function loadPlans() {
  const res = await fetch("/api/plans");
  const plans = await res.json();
  currentPlans = plans;
  fillPlanFilterOptions(plans);
  refreshPlansView();
}

async function submitPlan(e) {
  e.preventDefault();
  const msg = el("plan-msg");
  msg.className = "msg";
  msg.textContent = "Đang lưu...";
  const body = {
    planned_date: el("plan-date").value,
    farm_id: el("plan-farm").value,
    zone_id: el("plan-zone").value,
    shed: el("plan-shed").value,
    lot: el("plan-lot").value,
    pig_type_id: el("plan-pig-type").value,
    quantity: el("plan-quantity").value,
    expected_avg_weight_kg: el("plan-weight").value,
    note: el("plan-note").value,
  };
  const isEdit = editingPlanId !== null;
  try {
    const res = await fetch(isEdit ? `/api/plans/${editingPlanId}/edit` : "/api/plans", {
      method: isEdit ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await res.json();
    if (!res.ok) {
      msg.className = "msg error";
      msg.textContent = payload.error || "Lỗi khi lưu kế hoạch.";
      return;
    }
    msg.textContent = isEdit ? "Đã lưu thay đổi." : "Đã thêm kế hoạch.";
    if (isEdit) cancelEditPlan();
    else el("plan-form").reset();
    await loadPlans();
  } catch (err) {
    msg.className = "msg error";
    msg.textContent = "Lỗi khi lưu: " + err;
  }
}

async function startEditPlan(planId) {
  const plan = currentPlans.find((p) => String(p.id) === String(planId));
  if (!plan) return;
  editingPlanId = planId;
  el("plan-date").value = plan.planned_date || "";
  el("plan-farm").value = String(plan.farm_id);
  await loadZones(plan.zone_id);
  el("plan-shed").value = plan.shed || "";
  el("plan-lot").value = plan.lot || "";
  el("plan-pig-type").value = String(plan.pig_type_id);
  el("plan-quantity").value = plan.quantity;
  el("plan-weight").value = plan.expected_avg_weight_kg ?? "";
  el("plan-note").value = plan.note || "";
  el("plan-submit-btn").textContent = "💾 Lưu thay đổi";
  el("plan-cancel-edit").classList.remove("hidden");
  const notice = el("plan-edit-notice");
  notice.textContent = `Đang sửa kế hoạch ${plan.plan_code || "#" + plan.id}`;
  notice.classList.remove("hidden");
  el("plan-section").scrollIntoView({ behavior: "smooth", block: "start" });
}

function cancelEditPlan() {
  editingPlanId = null;
  el("plan-form").reset();
  el("plan-submit-btn").textContent = "➕ Thêm kế hoạch";
  el("plan-cancel-edit").classList.add("hidden");
  el("plan-edit-notice").classList.add("hidden");
  el("plan-msg").className = "msg";
  el("plan-msg").textContent = "";
}

async function setPlanStatus(planId, status) {
  const res = await fetch(`/api/plans/${planId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    showToast(payload.error || "Lỗi khi cập nhật kế hoạch.", "danger");
    return;
  }
  await loadPlans();
}

async function approvePlan(planId) {
  const ok = await confirmModal({ title: "Duyệt kế hoạch", body: "Duyệt kế hoạch này?", confirmLabel: "Duyệt" });
  if (!ok) return;
  const res = await fetch(`/api/plans/${planId}/approve`, { method: "POST" });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    showToast(payload.error || "Lỗi khi duyệt kế hoạch.", "danger");
    return;
  }
  await loadPlans();
}

async function rejectPlan(planId) {
  const reason = await promptModal({ title: "Từ chối kế hoạch", label: "Lý do từ chối", required: true, confirmLabel: "Từ chối" });
  if (!reason) return;
  const res = await fetch(`/api/plans/${planId}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    showToast(payload.error || "Lỗi khi từ chối kế hoạch.", "danger");
    return;
  }
  await loadPlans();
}

async function recordReceived(planId) {
  const plan = currentPlans.find((p) => String(p.id) === String(planId));
  const current = plan && plan.received_quantity !== null && plan.received_quantity !== undefined ? plan.received_quantity : "";
  const value = await promptModal({
    title: "Ghi nhận số lượng thực nhận",
    label: "Số lượng thực tế đã xuất chuồng (con)",
    inputType: "number",
    initialValue: current,
  });
  if (value === null) return;
  const res = await fetch(`/api/plans/${planId}/received`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ received_quantity: value }),
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    showToast(payload.error || "Lỗi khi ghi nhận số lượng thực nhận.", "danger");
    return;
  }
  await loadPlans();
}

async function deletePlan(planId) {
  const plan = currentPlans.find((p) => String(p.id) === String(planId));
  const code = plan && plan.plan_code ? plan.plan_code : "#" + planId;
  const ok = await confirmModal({
    title: "Xoá vĩnh viễn kế hoạch?",
    body: `Kế hoạch ${code} sẽ bị xoá và không thể khôi phục.`,
    confirmLabel: "Xoá vĩnh viễn",
  });
  if (!ok) return;
  const res = await fetch(`/api/plans/${planId}`, { method: "DELETE" });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    showToast(payload.error || "Lỗi khi xoá kế hoạch.", "danger");
    return;
  }
  await loadPlans();
}

// --- Xử lý chênh lệch kế hoạch trại (đối soát) — khuôn 1:1 với
// openIncidentModal/saveIncident ở allocation.js (#incident-modal). ---
const RECONCILE_PHOTO_REQUIRED_KINDS = new Set(["culled", "cancelled"]);
let reconcileTargetPlanId = null;
let reconcileKind = null;

function openReconcileModal(planId) {
  const plan = currentPlans.find((p) => String(p.id) === String(planId));
  if (!plan) return;
  reconcileTargetPlanId = planId;
  reconcileKind = null;
  el("rc-plan-code").textContent = plan.plan_code || "#" + planId;
  // Hiện lịch sử đã ghi nhận (nếu có) NGAY trong modal, trước khi người
  // dùng ghi thêm 1 bản mới — tránh ghi trùng "Tiếp tục bán"/"Còn tại
  // trại" nhiều lần chỉ vì không nhớ đã ghi trước đó rồi (2 kind này
  // không đóng chênh lệch nên kế hoạch vẫn hiện "Cần đối soát" mãi).
  const existingBreakdown = plan.reconciliation_breakdown || [];
  const existingHtml = existingBreakdown.length
    ? `<div class="plan-row"><span>Đã ghi nhận trước</span><strong>${existingBreakdown
        .map((b) => `${RECONCILE_KIND_LABELS[b.kind] || b.kind}: ${b.quantity} con`)
        .join(", ")}</strong></div>`
    : "";
  el("rc-summary").innerHTML = `
    <div class="plan-row"><span>Kế hoạch được duyệt</span><strong>${plan.quantity} con</strong></div>
    <div class="plan-row"><span>Đã bán</span><strong>${plan.actual_sold_quantity} con</strong></div>
    <div class="plan-row"><span>Cần xử lý</span><strong>${plan.remaining_to_reconcile} con</strong></div>
    ${existingHtml}`;
  for (const kind of Object.keys(RECONCILE_KIND_LABELS)) {
    el("rc-kind-" + kind).className = "btn btn-ghost";
  }
  el("rc-quantity").value = "";
  el("rc-quantity").max = plan.remaining_to_reconcile;
  el("rc-reason").value = "";
  el("rc-photos").value = "";
  el("rc-photos-hint").textContent = "";
  el("rc-msg").className = "msg";
  el("rc-msg").textContent = "";
  el("reconcile-modal").classList.remove("hidden");
}

function closeReconcileModal() {
  reconcileTargetPlanId = null;
  reconcileKind = null;
  el("reconcile-modal").classList.add("hidden");
}

function selectReconcileKind(kind) {
  reconcileKind = kind;
  for (const k of Object.keys(RECONCILE_KIND_LABELS)) {
    el("rc-kind-" + k).className = "btn " + (k === kind ? "btn-primary" : "btn-ghost");
  }
  el("rc-photos-hint").textContent = RECONCILE_PHOTO_REQUIRED_KINDS.has(kind) ? "(bắt buộc)" : "(tuỳ chọn)";
}

async function saveReconcile() {
  const msg = el("rc-msg");
  msg.className = "msg";
  if (!reconcileKind) {
    msg.className = "msg error";
    msg.textContent = "Vui lòng chọn loại xử lý.";
    return;
  }
  const quantity = el("rc-quantity").value;
  if (!quantity || Number(quantity) <= 0) {
    msg.className = "msg error";
    msg.textContent = "Vui lòng nhập số lượng hợp lệ.";
    return;
  }
  const reason = el("rc-reason").value.trim();
  if (!reason) {
    msg.className = "msg error";
    msg.textContent = "Vui lòng nhập lý do.";
    return;
  }
  const photos = el("rc-photos").files;
  if (RECONCILE_PHOTO_REQUIRED_KINDS.has(reconcileKind) && (!photos || photos.length === 0)) {
    msg.className = "msg error";
    msg.textContent = "Vui lòng chụp/chọn ít nhất 1 ảnh làm bằng chứng.";
    return;
  }

  const formData = new FormData();
  formData.append("kind", reconcileKind);
  formData.append("quantity", quantity);
  formData.append("reason", reason);
  for (const file of photos) formData.append("photos", file);

  msg.textContent = "Đang lưu...";
  try {
    const res = await fetch(`/api/plans/${reconcileTargetPlanId}/reconciliations`, {
      method: "POST",
      body: formData,
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      msg.className = "msg error";
      msg.textContent = payload.error || "Lỗi khi xử lý chênh lệch.";
      return;
    }
  } catch (err) {
    msg.className = "msg error";
    msg.textContent = "Lỗi khi lưu: " + err;
    return;
  }
  closeReconcileModal();
  showToast("Đã ghi nhận xử lý chênh lệch.", "success");
  await loadPlans();
}

async function handlePlanListClick(e) {
  // Action bấm từ trong modal chi tiết đang mở → đóng modal trước khi
  // dispatch (trừ khi chính nút Đóng gây ra click này). Cần cho mọi action
  // mở 1 trong 6 modal tĩnh (#reconcile-modal ở trang này...): các modal đó
  // nằm trong <main>, đứng trước modal chi tiết (append cuối <body>) trong
  // DOM order — cùng z-index:100 sẽ bị modal chi tiết đè lên nếu không
  // đóng trước.
  const dm = e.target.closest(".detail-modal");
  if (dm && !e.target.closest(".detail-modal-close") && dm._detailModalClose) {
    dm._detailModalClose();
  }

  const detailBtn = e.target.closest(".plan-btn-detail");
  const disableBtn = e.target.closest(".plan-btn-disable");
  const enableBtn = e.target.closest(".plan-btn-enable");
  const approveBtn = e.target.closest(".plan-btn-approve");
  const rejectBtn = e.target.closest(".plan-btn-reject");
  const receivedBtn = e.target.closest(".plan-btn-received");
  const reconcileBtn = e.target.closest(".plan-btn-reconcile");
  const editBtn = e.target.closest(".plan-btn-edit");
  const deleteBtn = e.target.closest(".plan-btn-delete");

  if (detailBtn) {
    openPlanDetailModal(detailBtn.dataset.id);
    return;
  }
  if (editBtn) {
    await startEditPlan(editBtn.dataset.id);
  } else if (deleteBtn) {
    await deletePlan(deleteBtn.dataset.id);
  } else if (disableBtn) {
    const ok = await confirmModal({
      title: "Vô hiệu hoá kế hoạch",
      body: "Vô hiệu hoá kế hoạch này? Bạn có thể kích hoạt lại bất cứ lúc nào.",
      confirmLabel: "Vô hiệu hoá",
    });
    if (!ok) return;
    await setPlanStatus(disableBtn.dataset.id, "disabled");
  } else if (enableBtn) {
    await setPlanStatus(enableBtn.dataset.id, "approved");
  } else if (approveBtn) {
    await approvePlan(approveBtn.dataset.id);
  } else if (rejectBtn) {
    await rejectPlan(rejectBtn.dataset.id);
  } else if (receivedBtn) {
    await recordReceived(receivedBtn.dataset.id);
  } else if (reconcileBtn) {
    openReconcileModal(reconcileBtn.dataset.id);
  }
}

if (el("plan-form")) el("plan-form").addEventListener("submit", submitPlan);
document.body.addEventListener("click", handlePlanListClick);
if (el("plan-farm")) el("plan-farm").addEventListener("change", () => loadZones());
if (el("plan-cancel-edit")) el("plan-cancel-edit").addEventListener("click", cancelEditPlan);
if (el("rc-cancel")) el("rc-cancel").addEventListener("click", closeReconcileModal);
if (el("rc-save")) el("rc-save").addEventListener("click", saveReconcile);
for (const kind of Object.keys(RECONCILE_KIND_LABELS)) {
  const btn = el("rc-kind-" + kind);
  if (btn) btn.addEventListener("click", () => selectReconcileKind(kind));
}
["plan-filter-farm", "plan-filter-pig-type", "plan-filter-date-from", "plan-filter-date-to", "plan-filter-status", "plan-filter-reconcile"].forEach((id) => {
  if (el(id)) el(id).addEventListener("change", refreshPlansView);
});
if (el("plan-filter-search")) el("plan-filter-search").addEventListener("input", refreshPlansView);

// Đến từ link "Cần xử lý" trên Tổng quan (?highlight=<id>) — scroll tới
// đúng dòng bảng + tô sáng tạm thời, theo yêu cầu exception-first UX của
// brief. Dòng rút gọn không còn đủ thông tin như card cũ nên mở luôn modal
// chi tiết để giữ tác dụng "nhìn thấy ngay" của link này.
function highlightFromQuery() {
  const params = new URLSearchParams(location.search);
  const id = params.get("highlight");
  if (!id) return;
  const row = document.querySelector(`#plan-list tr[data-id="${id}"]`);
  if (!row) return;
  row.scrollIntoView({ behavior: "smooth", block: "center" });
  row.classList.add("is-highlighted");
  setTimeout(() => row.classList.remove("is-highlighted"), 3000);

  // Đến từ trang Đối soát (?highlight=<id>&action=reconcile) — mở luôn
  // modal "Xử lý chênh lệch" thay vì modal chi tiết, đỡ phải bấm thêm 1
  // lần. Không có action thì mở modal chi tiết.
  if (params.get("action") === "reconcile" && CAN_RECONCILE_PLANS) {
    openReconcileModal(id);
  } else {
    openPlanDetailModal(id);
  }
}

(async function init() {
  await loadFarms();
  await loadPigTypes();
  await loadPlans();
  highlightFromQuery();
})();
