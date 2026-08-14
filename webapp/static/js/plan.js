const el = (id) => document.getElementById(id);
const fmtPrice = (v) => (v === null || v === undefined ? "" : Math.round(v).toLocaleString("vi-VN"));

function fmtIsoDate(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

async function loadFarms(selectCode) {
  const res = await fetch("/api/farms");
  const farms = await res.json();
  const select = el("plan-farm");
  const current = selectCode || select.value;
  select.innerHTML = farms.map((f) => `<option value="${f}">${f}</option>`).join("");
  if (farms.includes(current)) select.value = current;
  await loadZones();
}

async function addFarm() {
  const code = (prompt("Nhập mã trang trại mới (VD: XH4):") || "").trim();
  if (!code) return;
  const res = await fetch("/api/farms", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });
  const payload = await res.json();
  if (!res.ok) {
    alert(payload.error || "Lỗi khi thêm trang trại.");
    return;
  }
  await loadFarms(code);
}

async function loadZones(selectCode) {
  const farm = el("plan-farm").value;
  const select = el("plan-zone");
  if (!farm) {
    select.innerHTML = `<option value="" disabled selected>Chọn trang trại trước</option>`;
    return;
  }
  const res = await fetch(`/api/zones?farm=${encodeURIComponent(farm)}`);
  const zones = await res.json();
  const current = selectCode || select.value;
  if (!zones.length) {
    select.innerHTML = `<option value="" disabled selected>Chưa có khu — bấm ➕ Thêm khu</option>`;
    return;
  }
  select.innerHTML = zones.map((z) => `<option value="${z}">${z}</option>`).join("");
  if (zones.includes(current)) select.value = current;
}

async function addZone() {
  const farm = el("plan-farm").value;
  if (!farm) {
    alert("Vui lòng chọn trang trại trước.");
    return;
  }
  const code = (prompt(`Nhập tên khu mới cho ${farm} (VD: Khu A):`) || "").trim();
  if (!code) return;
  const res = await fetch("/api/zones", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ farm, code }),
  });
  const payload = await res.json();
  if (!res.ok) {
    alert(payload.error || "Lỗi khi thêm khu.");
    return;
  }
  await loadZones(code);
}

function planStatusBadge(plan) {
  if (plan.status === "done") return `<span class="plan-badge done">Đã bán</span>`;
  if (plan.status === "cancelled") return `<span class="plan-badge cancelled">Đã hủy</span>`;
  if (plan.reached_target) return `<span class="plan-badge reached">🔔 Đã đạt giá mong muốn</span>`;
  if (plan.days_left === null || plan.days_left === undefined) return "";
  if (plan.days_left < 0) return `<span class="plan-badge overdue">Đã qua ${Math.abs(plan.days_left)} ngày</span>`;
  if (plan.days_left === 0) return `<span class="plan-badge today">Hôm nay</span>`;
  return `<span class="plan-badge">Còn ${plan.days_left} ngày</span>`;
}

function renderPlans(plans) {
  const box = el("plan-list");
  if (!plans.length) {
    box.innerHTML = `<p class="msg">Chưa có kế hoạch nào.</p>`;
    return;
  }

  box.innerHTML = plans
    .map((p) => {
      const hasCur = p.current_price !== null && p.current_price !== undefined;
      const curHtml = hasCur
        ? `${fmtPrice(p.current_price)}<span class="unit"> đ/kg</span> (ngày ${p.current_price_date})`
        : "Chưa có dữ liệu";
      const diff = hasCur ? p.current_price - p.target_price : null;
      const diffHtml =
        diff === null
          ? ""
          : `<div class="plan-row"><span>Chênh lệch</span><strong class="${diff >= 0 ? "plan-up" : "plan-down"}">${diff >= 0 ? "+" : ""}${fmtPrice(diff)} đ/kg</strong></div>`;
      const actions =
        p.status === "active"
          ? `<button type="button" class="btn plan-btn-done" data-id="${p.id}">✅ Đã bán</button>
             <button type="button" class="btn plan-btn-delete" data-id="${p.id}">🗑️ Xóa</button>`
          : `<button type="button" class="btn plan-btn-delete" data-id="${p.id}">🗑️ Xóa</button>`;
      const reachedCls = p.reached_target && p.status === "active" ? "plan-card-reached" : "";

      return `<article class="plan-card ${reachedCls}">
        <div class="plan-card-head">
          <strong>${p.farm}${p.zone ? " · " + p.zone : ""}</strong>
          ${planStatusBadge(p)}
        </div>
        <div class="plan-row"><span>Ngày dự kiến</span><strong>${fmtIsoDate(p.planned_date)}</strong></div>
        <div class="plan-row"><span>Số lượng</span><strong>${p.quantity} con</strong></div>
        <div class="plan-row"><span>Giá mong muốn</span><strong>${fmtPrice(p.target_price)} đ/kg</strong></div>
        <div class="plan-row"><span>Giá hiện tại</span><strong>${curHtml}</strong></div>
        ${diffHtml}
        ${p.note ? `<div class="plan-note">${p.note}</div>` : ""}
        <div class="plan-actions">${actions}</div>
      </article>`;
    })
    .join("");
}

async function loadPlans() {
  const res = await fetch("/api/plans");
  const plans = await res.json();
  renderPlans(plans);
}

async function submitPlan(e) {
  e.preventDefault();
  const msg = el("plan-msg");
  msg.className = "msg";
  msg.textContent = "Đang lưu...";
  const body = {
    planned_date: el("plan-date").value,
    farm: el("plan-farm").value,
    zone: el("plan-zone").value,
    quantity: el("plan-quantity").value,
    target_price: el("plan-target-price").value,
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

async function handlePlanListClick(e) {
  const doneBtn = e.target.closest(".plan-btn-done");
  const delBtn = e.target.closest(".plan-btn-delete");
  if (doneBtn) {
    await fetch(`/api/plans/${doneBtn.dataset.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "done" }),
    });
    await loadPlans();
  } else if (delBtn) {
    if (!confirm("Xóa kế hoạch này?")) return;
    await fetch(`/api/plans/${delBtn.dataset.id}`, { method: "DELETE" });
    await loadPlans();
  }
}

el("plan-form").addEventListener("submit", submitPlan);
el("plan-list").addEventListener("click", handlePlanListClick);
el("btn-add-farm").addEventListener("click", addFarm);
el("btn-add-zone").addEventListener("click", addZone);
el("plan-farm").addEventListener("change", () => loadZones());

(async function init() {
  await loadFarms();
  await loadPlans();
})();
