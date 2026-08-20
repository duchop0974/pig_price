// Trang "Chào hàng" (Phase 4, brief nghiệp vụ — tách từ allocations.html/
// allocation.js cũ): chọn nguồn heo từ kế hoạch trại đã duyệt, gán giá, xây
// giỏ nháp rồi tạo đơn hàng mới. KHÔNG còn danh sách đơn hàng/modal quản lý
// đơn ở đây — đó là trang "Chốt bán" (chot_ban.js).
const CAN_CREATE_ALLOCATION = (window.CURRENT_USER_PERMISSIONS || []).includes("plans.allocation_create");

let currentAvailablePlans = [];
// Giỏ nháp phía client (đơn hàng đang xây dựng, CHƯA gọi API) — mỗi phần tử:
// {sale_plan_id, quantity, selling_price, note, _display: {...}}.
let draftLines = [];
// Khi khác null: form "Thêm dòng heo" đang thêm trực tiếp vào 1 đơn ĐANG CÓ
// (đến từ nút "➕ Thêm dòng" ở trang Chốt bán, qua query param) thay vì xây
// đơn mới — gọi API ngay, không qua giỏ nháp.
let targetOrderId = null;

function fillSalePlanOptions(plans) {
  const select = el("line-sale-plan");
  if (!select) return;
  const current = select.value;
  if (!plans.length) {
    select.innerHTML = `<option value="" disabled selected>Chưa có nguồn heo nào còn số lượng để bán</option>`;
    updateRemainingHint();
    return;
  }
  select.innerHTML =
    `<option value="" disabled ${current ? "" : "selected"}>-- Chọn nguồn heo --</option>` +
    plans
      .map(
        (p) =>
          `<option value="${p.id}">${p.plan_code || "#" + p.id} — ${p.farm}${p.zone ? " · " + p.zone : ""} · ${p.pig_type_name || ""} (còn ${p.remaining_quantity} con)</option>`
      )
      .join("");
  if ([...select.options].some((o) => o.value === current)) select.value = current;
  updateRemainingHint();
}

// Danh sách option cho 2 bộ lọc Trại/Loại heo — lấy trực tiếp từ dữ liệu đã
// tải (không gọi API riêng), giữ lại lựa chọn hiện tại nếu vẫn còn hợp lệ.
function fillFilterOptions(plans) {
  const farmSelect = el("filter-farm");
  const typeSelect = el("filter-pig-type");
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

// Tổng quan nguồn cung — nhóm theo loại heo, chỉ tính các kế hoạch còn số
// lượng (giữ đúng cách tính của "Tổng hợp theo loại heo" cũ).
function renderSupplyCards(plans) {
  const box = el("supply-summary-cards");
  if (!box) return;
  const available = plans.filter((p) => p.remaining_quantity > 0);
  if (!available.length) {
    box.innerHTML = `<p class="msg">Chưa có nguồn cung nào từ trại.</p>`;
    return;
  }
  const byType = new Map();
  for (const p of available) {
    const key = p.pig_type_name || "—";
    const cur = byType.get(key) || { remaining: 0, count: 0 };
    cur.remaining += p.remaining_quantity;
    cur.count += 1;
    byType.set(key, cur);
  }
  box.innerHTML = [...byType.entries()]
    .map(
      ([name, v]) => `<div class="kpi-tile">
        <div class="kpi-label">${name}</div>
        <div class="kpi-value">${v.remaining}<span class="unit"> con</span></div>
        <div class="kpi-sub">${v.count} kế hoạch</div>
      </div>`
    )
    .join("");
}

// Lọc thuần phía client (Trại/Loại heo/Khoảng ngày/Trạng thái/Search) — đọc
// trực tiếp giá trị hiện tại của các control filter, không giữ state riêng
// để tránh lệch đồng bộ với DOM.
function applyAvailablePlanFilters(plans) {
  const farm = el("filter-farm") ? el("filter-farm").value : "";
  const pigType = el("filter-pig-type") ? el("filter-pig-type").value : "";
  const dateFrom = el("filter-date-from") ? el("filter-date-from").value : "";
  const dateTo = el("filter-date-to") ? el("filter-date-to").value : "";
  const status = el("filter-status") ? el("filter-status").value : "available";
  const q = (el("filter-search") ? el("filter-search").value : "").trim().toLowerCase();
  return plans.filter((p) => {
    if (farm && p.farm !== farm) return false;
    if (pigType && p.pig_type_name !== pigType) return false;
    if (dateFrom && p.planned_date && p.planned_date < dateFrom) return false;
    if (dateTo && p.planned_date && p.planned_date > dateTo) return false;
    if (status === "available" && p.remaining_quantity <= 0) return false;
    if (status === "soldout" && p.remaining_quantity > 0) return false;
    if (q) {
      const hay = `${p.farm || ""} ${p.zone || ""} ${p.plan_code || ""} ${p.note || ""} ${p.pig_type_name || ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

function renderAvailablePlans(plans) {
  const box = el("available-plans-list");
  if (!box) return;
  if (!plans.length) {
    box.innerHTML = `<tr><td colspan="9">Không có nguồn cung phù hợp bộ lọc.</td></tr>`;
    return;
  }
  const selectEl = el("line-sale-plan");
  const selectedId = selectEl ? selectEl.value : "";
  box.innerHTML = plans
    .map((p) => {
      const soldOut = p.remaining_quantity <= 0;
      const needsReconcile = p.reconciliation_status === "needs_reconciliation";
      const isSelected = !soldOut && CAN_CREATE_ALLOCATION && String(p.id) === selectedId;
      const rowCls = [soldOut ? "is-soldout" : "", isSelected ? "is-selected" : ""].filter(Boolean).join(" ");
      const statusBadge = soldOut
        ? `<span class="badge">Đã bán hết</span>`
        : needsReconcile
          ? `<span class="badge badge-warning">⚠ Cần đối soát</span>`
          : `<span class="badge badge-success">Có thể bán</span>`;
      let actionCell = "";
      if (CAN_CREATE_ALLOCATION) {
        actionCell = soldOut
          ? `<button type="button" class="btn btn-ghost btn-sm" disabled>Đã bán hết</button>`
          : isSelected
            ? `<button type="button" class="btn btn-primary btn-sm" disabled>✓ Đã chọn</button>`
            : `<button type="button" class="btn btn-ghost btn-sm btn-pick-plan" data-id="${p.id}">Chọn nguồn này</button>`;
      }
      return `<tr class="${rowCls}">
        <td data-label="Trại">${p.farm}${p.zone ? " · " + p.zone : ""}</td>
        <td data-label="Loại heo">${p.pig_type_name || "—"}</td>
        <td data-label="Kế hoạch">${p.plan_code || "—"}</td>
        <td data-label="Ngày">${fmtIsoDate(p.planned_date)}</td>
        <td data-label="Được duyệt">${p.quantity}</td>
        <td data-label="Đã phân bổ">${p.allocated_quantity}</td>
        <td data-label="Còn lại">${p.remaining_quantity}</td>
        <td data-label="Trạng thái">${statusBadge}</td>
        <td>${actionCell}</td>
      </tr>`;
    })
    .join("");
}

function refreshAvailablePlansView() {
  renderAvailablePlans(applyAvailablePlanFilters(currentAvailablePlans));
}

async function loadAvailablePlans() {
  const res = await fetch("/api/plans");
  const plans = await res.json();
  const eligible = (plans || []).filter((p) => p.status === "approved");
  currentAvailablePlans = eligible;
  fillFilterOptions(eligible);
  fillSalePlanOptions(eligible.filter((p) => p.remaining_quantity > 0));
  renderSupplyCards(eligible);
  refreshAvailablePlansView();
}

function pickPlan(planId) {
  const select = el("line-sale-plan");
  if (!select) return;
  if ([...select.options].some((o) => o.value === String(planId))) select.value = String(planId);
  updateRemainingHint();
  const form = el("line-section");
  if (form) form.scrollIntoView({ behavior: "smooth", block: "start" });
}

// Điểm tập trung duy nhất mỗi lần nguồn heo đang chọn đổi (đổi select hoặc
// bấm "Chọn nguồn này" trong bảng) — cập nhật banner "Đã chọn nguồn", vẽ lại
// bảng nguồn cung để tô đúng dòng đang chọn, và tính lại validation số lượng.
function updateRemainingHint() {
  const select = el("line-sale-plan");
  if (!select) return;
  const opt = select.options[select.selectedIndex];
  const plan = opt && opt.value ? currentAvailablePlans.find((p) => String(p.id) === opt.value) : null;
  const box = el("selected-source-box");
  if (box) {
    if (plan) {
      box.classList.remove("hidden");
      box.querySelector(".selected-source-code").textContent = plan.plan_code || "#" + plan.id;
      box.querySelector(".selected-source-detail").textContent =
        `${plan.farm}${plan.zone ? " · " + plan.zone : ""} — ${plan.pig_type_name || "—"}`;
      box.querySelector(".selected-source-remaining-value").textContent = plan.remaining_quantity;
    } else {
      box.classList.add("hidden");
    }
  }
  refreshAvailablePlansView();
  computeQuantityFeedback();
}

// Validation số lượng bán real-time — trừ luôn số lượng CÙNG kế hoạch trại
// đã có sẵn trong giỏ nháp, để không cho vượt remaining thực tế khi cộng dồn
// nhiều dòng cùng 1 nguồn trước khi tạo đơn.
function computeQuantityFeedback() {
  const feedback = el("line-quantity-feedback");
  const select = el("line-sale-plan");
  const qtyInput = el("line-quantity");
  if (!feedback || !select || !qtyInput) return { valid: false };
  const opt = select.options[select.selectedIndex];
  const plan = opt && opt.value ? currentAvailablePlans.find((p) => String(p.id) === opt.value) : null;
  const qtyRaw = qtyInput.value;
  const qty = Number(qtyRaw);

  feedback.className = "msg plan-form-feedback";
  if (!plan) {
    feedback.textContent = "";
    return { valid: false };
  }
  if (!qtyRaw) {
    feedback.textContent = `Còn lại: ${plan.remaining_quantity} con`;
    return { valid: false };
  }
  if (!Number.isFinite(qty) || qty <= 0) {
    feedback.className = "msg plan-form-feedback error";
    feedback.textContent = "⚠ Số lượng phải lớn hơn 0.";
    return { valid: false };
  }
  const reserved = draftLines
    .filter((l) => String(l.sale_plan_id) === String(plan.id))
    .reduce((sum, l) => sum + Number(l.quantity || 0), 0);
  const effectiveRemaining = plan.remaining_quantity - reserved;
  if (qty > effectiveRemaining) {
    feedback.className = "msg plan-form-feedback error";
    feedback.textContent = `⚠ Số lượng bán vượt số lượng còn lại. Chỉ còn ${effectiveRemaining} con.`;
    return { valid: false };
  }
  feedback.className = "msg plan-form-feedback success";
  feedback.textContent = `✓ Hợp lệ — sau khi bán còn ${effectiveRemaining - qty} con.`;
  return { valid: true };
}

// ---- Giỏ nháp (đơn hàng đang xây dựng) ----

function renderDraftCart() {
  const box = el("draft-cart-list");
  const btn = el("btn-create-order");
  const totalEl = el("draft-total");
  if (!box) return;
  if (!draftLines.length) {
    box.innerHTML = `<tr><td colspan="8"><strong>Chưa có sản phẩm trong đơn hàng</strong><br>Chọn nguồn heo và thêm số lượng để bắt đầu tạo đơn.</td></tr>`;
  } else {
    box.innerHTML = draftLines
      .map(
        (l, idx) => `<tr>
          <td data-label="#">${idx + 1}</td>
          <td data-label="Trại">${l._display.farm}${l._display.zone ? " · " + l._display.zone : ""}</td>
          <td data-label="Loại heo">${l._display.pig_type_name || "—"}</td>
          <td data-label="Kế hoạch">${l._display.plan_code || "—"}</td>
          <td data-label="Số lượng">${l.quantity} con</td>
          <td data-label="Giá">${fmtPrice(l.selling_price)} đ/kg</td>
          <td class="detail-cell" data-label="Ghi chú">${l.note || ""}</td>
          <td><button type="button" class="btn btn-danger btn-sm btn-remove-draft-line" data-index="${idx}">Xoá</button></td>
        </tr>`
      )
      .join("");
  }
  if (totalEl) {
    const totalQty = draftLines.reduce((sum, l) => sum + Number(l.quantity || 0), 0);
    totalEl.textContent = draftLines.length ? `Tổng số lượng: ${totalQty} con` : "";
  }
  if (btn) btn.disabled = draftLines.length === 0;
}

function removeDraftLine(index) {
  draftLines.splice(Number(index), 1);
  renderDraftCart();
}

async function createOrderFromDraft() {
  const msg = el("draft-msg");
  msg.className = "msg";
  msg.textContent = "Đang tạo đơn...";
  const body = {
    lines: draftLines.map((l) => ({
      sale_plan_id: l.sale_plan_id,
      quantity: l.quantity,
      selling_price: l.selling_price,
      note: l.note,
    })),
  };
  try {
    const res = await fetch("/api/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await res.json();
    if (!res.ok) {
      msg.className = "msg error";
      msg.textContent = payload.error || "Lỗi khi tạo đơn hàng.";
      return;
    }
    msg.innerHTML = `Đã tạo đơn hàng ${payload.order_code || "#" + payload.id}. <a href="/chot-ban?highlight=${payload.id}">Sang Chốt bán để xử lý tiếp →</a>`;
    draftLines = [];
    renderDraftCart();
    await loadAvailablePlans();
  } catch (err) {
    msg.className = "msg error";
    msg.textContent = "Lỗi khi lưu: " + err;
  }
}

// ---- Form "Thêm dòng heo" — 2 chế độ: thêm vào giỏ nháp, hoặc thêm thẳng
// vào 1 đơn đang có sẵn (targetOrderId, đến từ trang Chốt bán) ----

function startAddLineToOrder(orderId, orderCode) {
  targetOrderId = orderId;
  el("line-submit-btn").textContent = "+ Thêm vào đơn";
  const notice = el("line-target-notice");
  notice.textContent = `Đang thêm dòng vào đơn ${orderCode || "#" + orderId}`;
  notice.classList.remove("hidden");
  el("line-cancel-target").classList.remove("hidden");
  const section = el("line-section");
  if (section) section.scrollIntoView({ behavior: "smooth", block: "start" });
}

function cancelAddLineTarget() {
  targetOrderId = null;
  el("line-form").reset();
  el("line-submit-btn").textContent = "+ Thêm vào đơn";
  el("line-target-notice").classList.add("hidden");
  el("line-cancel-target").classList.add("hidden");
  el("line-msg").className = "msg";
  el("line-msg").textContent = "";
  updateRemainingHint();
}

async function handleLineFormSubmit(e) {
  e.preventDefault();
  const msg = el("line-msg");
  msg.className = "msg";
  const planId = el("line-sale-plan").value;
  const plan = currentAvailablePlans.find((p) => String(p.id) === String(planId));
  const priceValue = parsePriceInputValue(el("line-selling-price").value);

  if (plan) {
    const feedback = computeQuantityFeedback();
    if (!feedback.valid) {
      msg.className = "msg error";
      msg.textContent = "Vui lòng nhập số lượng hợp lệ — xem gợi ý phía trên nút Thêm vào đơn.";
      return;
    }
  }
  if (!priceValue || priceValue <= 0) {
    msg.className = "msg error";
    msg.textContent = "Giá chào bán phải lớn hơn 0.";
    return;
  }

  const line = {
    sale_plan_id: planId,
    quantity: el("line-quantity").value,
    selling_price: priceValue,
    note: el("line-note").value,
  };

  if (targetOrderId) {
    msg.textContent = "Đang lưu...";
    try {
      const res = await fetch(`/api/orders/${targetOrderId}/lines`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(line),
      });
      const payload = await res.json();
      if (!res.ok) {
        msg.className = "msg error";
        msg.textContent = payload.error || "Lỗi khi thêm dòng.";
        return;
      }
      const orderId = targetOrderId;
      cancelAddLineTarget();
      await loadAvailablePlans();
      msg.innerHTML = `Đã thêm dòng. <a href="/chot-ban?highlight=${orderId}">Quay lại Chốt bán →</a>`;
    } catch (err) {
      msg.className = "msg error";
      msg.textContent = "Lỗi khi lưu: " + err;
    }
    return;
  }

  if (!plan) {
    msg.className = "msg error";
    msg.textContent = "Vui lòng chọn nguồn heo hợp lệ.";
    return;
  }
  draftLines.push({
    ...line,
    _display: { farm: plan.farm, zone: plan.zone, pig_type_name: plan.pig_type_name, plan_code: plan.plan_code },
  });
  renderDraftCart();
  el("line-form").reset();
  updateRemainingHint();
  msg.textContent = "Đã thêm vào giỏ nháp.";
}

// ---- Click delegation ----

function handleAvailablePlansClick(e) {
  const pickBtn = e.target.closest(".btn-pick-plan");
  if (pickBtn) pickPlan(pickBtn.dataset.id);
}

function handleDraftCartClick(e) {
  const removeBtn = e.target.closest(".btn-remove-draft-line");
  if (removeBtn) removeDraftLine(removeBtn.dataset.index);
}

if (el("line-form")) el("line-form").addEventListener("submit", handleLineFormSubmit);
if (el("line-cancel-target")) el("line-cancel-target").addEventListener("click", cancelAddLineTarget);
if (el("line-sale-plan")) el("line-sale-plan").addEventListener("change", updateRemainingHint);
if (el("line-quantity")) el("line-quantity").addEventListener("input", computeQuantityFeedback);
if (el("line-selling-price")) {
  el("line-selling-price").addEventListener("input", (e) => {
    const input = e.target;
    const digitsBeforeCursor = input.value.slice(0, input.selectionStart).replace(/\D/g, "").length;
    input.value = formatPriceInputValue(input.value);
    // Đặt lại con trỏ theo số chữ số đã gõ trước đó (không tính dấu chấm ngăn
    // cách vừa chèn thêm), để gõ tiếp không bị nhảy vị trí.
    let pos = 0;
    let digitsSeen = 0;
    while (pos < input.value.length && digitsSeen < digitsBeforeCursor) {
      if (/\d/.test(input.value[pos])) digitsSeen++;
      pos++;
    }
    input.setSelectionRange(pos, pos);
  });
}
if (el("btn-create-order")) el("btn-create-order").addEventListener("click", createOrderFromDraft);
if (el("draft-cart-list")) el("draft-cart-list").addEventListener("click", handleDraftCartClick);
if (el("available-plans-list")) el("available-plans-list").addEventListener("click", handleAvailablePlansClick);

["filter-farm", "filter-pig-type", "filter-date-from", "filter-date-to", "filter-status"].forEach((id) => {
  if (el(id)) el(id).addEventListener("change", refreshAvailablePlansView);
});
if (el("filter-search")) el("filter-search").addEventListener("input", refreshAvailablePlansView);

// Đến từ nút "➕ Thêm dòng" của 1 đơn ở trang Chốt bán (?target_order=<id>).
function targetOrderFromQuery() {
  const params = new URLSearchParams(location.search);
  const id = params.get("target_order");
  if (!id) return;
  startAddLineToOrder(id, params.get("target_order_code"));
}

if (el("available-plans-list")) {
  (async function initChaoHang() {
    renderDraftCart();
    await loadAvailablePlans();
    targetOrderFromQuery();
  })();
}
