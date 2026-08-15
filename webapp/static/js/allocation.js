// Ai tạo/quản lý/chốt bán/ghi doanh thu kế hoạch bán — khớp permission_required
// tương ứng ở server (webapp/routes/plans.py, route /api/allocations*).
const CAN_CREATE_ALLOCATION = (window.CURRENT_USER_PERMISSIONS || []).includes("plans.allocation_create");
const CAN_MANAGE_ALLOCATIONS = (window.CURRENT_USER_PERMISSIONS || []).includes("plans.allocation_manage");
const CAN_ALLOC_SALE_DETAILS = (window.CURRENT_USER_PERMISSIONS || []).includes("plans.sale_details");
const CAN_ALLOC_REVENUE_DETAILS = (window.CURRENT_USER_PERMISSIONS || []).includes("plans.revenue_details");

const ALLOC_PAYMENT_METHOD_LABEL = {
  bank_transfer_immediate: "Chuyển khoản ngay",
  bank_transfer_24h: "Chuyển khoản trước 24h",
  cash: "Tiền mặt",
  credit: "Công nợ",
  other: "Khác",
};

let currentAllocations = [];

function fillSalePlanOptions(plans) {
  const select = el("alloc-sale-plan");
  if (!select) return;
  const current = select.value;
  const eligible = (plans || []).filter((p) => p.status === "approved" && p.remaining_quantity > 0);
  if (!eligible.length) {
    select.innerHTML = `<option value="" disabled selected>Chưa có kế hoạch trại nào còn số lượng để bán</option>`;
    el("alloc-remaining-hint").textContent = "";
    return;
  }
  select.innerHTML = eligible
    .map(
      (p) =>
        `<option value="${p.id}" data-remaining="${p.remaining_quantity}">${p.plan_code || "#" + p.id} — ${p.farm}${p.zone ? " · " + p.zone : ""} · ${p.pig_type_name || ""} (còn ${p.remaining_quantity} con)</option>`
    )
    .join("");
  if ([...select.options].some((o) => o.value === current)) select.value = current;
  updateRemainingHint();
}
window.onPlansLoaded = fillSalePlanOptions;

function updateRemainingHint() {
  const select = el("alloc-sale-plan");
  const hint = el("alloc-remaining-hint");
  if (!select || !hint) return;
  const opt = select.options[select.selectedIndex];
  hint.textContent = opt && opt.dataset.remaining ? `Còn lại: ${opt.dataset.remaining} con` : "";
}

function allocationStatusBadge(a) {
  if (a.status === "done") return `<span class="plan-badge done">Đã bán</span>`;
  if (a.status === "cancelled") return `<span class="plan-badge cancelled">Đã hủy</span>`;
  if (a.status === "disabled") return `<span class="plan-badge disabled">🚫 Đã vô hiệu hoá</span>`;
  if (a.reached_target) return `<span class="plan-badge reached">🔔 Đã đạt giá mong muốn</span>`;
  if (a.days_left === null || a.days_left === undefined) return "";
  if (a.days_left < 0) return `<span class="plan-badge overdue">Đã qua ${Math.abs(a.days_left)} ngày</span>`;
  if (a.days_left === 0) return `<span class="plan-badge today">Hôm nay</span>`;
  return `<span class="plan-badge">Còn ${a.days_left} ngày</span>`;
}

function renderAllocations(allocs) {
  const box = el("allocation-list");
  if (!box) return;
  if (!allocs.length) {
    box.innerHTML = `<p class="msg">Chưa có kế hoạch bán nào.</p>`;
    return;
  }

  box.innerHTML = allocs
    .map((a) => {
      const hasCur = a.current_price !== null && a.current_price !== undefined;
      const scopeLabel = a.current_price_is_national
        ? "cả nước — trại chưa gán tỉnh hoặc tỉnh chưa có dữ liệu"
        : `tỉnh ${a.province}`;
      const curHtml = hasCur
        ? `${fmtPrice(a.current_price)}<span class="unit"> đ/kg</span> (${scopeLabel}, ngày ${a.current_price_date})`
        : "Chưa có dữ liệu";
      const diff = hasCur && a.selling_price ? a.current_price - a.selling_price : null;
      const diffHtml =
        diff === null
          ? ""
          : `<div class="plan-row"><span>Chênh lệch</span><strong class="${diff >= 0 ? "plan-up" : "plan-down"}">${diff >= 0 ? "+" : ""}${fmtPrice(diff)} đ/kg</strong></div>`;
      const actualHtml =
        a.status === "done" && a.actual_price !== null && a.actual_price !== undefined
          ? `<div class="plan-row"><span>Giá bán thực tế</span><strong>${fmtPrice(a.actual_price)} đ/kg</strong></div>
             <div class="plan-row"><span>Số lượng đã bán</span><strong>${a.actual_quantity} con</strong></div>`
          : "";
      let actions = "";
      if (CAN_MANAGE_ALLOCATIONS) {
        if (a.status === "active") {
          actions += `<button type="button" class="btn alloc-btn-done" data-id="${a.id}">✅ Đã bán</button>
             <button type="button" class="btn alloc-btn-disable" data-id="${a.id}">🚫 Vô hiệu hoá</button>`;
        } else if (a.status === "disabled") {
          actions += `<button type="button" class="btn alloc-btn-enable" data-id="${a.id}">▶️ Kích hoạt lại</button>`;
        }
      }
      if (a.status === "active" && CAN_ALLOC_SALE_DETAILS) {
        actions += `<button type="button" class="btn alloc-btn-sale-details" data-id="${a.id}">🤝 Chốt bán hàng</button>
             <button type="button" class="btn alloc-btn-quotation" data-id="${a.id}">⬇️ Xuất chào hàng</button>`;
      }
      if (a.status === "done" && CAN_ALLOC_REVENUE_DETAILS) {
        actions += `<button type="button" class="btn alloc-btn-revenue" data-id="${a.id}">💰 Ghi nhận doanh thu</button>`;
      }
      const reachedCls =
        a.status === "disabled" ? "plan-card-disabled" : a.reached_target && a.status === "active" ? "plan-card-reached" : "";
      const saleDetailsHtml =
        a.customer_name || a.contact_note || a.confirmed_sale_at || a.delivery_time || a.payment_method
          ? `${a.customer_name ? `<div class="plan-row"><span>Khách hàng</span><strong>${a.customer_name}${a.customer_phone ? " · " + a.customer_phone : ""}</strong></div>` : ""}
             ${a.confirmed_sale_at ? `<div class="plan-row"><span>Ngày chốt bán</span><strong>${fmtIsoDate(a.confirmed_sale_at)}</strong></div>` : ""}
             ${a.delivery_time ? `<div class="plan-row"><span>Khung giờ giao</span><strong>${a.delivery_time}</strong></div>` : ""}
             ${a.payment_method ? `<div class="plan-row"><span>Thanh toán</span><strong>${ALLOC_PAYMENT_METHOD_LABEL[a.payment_method] || a.payment_method}</strong></div>` : ""}
             ${a.contact_note ? `<div class="plan-note">Liên hệ (${a.contacted_by || "—"}): ${a.contact_note}</div>` : ""}`
          : "";
      const revenueDetailsHtml =
        a.paid_amount || a.weighing_ref || a.invoice_number
          ? `${a.paid_amount ? `<div class="plan-row"><span>Đã thu tiền</span><strong>${fmtPrice(a.paid_amount)} đ${a.paid_at ? " · " + fmtIsoDate(a.paid_at.slice(0, 10)) : ""}</strong></div>` : ""}
             ${a.weighing_ref ? `<div class="plan-row"><span>Chứng từ cân</span><strong>${a.weighing_ref}</strong></div>` : ""}
             ${a.invoice_number ? `<div class="plan-row"><span>Số hoá đơn</span><strong>${a.invoice_number}${a.invoiced_by ? " · " + a.invoiced_by : ""}</strong></div>` : ""}`
          : "";

      return `<article class="plan-card ${reachedCls}">
        <div class="plan-card-head">
          <strong>${a.farm}${a.zone ? " · " + a.zone : ""}</strong>
          ${allocationStatusBadge(a)}
        </div>
        ${a.plan_code ? `<div class="plan-code">${a.plan_code}</div>` : ""}
        ${a.sale_plan_code ? `<div class="plan-row"><span>Từ kế hoạch trại</span><strong>${a.sale_plan_code}</strong></div>` : ""}
        <div class="plan-row"><span>Loại heo</span><strong>${a.pig_type_name || "—"}</strong></div>
        <div class="plan-row"><span>Ngày dự kiến</span><strong>${fmtIsoDate(a.planned_date)}</strong></div>
        <div class="plan-row"><span>Số lượng</span><strong>${a.quantity} con</strong></div>
        <div class="plan-row"><span>Giá chào bán</span><strong>${a.selling_price ? fmtPrice(a.selling_price) + " đ/kg" : "—"}</strong></div>
        <div class="plan-row"><span>Giá hiện tại</span><strong>${curHtml}</strong></div>
        ${diffHtml}
        ${saleDetailsHtml}
        ${actualHtml}
        ${revenueDetailsHtml}
        ${a.note ? `<div class="plan-note">${a.note}</div>` : ""}
        ${actions ? `<div class="plan-actions">${actions}</div>` : ""}
      </article>`;
    })
    .join("");
}

async function loadAllocations() {
  const box = el("allocation-list");
  if (!box) return;
  const res = await fetch("/api/allocations");
  const allocs = await res.json();
  currentAllocations = allocs;
  renderAllocations(allocs);
}

async function submitAllocation(e) {
  e.preventDefault();
  const msg = el("allocation-msg");
  msg.className = "msg";
  msg.textContent = "Đang lưu...";
  const body = {
    sale_plan_id: el("alloc-sale-plan").value,
    quantity: el("alloc-quantity").value,
    selling_price: el("alloc-selling-price").value,
    note: el("alloc-note").value,
  };
  try {
    const res = await fetch("/api/allocations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await res.json();
    if (!res.ok) {
      msg.className = "msg error";
      msg.textContent = payload.error || "Lỗi khi tạo kế hoạch bán.";
      return;
    }
    msg.textContent = "Đã tạo kế hoạch bán.";
    el("allocation-form").reset();
    await loadPlans();
    await loadAllocations();
  } catch (err) {
    msg.className = "msg error";
    msg.textContent = "Lỗi khi lưu: " + err;
  }
}

async function markAllocationDone(allocationId) {
  const actualPrice = prompt("Giá bán thực tế (đ/kg):");
  if (actualPrice === null) return;
  const actualQuantity = prompt("Số lượng đã bán thực tế (con):");
  if (actualQuantity === null) return;
  const res = await fetch(`/api/allocations/${allocationId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: "done", actual_price: actualPrice, actual_quantity: actualQuantity }),
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    alert(payload.error || "Lỗi khi cập nhật kế hoạch bán.");
    return;
  }
  await loadAllocations();
}

async function setAllocationStatus(allocationId, status) {
  const res = await fetch(`/api/allocations/${allocationId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    alert(payload.error || "Lỗi khi cập nhật kế hoạch bán.");
    return;
  }
  await loadAllocations();
}

let saleDetailsAllocationId = null;

async function openSaleDetailsModal(allocationId, alloc) {
  saleDetailsAllocationId = allocationId;
  const res = await fetch("/api/customers?active_only=true");
  const customers = await res.json();
  const select = el("sd-customer");
  select.innerHTML =
    `<option value="">-- Chưa chọn --</option>` +
    customers
      .map(
        (c) =>
          `<option value="${c.id}" ${alloc.customer_id === c.id ? "selected" : ""}>${c.name}${c.phone ? " · " + c.phone : ""}</option>`
      )
      .join("");
  el("sd-contact-note").value = "";
  el("sd-confirmed-date").value = alloc.confirmed_sale_at || "";
  el("sd-selling-price").value = alloc.selling_price || "";
  el("sd-delivery-time").value = alloc.delivery_time || "";
  el("sd-payment-method").value = alloc.payment_method || "";
  el("sd-msg").className = "msg";
  el("sd-msg").textContent = "";
  el("sale-details-modal").classList.remove("hidden");
}

function closeSaleDetailsModal() {
  saleDetailsAllocationId = null;
  el("sale-details-modal").classList.add("hidden");
}

async function saveSaleDetails() {
  const body = {
    customer_id: el("sd-customer").value || null,
    contact_note: el("sd-contact-note").value,
    confirmed_sale_at: el("sd-confirmed-date").value || null,
    selling_price: el("sd-selling-price").value || null,
    delivery_time: el("sd-delivery-time").value,
    payment_method: el("sd-payment-method").value || null,
  };
  const res = await fetch(`/api/allocations/${saleDetailsAllocationId}/sale-details`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    el("sd-msg").className = "msg error";
    el("sd-msg").textContent = payload.error || "Lỗi khi lưu thông tin bán hàng.";
    return;
  }
  closeSaleDetailsModal();
  await loadAllocations();
}

let revenueAllocationId = null;

async function openRevenueModal(allocationId, alloc) {
  revenueAllocationId = allocationId;
  el("rv-paid-amount").value = alloc.paid_amount || "";
  el("rv-weighing-ref").value = alloc.weighing_ref || "";
  el("rv-invoice-number").value = alloc.invoice_number || "";
  el("rv-msg").className = "msg";
  el("rv-msg").textContent = "";
  el("revenue-modal").classList.remove("hidden");
}

function closeRevenueModal() {
  revenueAllocationId = null;
  el("revenue-modal").classList.add("hidden");
}

async function saveRevenueDetails() {
  const body = {
    paid_amount: el("rv-paid-amount").value || null,
    weighing_ref: el("rv-weighing-ref").value,
    invoice_number: el("rv-invoice-number").value,
  };
  const res = await fetch(`/api/allocations/${revenueAllocationId}/revenue-details`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    el("rv-msg").className = "msg error";
    el("rv-msg").textContent = payload.error || "Lỗi khi lưu thông tin doanh thu.";
    return;
  }
  closeRevenueModal();
  await loadAllocations();
}

async function handleAllocationListClick(e) {
  const doneBtn = e.target.closest(".alloc-btn-done");
  const disableBtn = e.target.closest(".alloc-btn-disable");
  const enableBtn = e.target.closest(".alloc-btn-enable");
  const saleDetailsBtn = e.target.closest(".alloc-btn-sale-details");
  const revenueBtn = e.target.closest(".alloc-btn-revenue");
  const quotationBtn = e.target.closest(".alloc-btn-quotation");
  if (doneBtn) {
    await markAllocationDone(doneBtn.dataset.id);
  } else if (disableBtn) {
    if (!confirm("Vô hiệu hoá kế hoạch bán này? Bạn có thể kích hoạt lại bất cứ lúc nào.")) return;
    await setAllocationStatus(disableBtn.dataset.id, "disabled");
  } else if (enableBtn) {
    await setAllocationStatus(enableBtn.dataset.id, "active");
  } else if (saleDetailsBtn) {
    const alloc = currentAllocations.find((a) => String(a.id) === saleDetailsBtn.dataset.id);
    if (alloc) await openSaleDetailsModal(saleDetailsBtn.dataset.id, alloc);
  } else if (revenueBtn) {
    const alloc = currentAllocations.find((a) => String(a.id) === revenueBtn.dataset.id);
    if (alloc) await openRevenueModal(revenueBtn.dataset.id, alloc);
  } else if (quotationBtn) {
    window.open(`/api/allocations/quotation.xlsx?ids=${quotationBtn.dataset.id}`, "_blank");
  }
}

if (el("allocation-form")) el("allocation-form").addEventListener("submit", submitAllocation);
if (el("allocation-list")) el("allocation-list").addEventListener("click", handleAllocationListClick);
if (el("alloc-sale-plan")) el("alloc-sale-plan").addEventListener("change", updateRemainingHint);
if (el("sd-save")) el("sd-save").addEventListener("click", saveSaleDetails);
if (el("sd-cancel")) el("sd-cancel").addEventListener("click", closeSaleDetailsModal);
if (el("rv-save")) el("rv-save").addEventListener("click", saveRevenueDetails);
if (el("rv-cancel")) el("rv-cancel").addEventListener("click", closeRevenueModal);

if (el("allocation-list")) {
  (async function initAllocations() {
    await loadAllocations();
  })();
}
