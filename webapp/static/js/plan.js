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

function planStatusBadge(plan) {
  if (plan.status === "pending_approval") return `<span class="plan-badge pending-approval">⏳ Chờ duyệt</span>`;
  if (plan.status === "rejected") return `<span class="plan-badge rejected">❌ Bị từ chối</span>`;
  if (plan.status === "cancelled") return `<span class="plan-badge cancelled">Đã hủy</span>`;
  if (plan.status === "disabled") return `<span class="plan-badge disabled">🚫 Đã vô hiệu hoá</span>`;
  if (plan.remaining_quantity !== undefined && plan.remaining_quantity <= 0 && plan.status === "approved") {
    return `<span class="plan-badge done">Đã phân bổ hết</span>`;
  }
  if (plan.days_left === null || plan.days_left === undefined) return "";
  if (plan.days_left < 0) return `<span class="plan-badge overdue">Đã qua ${Math.abs(plan.days_left)} ngày</span>`;
  if (plan.days_left === 0) return `<span class="plan-badge today">Hôm nay</span>`;
  return `<span class="plan-badge">Còn ${plan.days_left} ngày</span>`;
}

// Ai duyệt/từ chối được kế hoạch trại — khớp @permission_required(perm.PLAN_REVIEW) ở server.
const CAN_REVIEW_PLANS = (window.CURRENT_USER_PERMISSIONS || []).includes("plans.review");
// Ai ghi nhận số lượng thực nhận — khớp @permission_required(perm.PLAN_RECEIVE) ở server.
const CAN_RECEIVE_PLANS = (window.CURRENT_USER_PERMISSIONS || []).includes("plans.receive");

// Danh sách kế hoạch trại đang hiển thị — allocation.js dùng lại để đổ vào
// dropdown "Từ kế hoạch trại" khi tạo kế hoạch bán.
let currentPlans = [];

function renderPlans(plans) {
  const box = el("plan-list");
  if (!box) return;
  if (!plans.length) {
    box.innerHTML = `<p class="msg">Chưa có kế hoạch nào.</p>`;
    return;
  }

  box.innerHTML = plans
    .map((p) => {
      let actions = "";
      if (CAN_REVIEW_PLANS) {
        if (p.status === "pending_approval") {
          actions = `<button type="button" class="btn plan-btn-approve" data-id="${p.id}">✅ Duyệt</button>
             <button type="button" class="btn plan-btn-reject" data-id="${p.id}">❌ Từ chối</button>`;
        } else if (p.status === "disabled") {
          actions = `<button type="button" class="btn plan-btn-enable" data-id="${p.id}">▶️ Kích hoạt lại</button>`;
        } else if (p.status === "approved") {
          actions = `<button type="button" class="btn plan-btn-disable" data-id="${p.id}">🚫 Vô hiệu hoá</button>`;
        }
      }
      if (p.status === "approved" && CAN_RECEIVE_PLANS) {
        actions += `<button type="button" class="btn plan-btn-received" data-id="${p.id}">📦 Ghi nhận đã xuất chuồng</button>`;
      }
      const reachedCls = p.status === "disabled" ? "plan-card-disabled" : "";
      const approvedHtml = p.approved_by
        ? `<div class="plan-row"><span>Duyệt bởi</span><strong>${p.approved_by}</strong></div>`
        : "";
      const rejectedHtml =
        p.status === "rejected" && p.rejected_reason
          ? `<div class="plan-note plan-note-danger">Lý do từ chối (${p.rejected_by || "—"}): ${p.rejected_reason}</div>`
          : "";
      const receivedHtml =
        p.received_quantity !== null && p.received_quantity !== undefined
          ? `<div class="plan-row"><span>Thực nhận</span><strong>${p.received_quantity} / ${p.quantity} con${p.received_by ? " · " + p.received_by : ""}</strong></div>`
          : "";
      const allocatedHtml =
        p.status === "approved"
          ? `<div class="plan-row"><span>Đã phân bổ</span><strong>${p.allocated_quantity} / ${p.quantity} con (còn ${p.remaining_quantity})</strong></div>`
          : "";

      return `<article class="plan-card ${reachedCls}">
        <div class="plan-card-head">
          <strong>${p.farm}${p.zone ? " · " + p.zone : ""}</strong>
          ${planStatusBadge(p)}
        </div>
        ${p.plan_code ? `<div class="plan-code">${p.plan_code}</div>` : ""}
        ${p.created_by ? `<div class="plan-row"><span>Tạo bởi</span><strong>${p.created_by}</strong></div>` : ""}
        ${approvedHtml}
        <div class="plan-row"><span>Loại heo</span><strong>${p.pig_type_name || "—"}</strong></div>
        <div class="plan-row"><span>Ngày dự kiến</span><strong>${fmtIsoDate(p.planned_date)}</strong></div>
        ${p.shed || p.lot ? `<div class="plan-row"><span>Chuồng/Lô</span><strong>${p.shed || "—"}${p.lot ? " · " + p.lot : ""}</strong></div>` : ""}
        <div class="plan-row"><span>Số lượng kế hoạch</span><strong>${p.quantity} con</strong></div>
        ${allocatedHtml}
        ${receivedHtml}
        ${p.note ? `<div class="plan-note">${p.note}</div>` : ""}
        ${rejectedHtml}
        ${actions ? `<div class="plan-actions">${actions}</div>` : ""}
      </article>`;
    })
    .join("");
}

async function loadPlans() {
  const res = await fetch("/api/plans");
  const plans = await res.json();
  currentPlans = plans;
  renderPlans(plans);
  if (window.onPlansLoaded) window.onPlansLoaded(plans);
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
    note: el("plan-note").value,
  };
  try {
    const res = await fetch("/api/plans", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await res.json();
    if (!res.ok) {
      msg.className = "msg error";
      msg.textContent = payload.error || "Lỗi khi lưu kế hoạch.";
      return;
    }
    msg.textContent = "Đã thêm kế hoạch.";
    el("plan-form").reset();
    await loadPlans();
  } catch (err) {
    msg.className = "msg error";
    msg.textContent = "Lỗi khi lưu: " + err;
  }
}

async function setPlanStatus(planId, status) {
  const res = await fetch(`/api/plans/${planId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    alert(payload.error || "Lỗi khi cập nhật kế hoạch.");
    return;
  }
  await loadPlans();
}

async function approvePlan(planId) {
  if (!confirm("Duyệt kế hoạch này?")) return;
  const res = await fetch(`/api/plans/${planId}/approve`, { method: "POST" });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    alert(payload.error || "Lỗi khi duyệt kế hoạch.");
    return;
  }
  await loadPlans();
}

async function rejectPlan(planId) {
  const reason = prompt("Lý do từ chối:");
  if (!reason) return;
  const res = await fetch(`/api/plans/${planId}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    alert(payload.error || "Lỗi khi từ chối kế hoạch.");
    return;
  }
  await loadPlans();
}

async function recordReceived(planId) {
  const plan = currentPlans.find((p) => String(p.id) === String(planId));
  const current = plan && plan.received_quantity !== null && plan.received_quantity !== undefined ? plan.received_quantity : "";
  const value = prompt("Số lượng thực tế đã xuất chuồng (con):", current);
  if (value === null) return;
  const res = await fetch(`/api/plans/${planId}/received`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ received_quantity: value }),
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    alert(payload.error || "Lỗi khi ghi nhận số lượng thực nhận.");
    return;
  }
  await loadPlans();
}

async function handlePlanListClick(e) {
  const disableBtn = e.target.closest(".plan-btn-disable");
  const enableBtn = e.target.closest(".plan-btn-enable");
  const approveBtn = e.target.closest(".plan-btn-approve");
  const rejectBtn = e.target.closest(".plan-btn-reject");
  const receivedBtn = e.target.closest(".plan-btn-received");
  if (disableBtn) {
    if (!confirm("Vô hiệu hoá kế hoạch này? Bạn có thể kích hoạt lại bất cứ lúc nào.")) return;
    await setPlanStatus(disableBtn.dataset.id, "disabled");
  } else if (enableBtn) {
    await setPlanStatus(enableBtn.dataset.id, "approved");
  } else if (approveBtn) {
    await approvePlan(approveBtn.dataset.id);
  } else if (rejectBtn) {
    await rejectPlan(rejectBtn.dataset.id);
  } else if (receivedBtn) {
    await recordReceived(receivedBtn.dataset.id);
  }
}

if (el("plan-form")) el("plan-form").addEventListener("submit", submitPlan);
if (el("plan-list")) el("plan-list").addEventListener("click", handlePlanListClick);
if (el("plan-farm")) el("plan-farm").addEventListener("change", () => loadZones());

(async function init() {
  await loadFarms();
  await loadPigTypes();
  await loadPlans();
})();
