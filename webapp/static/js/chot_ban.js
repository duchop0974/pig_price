// Trang "Chốt bán" (Phase 4, brief nghiệp vụ — tách từ allocations.html/
// allocation.js cũ): quản lý đơn hàng ĐÃ TỒN TẠI — chốt thông tin bán hàng,
// đánh dấu Đã bán, ghi nhận doanh thu, xuất giao/heo loại-hủy theo dòng.
// KHÔNG còn "Nguồn cung có thể bán"/giỏ nháp/tạo đơn mới ở đây — đó là
// trang "Chào hàng" (chao_hang.js); nút "➕ Thêm dòng" điều hướng sang đó.
const CAN_CREATE_ALLOCATION = (window.CURRENT_USER_PERMISSIONS || []).includes("plans.allocation_create");
const CAN_MANAGE_ALLOCATIONS = (window.CURRENT_USER_PERMISSIONS || []).includes("plans.allocation_manage");
const CAN_ALLOC_SALE_DETAILS = (window.CURRENT_USER_PERMISSIONS || []).includes("plans.sale_details");
const CAN_ALLOC_REVENUE_DETAILS = (window.CURRENT_USER_PERMISSIONS || []).includes("plans.revenue_details");
// Xoá vĩnh viễn đơn hàng / sửa dòng hàng bất kể trạng thái — mặc định chỉ
// admin có 2 quyền này (Giai đoạn 9), khớp plans.order_delete/plans.order_edit_line ở server.
const CAN_DELETE_ORDERS = (window.CURRENT_USER_PERMISSIONS || []).includes("plans.order_delete");
const CAN_EDIT_ORDER_LINE = (window.CURRENT_USER_PERMISSIONS || []).includes("plans.order_edit_line");
// Khoá vĩnh viễn đơn hàng (Data Freeze) — mặc định chỉ admin có, khớp
// plans.order_lock ở server.
const CAN_LOCK_ORDER = (window.CURRENT_USER_PERMISSIONS || []).includes("plans.order_lock");
// Ghi nhận / xoá lần xuất giao thực tế (sale_deliveries) — khớp
// plans.delivery_create/plans.delivery_delete ở server.
const CAN_RECORD_DELIVERY = (window.CURRENT_USER_PERMISSIONS || []).includes("plans.delivery_create");
const CAN_DELETE_DELIVERY = (window.CURRENT_USER_PERMISSIONS || []).includes("plans.delivery_delete");

const ALLOC_PAYMENT_METHOD_LABEL = {
  bank_transfer_immediate: "Chuyển khoản ngay",
  bank_transfer_24h: "Chuyển khoản trước 24h",
  cash: "Tiền mặt",
  credit: "Công nợ",
  other: "Khác",
};

let currentOrders = [];

// ---- Đơn hàng ----

function orderStatusBadge(o) {
  if (o.status === "done") return renderBadge("done");
  if (o.status === "cancelled") return renderBadge("cancelled");
  if (o.status === "disabled") return renderBadge("disabled");
  return renderBadge("active");
}

// Mini workflow stepper cho vòng đời đơn hàng: Đang xử lý → Chốt bán hàng →
// Đã bán → Doanh thu ghi nhận. Chốt bán hàng và Đã bán có thể xảy ra không
// theo đúng thứ tự này ở thực tế (backend không ép buộc) nên mỗi bước tự
// tính "done" theo dữ liệu riêng của nó, chỉ bước đầu tiên chưa xong được
// đánh dấu is-current — tránh hiển thị sai khi thứ tự thực tế bị đảo.
// disabled/cancelled → is-exception ngay tại bước đầu tiên còn dang dở.
const ORDER_STEPPER_STATE_CLASS = { done: "is-done", current: "is-current", pending: "", exception: "is-exception", locked: "is-locked" };
const ORDER_STEPPER_MARKER = { done: "✓", current: "●", pending: "○", exception: "!", locked: "🔒" };

function orderStepperHtml(order) {
  const labels = ["Đang xử lý", "Chốt bán hàng", "Đã bán", "Doanh thu ghi nhận"];
  const flags = [
    true,
    !!(order.customer_name || order.confirmed_sale_at || order.payment_method || order.delivery_time),
    order.status === "done",
    !!(order.paid_amount || order.invoice_number),
  ];
  let states;
  if (order.status === "cancelled" || order.status === "disabled") {
    const firstFalse = flags.findIndex((f) => !f);
    const cut = firstFalse === -1 ? flags.length - 1 : firstFalse;
    states = labels.map((_, i) => (i < cut ? "done" : i === cut ? "exception" : "locked"));
  } else {
    let currentSet = false;
    states = flags.map((f) => {
      if (f) return "done";
      if (!currentSet) {
        currentSet = true;
        return "current";
      }
      return "pending";
    });
  }
  return `<div class="stepper">${labels
    .map((label, i) => {
      const s = states[i];
      const connector = i < labels.length - 1 ? `<span class="stepper-connector"></span>` : "";
      return `<span class="stepper-step ${ORDER_STEPPER_STATE_CLASS[s]}"><span class="stepper-step-marker">${ORDER_STEPPER_MARKER[s]}</span><span class="stepper-step-label">${label}</span></span>${connector}`;
    })
    .join("")}</div>`;
}

function incidentItemHtml(inc) {
  const kindLabel = inc.kind === "culled" ? "Loại" : "Hủy";
  const photos = (inc.media || []).map((m) => `<img src="/media/${m.id}" alt="" class="incident-photo">`).join("");
  return `<div class="plan-note">
    <strong>${kindLabel} ${inc.quantity} con</strong> — ${inc.description}
    ${photos ? `<div class="incident-photos">${photos}</div>` : ""}
  </div>`;
}

// Khối "Heo loại/hủy" trên 1 dòng hàng — đối chiếu kế hoạch − Σloại − Σhủy,
// KHÔNG đụng tới line.actual_quantity (giữ độc lập, chỉ đối chiếu trực quan).
function incidentSectionHtml(order, line) {
  const lineIncidents = (order.incidents || []).filter((inc) => inc.allocation_id === line.id);
  const culledQty = lineIncidents.filter((i) => i.kind === "culled").reduce((sum, i) => sum + i.quantity, 0);
  const cancelledQty = lineIncidents.filter((i) => i.kind === "cancelled").reduce((sum, i) => sum + i.quantity, 0);
  const reconciled = line.quantity - culledQty - cancelledQty;
  const canAdd = order.status === "active" && CAN_CREATE_ALLOCATION;
  if (!lineIncidents.length && !canAdd) return "";
  return `<div class="plan-card-section">
    <div class="plan-card-section-label">Heo loại/hủy</div>
    <div class="plan-meta-grid">
      <div class="plan-row"><span>Kế hoạch</span><strong>${line.quantity} con</strong></div>
      ${culledQty ? `<div class="plan-row"><span>Loại</span><strong class="plan-down">-${culledQty} con</strong></div>` : ""}
      ${cancelledQty ? `<div class="plan-row"><span>Hủy</span><strong class="plan-down">-${cancelledQty} con</strong></div>` : ""}
      ${culledQty || cancelledQty ? `<div class="plan-row"><span>Đối chiếu còn lại</span><strong>${reconciled} con</strong></div>` : ""}
    </div>
    ${lineIncidents.map(incidentItemHtml).join("")}
    ${canAdd ? `<button type="button" class="btn btn-ghost btn-sm btn-add-incident" data-order-id="${order.id}" data-line-id="${line.id}">🐖 Ghi nhận Loại/Hủy</button>` : ""}
  </div>`;
}

function deliveryItemHtml(d) {
  const weightHtml = d.total_weight_kg !== null && d.total_weight_kg !== undefined ? ` · ${fmtWeight(d.total_weight_kg)} kg` : "";
  const priceHtml = d.unit_price !== null && d.unit_price !== undefined ? ` · ${fmtPrice(d.unit_price)} đ/kg` : "";
  // Bản ghi đã khoá (Data Freeze) thì không cho xoá — nút "Ghi nhận xuất
  // giao" (thêm mới) đã tự ẩn theo order.locked_at ở deliverySectionHtml,
  // nút xoá TỪNG DÒNG phải tự kiểm d.locked_at riêng (server đã chặn, đây là
  // lớp UX tương ứng, tránh hiện nút chỉ để bấm ra lỗi 400).
  const deleteHtml =
    CAN_DELETE_DELIVERY && !d.locked_at
      ? `<button type="button" class="btn btn-ghost btn-sm btn-delete-delivery" data-id="${d.id}">🗑️</button>`
      : "";
  return `<div class="plan-note">
    <strong>${d.pig_type_name || "—"} · ${d.quantity} con</strong>${weightHtml}${priceHtml}
    <div class="plan-note">${fmtIsoDate(d.delivered_date)}${d.created_by ? " · " + d.created_by : ""}${d.weighing_ref ? " · Phiếu cân " + d.weighing_ref : ""}</div>
    ${d.note ? `<div class="plan-note">${d.note}</div>` : ""}
    ${deleteHtml}
  </div>`;
}

// Khối "Xuất giao thực tế" trên 1 dòng hàng — lịch sử các lần xuất (có thể
// KHÁC loại heo kế hoạch, xem sale_deliveries). Rộng hơn điều kiện hiện nút
// "🐖 Ghi nhận Loại/Hủy" (chỉ status active): xuất nhiều lần vẫn hợp lệ cả
// khi đơn đã "Đã bán" (status done), chỉ chặn khi đã khoá (Data Freeze)/huỷ.
function deliverySectionHtml(order, line) {
  const lineDeliveries = (order.deliveries || []).filter((d) => d.allocation_id === line.id);
  const canAdd = !order.locked_at && order.status !== "cancelled" && order.status !== "disabled" && CAN_RECORD_DELIVERY;
  if (!lineDeliveries.length && !canAdd) return "";
  return `<div class="plan-card-section">
    <div class="plan-card-section-label">Xuất giao thực tế</div>
    ${lineDeliveries.map(deliveryItemHtml).join("")}
    ${canAdd ? `<button type="button" class="btn btn-ghost btn-sm btn-add-delivery" data-order-id="${order.id}" data-line-id="${line.id}">🚚 Ghi nhận xuất giao</button>` : ""}
  </div>`;
}

function lineHtml(order, line) {
  const hasCur = line.current_price !== null && line.current_price !== undefined;
  const scopeLabel = line.current_price_is_national
    ? "cả nước — trại chưa gán tỉnh hoặc tỉnh chưa có dữ liệu"
    : `tỉnh ${line.province}`;
  const curHtml = hasCur
    ? `${fmtPrice(line.current_price)}<span class="unit"> đ/kg</span> (${scopeLabel}, ngày ${line.current_price_date})`
    : "Chưa có dữ liệu";
  const diff = hasCur && line.selling_price ? line.current_price - line.selling_price : null;
  const diffHtml =
    diff === null
      ? ""
      : `<div class="plan-row"><span>Chênh lệch</span><strong class="${diff >= 0 ? "plan-up" : "plan-down"}">${diff >= 0 ? "+" : ""}${fmtPrice(diff)} đ/kg</strong></div>`;
  const reachedHtml = line.reached_target ? `<span class="badge badge-success">🔔 Đã đạt giá mong muốn</span>` : "";
  const actualHtml =
    order.status === "done" && line.actual_price !== null && line.actual_price !== undefined
      ? `<div class="plan-row"><span>Giá bán thực tế</span><strong>${fmtPrice(line.actual_price)} đ/kg</strong></div>
         <div class="plan-row"><span>Số lượng đã bán</span><strong>${line.actual_quantity} con</strong></div>`
      : "";
  const canRemove = order.status === "active" && CAN_CREATE_ALLOCATION && order.lines.length > 1;
  let lineActions = "";
  if (canRemove) {
    lineActions += `<button type="button" class="btn btn-danger btn-remove-line" data-order-id="${order.id}" data-line-id="${line.id}">🗑️ Xoá dòng</button>`;
  }
  if (CAN_EDIT_ORDER_LINE) {
    lineActions += `<button type="button" class="btn btn-ghost btn-edit-line" data-order-id="${order.id}" data-line-id="${line.id}">✏️ Sửa dòng</button>`;
  }
  return `<article class="plan-card">
    <div class="plan-card-head">
      <strong>${line.farm}${line.zone ? " · " + line.zone : ""} · ${line.pig_type_name || "—"}</strong>
      ${reachedHtml}
    </div>
    ${line.plan_code ? `<div class="plan-code">${line.plan_code}</div>` : ""}
    <div class="plan-meta-grid">
      ${line.sale_plan_code ? `<div class="plan-row"><span>Từ kế hoạch trại</span><strong>${line.sale_plan_code}</strong></div>` : ""}
      <div class="plan-row"><span>Ngày dự kiến</span><strong>${fmtIsoDate(line.planned_date)}</strong></div>
      <div class="plan-row"><span>Số lượng</span><strong>${line.quantity} con</strong></div>
      <div class="plan-row"><span>Giá chào bán</span><strong>${line.selling_price ? fmtPrice(line.selling_price) + " đ/kg" : "—"}</strong></div>
      <div class="plan-row"><span>Giá hiện tại</span><strong>${curHtml}</strong></div>
      ${diffHtml}
      ${actualHtml}
    </div>
    ${line.note ? `<div class="plan-note">${line.note}</div>` : ""}
    ${deliverySectionHtml(order, line)}
    ${incidentSectionHtml(order, line)}
    ${lineActions ? `<div class="plan-actions">${lineActions}</div>` : ""}
  </article>`;
}

// Ứng viên action cho 1 đơn hàng — tái tạo đúng 9 điều kiện if-chain gốc
// của renderOrders() cũ, giữ nguyên permission gate + status condition cho
// từng nút, chỉ đổi cách gom lại thành mảng thay vì nối chuỗi HTML trực tiếp.
function orderCandidateActions(o) {
  const items = [];
  if (o.status === "active" && CAN_CREATE_ALLOCATION) items.push({ label: "➕ Thêm dòng", cls: "order-btn-add-line" });
  if (CAN_MANAGE_ALLOCATIONS && o.status === "active") items.push({ label: "✅ Đã bán", cls: "order-btn-done" });
  if (o.status === "active" && CAN_ALLOC_SALE_DETAILS) items.push({ label: "🤝 Chốt bán hàng", cls: "order-btn-sale-details" });
  if (o.status === "active" && CAN_ALLOC_SALE_DETAILS) items.push({ label: "⬇️ Xuất chào hàng", cls: "order-btn-quotation" });
  if (o.status === "done" && CAN_ALLOC_REVENUE_DETAILS) items.push({ label: "💰 Ghi nhận doanh thu", cls: "order-btn-revenue" });
  if (CAN_MANAGE_ALLOCATIONS && o.status === "active") items.push({ label: "🚫 Vô hiệu hoá", cls: "order-btn-disable", danger: true });
  if (CAN_MANAGE_ALLOCATIONS && o.status === "disabled") items.push({ label: "▶️ Kích hoạt lại", cls: "order-btn-enable" });
  if (o.status === "done" && !o.locked_at && CAN_LOCK_ORDER) items.push({ label: "🔒 Khoá đơn hàng", cls: "order-btn-lock" });
  if (CAN_DELETE_ORDERS && !o.locked_at) items.push({ label: "🗑️ Xoá đơn", cls: "order-btn-delete", danger: true });
  return items;
}

// 1 primary action/hàng — khuôn planPrimaryAction (plan.js), theo đúng thứ
// tự ưu tiên khớp 4 bước của orderStepperHtml. "🔒 Khoá đơn hàng" KHÔNG nằm
// trong bất kỳ nhánh nào ở đây → không bao giờ là primary, luôn rơi xuống
// menu — đúng vì đây là hành động admin-only/hiếm dùng.
function orderPrimaryAction(o) {
  const hasSaleDetails = !!(o.customer_name || o.confirmed_sale_at || o.payment_method || o.delivery_time);
  if (o.status === "active" && !hasSaleDetails && CAN_ALLOC_SALE_DETAILS) {
    return { label: "🤝 Chốt bán hàng", cls: "order-btn-sale-details" };
  }
  if (o.status === "active" && hasSaleDetails && CAN_MANAGE_ALLOCATIONS) {
    return { label: "✅ Đã bán", cls: "order-btn-done" };
  }
  if (o.status === "done" && !o.paid_amount && !o.invoice_number && CAN_ALLOC_REVENUE_DETAILS) {
    return { label: "💰 Ghi nhận doanh thu", cls: "order-btn-revenue" };
  }
  if (o.status === "disabled" && CAN_MANAGE_ALLOCATIONS) {
    return { label: "▶️ Kích hoạt lại", cls: "order-btn-enable" };
  }
  return null;
}

// Phần còn lại (không trùng primary) — vào action bar của modal chi tiết.
function orderMenuActions(o) {
  const primary = orderPrimaryAction(o);
  return orderCandidateActions(o).filter((it) => !primary || it.cls !== primary.cls);
}

function applyOrderFilters(orders) {
  const status = el("order-filter-status").value;
  const q = el("order-filter-search").value.trim().toLowerCase();
  return orders.filter((o) => {
    if (status && o.status !== status) return false;
    if (q) {
      const lineHay = (o.lines || []).map((l) => `${l.farm || ""} ${l.pig_type_name || ""} ${l.plan_code || ""}`).join(" ");
      const hay = `${o.order_code || ""} ${o.customer_name || ""} ${lineHay}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

function orderRowHtml(o) {
  const primary = orderPrimaryAction(o);
  const primaryHtml = primary
    ? `<button type="button" class="btn btn-primary btn-sm ${primary.cls}" data-id="${o.id}">${primary.label}</button>`
    : "";
  const totalQty = o.lines.reduce((sum, l) => sum + (l.quantity || 0), 0);
  const rowCls = o.status === "disabled" ? "plan-card-disabled" : "";
  return `<tr class="${rowCls}" data-id="${o.id}">
    <td data-label="Mã đơn hàng">${o.order_code || "#" + o.id}</td>
    <td data-label="Trạng thái">${orderStatusBadge(o)}${o.locked_at ? " 🔒" : ""}</td>
    <td data-label="Khách hàng">${o.customer_name || "—"}</td>
    <td data-label="Dòng hàng">${o.lines.length} dòng · ${totalQty} con</td>
    <td class="admin-table-actions">
      ${primaryHtml}
      <button type="button" class="btn btn-ghost btn-sm order-btn-detail" data-id="${o.id}">Chi tiết</button>
    </td>
  </tr>`;
}

function renderOrdersTable(orders) {
  const tbody = el("order-list");
  const emptyMsg = el("order-list-empty");
  if (!tbody) return;
  if (!orders.length) {
    tbody.innerHTML = "";
    if (emptyMsg) emptyMsg.classList.remove("hidden");
    return;
  }
  if (emptyMsg) emptyMsg.classList.add("hidden");
  tbody.innerHTML = orders.map(orderRowHtml).join("");
}

function refreshOrdersView() {
  renderOrdersTable(applyOrderFilters(currentOrders));
}

// Body modal chi tiết — tái dùng nguyên orderStepperHtml/lineHtml (kèm
// deliverySectionHtml/incidentSectionHtml bên trong nó); saleDetailsHtml/
// revenueDetailsHtml/lockedBannerHtml là copy nguyên văn phần tương ứng của
// renderOrders() cũ. Bọc trong <div class="order-card"> — bắt buộc:
// handleOrderListClick's linesToggleBtn.closest(".order-card") cần 1 tổ
// tiên chung giữa nút toggle và .order-lines.
function orderDetailBodyHtml(o) {
  const totalQty = o.lines.reduce((sum, l) => sum + (l.quantity || 0), 0);
  const lockedBannerHtml = o.locked_at
    ? `<div class="locked-banner">
         <div>🔒 DỮ LIỆU ĐÃ KHÓA</div>
         <div class="locked-banner-meta">Dữ liệu đã được chốt lúc ${o.locked_at}${o.locked_by ? " bởi " + o.locked_by : ""}. Dữ liệu không thể chỉnh sửa trực tiếp. Nếu phát hiện sai, ghi nhận qua "Heo loại/hủy".</div>
       </div>`
    : "";
  const saleDetailsHtml =
    o.customer_name || o.contact_note || o.confirmed_sale_at || o.delivery_time || o.payment_method
      ? `<div class="plan-card-section">
           <div class="plan-card-section-label">Thông tin bán hàng</div>
           <div class="plan-meta-grid">
             ${o.customer_name ? `<div class="plan-row"><span>Khách hàng</span><strong>${o.customer_name}${o.customer_phone ? " · " + o.customer_phone : ""}</strong></div>` : ""}
             ${o.confirmed_sale_at ? `<div class="plan-row"><span>Ngày chốt bán</span><strong>${fmtIsoDate(o.confirmed_sale_at)}</strong></div>` : ""}
             ${o.delivery_time ? `<div class="plan-row"><span>Khung giờ giao</span><strong>${o.delivery_time}</strong></div>` : ""}
             ${o.payment_method ? `<div class="plan-row"><span>Thanh toán</span><strong>${ALLOC_PAYMENT_METHOD_LABEL[o.payment_method] || o.payment_method}</strong></div>` : ""}
           </div>
           ${o.contact_note ? `<div class="plan-note">Liên hệ (${o.contacted_by || "—"}): ${o.contact_note}</div>` : ""}
         </div>`
      : "";
  const revenueDetailsHtml =
    o.paid_amount || o.weighing_ref || o.invoice_number
      ? `<div class="plan-card-section">
           <div class="plan-card-section-label">Doanh thu / hoá đơn</div>
           <div class="plan-meta-grid">
             ${o.paid_amount ? `<div class="plan-row"><span>Đã thu tiền</span><strong>${fmtPrice(o.paid_amount)} đ${o.paid_at ? " · " + fmtIsoDate(o.paid_at.slice(0, 10)) : ""}</strong></div>` : ""}
             ${o.weighing_ref ? `<div class="plan-row"><span>Chứng từ cân</span><strong>${o.weighing_ref}</strong></div>` : ""}
             ${o.invoice_number ? `<div class="plan-row"><span>Số hoá đơn</span><strong>${o.invoice_number}${o.invoiced_by ? " · " + o.invoiced_by : ""}</strong></div>` : ""}
           </div>
         </div>`
      : "";

  return `<div class="order-card">
    <div class="plan-card-head">
      <strong>${o.order_code || "#" + o.id}</strong>
      ${orderStatusBadge(o)}
    </div>
    ${orderStepperHtml(o)}
    ${lockedBannerHtml}
    ${saleDetailsHtml}
    ${revenueDetailsHtml}
    <button type="button" class="btn btn-ghost order-lines-toggle" data-id="${o.id}">
      <span>📋 ${o.lines.length} dòng · ${totalQty} con</span><span class="toggle-caret">▾</span>
    </button>
    <div class="order-lines is-collapsed">${o.lines.map((line) => lineHtml(o, line)).join("")}</div>
  </div>`;
}

function orderDetailActionsHtml(o) {
  const primary = orderPrimaryAction(o);
  const menu = orderMenuActions(o);
  const all = [...(primary ? [primary] : []), ...menu];
  if (!all.length) return "";
  return all
    .map((it) => {
      const cls = it.danger ? "btn-danger" : primary && it.cls === primary.cls ? "btn-primary" : "btn-ghost";
      return `<button type="button" class="btn ${cls} ${it.cls}" data-id="${o.id}">${it.label}</button>`;
    })
    .join("");
}

function openOrderDetailModal(orderId) {
  const o = currentOrders.find((x) => String(x.id) === String(orderId));
  if (!o) return;
  detailModal({
    title: o.order_code || "#" + o.id,
    bodyHtml: orderDetailBodyHtml(o),
    actionsHtml: orderDetailActionsHtml(o),
  });
}

async function loadOrders() {
  const box = el("order-list");
  if (!box) return;
  const res = await fetch("/api/orders");
  const orders = await res.json();
  // Nạp kèm incident (heo loại/hủy) của từng đơn — song song, không chặn
  // nhau — để render breakdown ngay trong lineHtml() mà không cần request
  // riêng lẻ khi mở từng đơn.
  await Promise.all(
    orders.map(async (o) => {
      try {
        const r = await fetch(`/api/orders/${o.id}/incidents`);
        o.incidents = r.ok ? await r.json() : [];
      } catch (err) {
        o.incidents = [];
      }
      try {
        const r = await fetch(`/api/orders/${o.id}/deliveries`);
        o.deliveries = r.ok ? await r.json() : [];
      } catch (err) {
        o.deliveries = [];
      }
    })
  );
  currentOrders = orders;
  refreshOrdersView();
}

async function setOrderStatus(orderId, status) {
  const res = await fetch(`/api/orders/${orderId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    showToast(payload.error || "Lỗi khi cập nhật đơn hàng.", "danger");
    return;
  }
  await loadOrders();
}

async function lockOrder(orderId, orderCode) {
  const ok = await confirmModal({
    title: "Khoá dữ liệu đơn hàng",
    body: `Đơn hàng ${orderCode || "#" + orderId} sẽ bị khoá vĩnh viễn.`,
    consequence:
      "Sau khi khoá, dữ liệu không thể chỉnh sửa trực tiếp. Nếu phát hiện sai, ghi nhận qua \"Heo loại/hủy\" cho dòng liên quan thay vì sửa trực tiếp.",
    confirmLabel: "Khoá dữ liệu",
  });
  if (!ok) return;
  const res = await fetch(`/api/orders/${orderId}/lock`, { method: "PATCH" });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    showToast(payload.error || "Lỗi khi khoá đơn hàng.", "danger");
    return;
  }
  await loadOrders();
}

async function removeOrderLine(orderId, lineId) {
  const ok = await confirmModal({ title: "Xoá dòng hàng", body: "Xoá dòng này khỏi đơn hàng?", confirmLabel: "Xoá" });
  if (!ok) return;
  const res = await fetch(`/api/orders/${orderId}/lines/${lineId}`, { method: "DELETE" });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    showToast(payload.error || "Lỗi khi xoá dòng.", "danger");
    return;
  }
  await loadOrders();
}

async function deleteOrder(orderId) {
  const ok = await confirmModal({
    title: "Xoá đơn hàng",
    body: "Xoá vĩnh viễn đơn hàng này?",
    consequence: "Kèm toàn bộ dòng hàng, không thể hoàn tác.",
    confirmLabel: "Xoá vĩnh viễn",
  });
  if (!ok) return;
  const res = await fetch(`/api/orders/${orderId}`, { method: "DELETE" });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    showToast(payload.error || "Lỗi khi xoá đơn hàng.", "danger");
    return;
  }
  await loadOrders();
}

async function editLine(orderId, lineId) {
  const order = currentOrders.find((o) => String(o.id) === String(orderId));
  const line = order && order.lines.find((l) => String(l.id) === String(lineId));
  if (!line) return;
  const quantity = await promptModal({ title: "Sửa dòng hàng", label: "Số lượng (con)", inputType: "number", initialValue: line.quantity });
  if (quantity === null) return;
  const sellingPrice = await promptModal({ title: "Sửa dòng hàng", label: "Giá chào bán (đ/kg)", inputType: "number", initialValue: line.selling_price });
  if (sellingPrice === null) return;
  const note = await promptModal({ title: "Sửa dòng hàng", label: "Ghi chú", initialValue: line.note || "" });
  if (note === null) return;
  const res = await fetch(`/api/orders/${orderId}/lines/${lineId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ quantity, selling_price: sellingPrice, note }),
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    showToast(payload.error || "Lỗi khi sửa dòng hàng.", "danger");
    return;
  }
  await loadOrders();
}

// ---- Modal Đánh dấu Đã bán (nhiều dòng) ----

let markDoneOrderId = null;

function openMarkDoneModal(orderId) {
  const order = currentOrders.find((o) => String(o.id) === String(orderId));
  if (!order) return;
  markDoneOrderId = orderId;
  el("md-lines").innerHTML = order.lines
    .map(
      (line) => `<div class="control-row">
        <label>${line.pig_type_name || "—"} (${line.plan_code || "#" + line.id})</label>
      </div>
      <div class="control-row">
        <label for="md-price-${line.id}">Giá bán thực tế (đ/kg)</label>
        <input type="number" id="md-price-${line.id}" min="0" step="1000" value="${line.selling_price || ""}">
      </div>
      <div class="control-row">
        <label for="md-qty-${line.id}">Số lượng bán thực tế (con)</label>
        <input type="number" id="md-qty-${line.id}" min="1" step="1" value="${line.quantity || ""}">
      </div>`
    )
    .join("");
  el("md-msg").className = "msg";
  el("md-msg").textContent = "";
  el("mark-done-modal").classList.remove("hidden");
}

function closeMarkDoneModal() {
  markDoneOrderId = null;
  el("mark-done-modal").classList.add("hidden");
}

async function saveMarkDone() {
  const order = currentOrders.find((o) => String(o.id) === String(markDoneOrderId));
  if (!order) return;
  const lines = order.lines.map((line) => ({
    allocation_id: line.id,
    actual_price: el(`md-price-${line.id}`).value,
    actual_quantity: el(`md-qty-${line.id}`).value,
  }));
  const res = await fetch(`/api/orders/${markDoneOrderId}/mark-done`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lines }),
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    el("md-msg").className = "msg error";
    el("md-msg").textContent = payload.error || "Lỗi khi đánh dấu Đã bán.";
    return;
  }
  closeMarkDoneModal();
  await loadOrders();
}

// ---- Modal Chốt bán hàng ----

let saleDetailsOrderId = null;

async function openSaleDetailsModal(orderId, order) {
  saleDetailsOrderId = orderId;
  const res = await fetch("/api/customers?active_only=true");
  const customers = await res.json();
  const select = el("sd-customer");
  select.innerHTML =
    `<option value="">-- Chưa chọn --</option>` +
    customers
      .map(
        (c) =>
          `<option value="${c.id}" ${order.customer_id === c.id ? "selected" : ""}>${c.name}${c.phone ? " · " + c.phone : ""}</option>`
      )
      .join("");
  el("sd-contact-note").value = "";
  el("sd-confirmed-date").value = order.confirmed_sale_at || "";
  el("sd-delivery-time").value = order.delivery_time || "";
  el("sd-payment-method").value = order.payment_method || "";
  el("sd-msg").className = "msg";
  el("sd-msg").textContent = "";
  el("sale-details-modal").classList.remove("hidden");
}

function closeSaleDetailsModal() {
  saleDetailsOrderId = null;
  el("sale-details-modal").classList.add("hidden");
}

async function saveSaleDetails() {
  const body = {
    customer_id: el("sd-customer").value || null,
    contact_note: el("sd-contact-note").value,
    confirmed_sale_at: el("sd-confirmed-date").value || null,
    delivery_time: el("sd-delivery-time").value,
    payment_method: el("sd-payment-method").value || null,
  };
  const res = await fetch(`/api/orders/${saleDetailsOrderId}/sale-details`, {
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
  await loadOrders();
}

// ---- Modal Ghi nhận doanh thu ----

let revenueOrderId = null;

async function openRevenueModal(orderId, order) {
  revenueOrderId = orderId;
  el("rv-paid-amount").value = order.paid_amount || "";
  el("rv-weighing-ref").value = order.weighing_ref || "";
  el("rv-invoice-number").value = order.invoice_number || "";
  el("rv-msg").className = "msg";
  el("rv-msg").textContent = "";
  el("revenue-modal").classList.remove("hidden");
}

function closeRevenueModal() {
  revenueOrderId = null;
  el("revenue-modal").classList.add("hidden");
}

async function saveRevenueDetails() {
  const body = {
    paid_amount: el("rv-paid-amount").value || null,
    weighing_ref: el("rv-weighing-ref").value,
    invoice_number: el("rv-invoice-number").value,
  };
  const res = await fetch(`/api/orders/${revenueOrderId}/revenue-details`, {
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
  await loadOrders();
}

// ---- Modal Ghi nhận heo Loại/Hủy ----

let incidentTargetOrderId = null;
let incidentTargetLineId = null;
let incidentKind = null;

function openIncidentModal(orderId, lineId) {
  incidentTargetOrderId = orderId;
  incidentTargetLineId = lineId;
  incidentKind = null;
  el("ic-kind-culled").className = "btn btn-ghost";
  el("ic-kind-cancelled").className = "btn btn-ghost";
  el("ic-quantity").value = "";
  el("ic-photos").value = "";
  el("ic-description").value = "";
  el("ic-msg").className = "msg";
  el("ic-msg").textContent = "";
  el("incident-modal").classList.remove("hidden");
}

function closeIncidentModal() {
  incidentTargetOrderId = null;
  incidentTargetLineId = null;
  incidentKind = null;
  el("incident-modal").classList.add("hidden");
}

function selectIncidentKind(kind) {
  incidentKind = kind;
  el("ic-kind-culled").className = "btn " + (kind === "culled" ? "btn-primary" : "btn-ghost");
  el("ic-kind-cancelled").className = "btn " + (kind === "cancelled" ? "btn-primary" : "btn-ghost");
}

async function saveIncident() {
  const msg = el("ic-msg");
  msg.className = "msg";
  if (!incidentKind) {
    msg.className = "msg error";
    msg.textContent = "Vui lòng chọn Loại hoặc Hủy.";
    return;
  }
  const quantity = el("ic-quantity").value;
  if (!quantity || Number(quantity) <= 0) {
    msg.className = "msg error";
    msg.textContent = "Vui lòng nhập số lượng hợp lệ.";
    return;
  }
  const photos = el("ic-photos").files;
  if (!photos || photos.length === 0) {
    msg.className = "msg error";
    msg.textContent = "Vui lòng chụp/chọn ít nhất 1 ảnh làm bằng chứng.";
    return;
  }
  const description = el("ic-description").value.trim();
  if (!description) {
    msg.className = "msg error";
    msg.textContent = "Vui lòng nhập lý do.";
    return;
  }

  const formData = new FormData();
  formData.append("kind", incidentKind);
  formData.append("quantity", quantity);
  formData.append("description", description);
  for (const file of photos) formData.append("photos", file);

  msg.textContent = "Đang lưu...";
  try {
    const res = await fetch(`/api/orders/${incidentTargetOrderId}/lines/${incidentTargetLineId}/incidents`, {
      method: "POST",
      body: formData,
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      msg.className = "msg error";
      msg.textContent = payload.error || "Lỗi khi ghi nhận.";
      return;
    }
  } catch (err) {
    msg.className = "msg error";
    msg.textContent = "Lỗi khi lưu: " + err;
    return;
  }
  closeIncidentModal();
  await loadOrders();
}

// ---- Ghi nhận xuất giao thực tế (sale_deliveries) ----
// Gửi JSON (không multipart — route deliveries.py không nhận ảnh), khác
// saveIncident() ở trên. Loại heo cho phép chọn KHÁC loại kế hoạch của dòng
// hàng (mặc định preselect đúng loại kế hoạch cho trường hợp phổ biến không
// lệch cơ cấu).
let deliveryTargetOrderId = null;
let deliveryTargetLineId = null;

async function openDeliveryModal(orderId, lineId) {
  const order = currentOrders.find((o) => String(o.id) === String(orderId));
  const line = order && order.lines.find((l) => String(l.id) === String(lineId));
  if (!line) return;
  deliveryTargetOrderId = orderId;
  deliveryTargetLineId = lineId;

  const select = el("dv-pig-type");
  select.innerHTML = `<option value="">Đang tải...</option>`;
  el("delivery-modal").classList.remove("hidden");
  try {
    const res = await fetch("/api/pig-types");
    const pigTypes = await res.json();
    select.innerHTML = pigTypes.map((pt) => `<option value="${pt.id}">${pt.name}</option>`).join("");
    if (line.pig_type_id !== null && line.pig_type_id !== undefined) select.value = String(line.pig_type_id);
  } catch (err) {
    select.innerHTML = `<option value="">Lỗi tải danh mục loại heo</option>`;
  }

  el("dv-quantity").value = "";
  el("dv-weight").value = "";
  el("dv-price").value = "";
  el("dv-date").value = new Date().toISOString().slice(0, 10);
  el("dv-weighing-ref").value = "";
  el("dv-note").value = "";
  el("dv-msg").className = "msg";
  el("dv-msg").textContent = "";
}

function closeDeliveryModal() {
  deliveryTargetOrderId = null;
  deliveryTargetLineId = null;
  el("delivery-modal").classList.add("hidden");
}

async function saveDelivery() {
  const msg = el("dv-msg");
  msg.className = "msg";
  const pigTypeId = el("dv-pig-type").value;
  if (!pigTypeId) {
    msg.className = "msg error";
    msg.textContent = "Vui lòng chọn loại heo thực tế.";
    return;
  }
  const quantity = el("dv-quantity").value;
  if (!quantity || Number(quantity) <= 0) {
    msg.className = "msg error";
    msg.textContent = "Vui lòng nhập số lượng hợp lệ.";
    return;
  }

  const body = {
    pig_type_id: Number(pigTypeId),
    quantity: Number(quantity),
    delivered_date: el("dv-date").value || undefined,
  };
  if (el("dv-weight").value) body.total_weight_kg = Number(el("dv-weight").value);
  if (el("dv-price").value) body.unit_price = Number(el("dv-price").value);
  if (el("dv-weighing-ref").value.trim()) body.weighing_ref = el("dv-weighing-ref").value.trim();
  if (el("dv-note").value.trim()) body.note = el("dv-note").value.trim();

  msg.textContent = "Đang lưu...";
  try {
    const res = await fetch(`/api/orders/${deliveryTargetOrderId}/lines/${deliveryTargetLineId}/deliveries`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      msg.className = "msg error";
      msg.textContent = payload.error || "Lỗi khi ghi nhận xuất giao.";
      return;
    }
  } catch (err) {
    msg.className = "msg error";
    msg.textContent = "Lỗi khi lưu: " + err;
    return;
  }
  closeDeliveryModal();
  showToast("Đã ghi nhận xuất giao.", "success");
  await loadOrders();
}

async function deleteDelivery(deliveryId) {
  const ok = await confirmModal({
    title: "Xoá bản ghi xuất giao?",
    body: "Bản ghi xuất giao này sẽ bị xoá. Số lượng/giá bán thực tế của dòng hàng sẽ được tính lại.",
    confirmLabel: "Xoá",
  });
  if (!ok) return;
  const res = await fetch(`/api/deliveries/${deliveryId}`, { method: "DELETE" });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    showToast(payload.error || "Lỗi khi xoá bản ghi xuất giao.", "danger");
    return;
  }
  await loadOrders();
}

// ---- Click delegation ----

async function handleOrderListClick(e) {
  // Action bấm từ trong modal chi tiết đang mở → đóng modal trước khi
  // dispatch (trừ khi chính nút Đóng gây ra click này) — xem lý do z-index
  // ở plan.js's handlePlanListClick (áp dụng y hệt cho 5 modal tĩnh ở trang
  // này: #sale-details-modal/#revenue-modal/#mark-done-modal/
  // #delivery-modal/#incident-modal).
  const dm = e.target.closest(".detail-modal");
  if (dm && !e.target.closest(".detail-modal-close") && dm._detailModalClose) {
    dm._detailModalClose();
  }

  const detailBtn = e.target.closest(".order-btn-detail");
  const doneBtn = e.target.closest(".order-btn-done");
  const disableBtn = e.target.closest(".order-btn-disable");
  const enableBtn = e.target.closest(".order-btn-enable");
  const addLineBtn = e.target.closest(".order-btn-add-line");
  const saleDetailsBtn = e.target.closest(".order-btn-sale-details");
  const revenueBtn = e.target.closest(".order-btn-revenue");
  const quotationBtn = e.target.closest(".order-btn-quotation");
  const removeLineBtn = e.target.closest(".btn-remove-line");
  const deleteOrderBtn = e.target.closest(".order-btn-delete");
  const lockOrderBtn = e.target.closest(".order-btn-lock");
  const editLineBtn = e.target.closest(".btn-edit-line");
  const addIncidentBtn = e.target.closest(".btn-add-incident");
  const addDeliveryBtn = e.target.closest(".btn-add-delivery");
  const deleteDeliveryBtn = e.target.closest(".btn-delete-delivery");
  const linesToggleBtn = e.target.closest(".order-lines-toggle");

  if (detailBtn) {
    openOrderDetailModal(detailBtn.dataset.id);
    return;
  }

  if (linesToggleBtn) {
    const linesEl = linesToggleBtn.closest(".order-card").querySelector(".order-lines");
    linesEl.classList.toggle("is-collapsed");
    linesToggleBtn.classList.toggle("is-expanded");
  } else if (doneBtn) {
    openMarkDoneModal(doneBtn.dataset.id);
  } else if (disableBtn) {
    const ok = await confirmModal({
      title: "Vô hiệu hoá đơn hàng",
      body: "Vô hiệu hoá đơn hàng này? Bạn có thể kích hoạt lại bất cứ lúc nào.",
      confirmLabel: "Vô hiệu hoá",
    });
    if (!ok) return;
    await setOrderStatus(disableBtn.dataset.id, "disabled");
  } else if (enableBtn) {
    await setOrderStatus(enableBtn.dataset.id, "active");
  } else if (addLineBtn) {
    // Form "Thêm dòng heo" giờ sống ở trang Chào hàng — điều hướng sang đó
    // kèm order id/code qua query param (xem targetOrderFromQuery ở chao_hang.js).
    const order = currentOrders.find((o) => String(o.id) === addLineBtn.dataset.id);
    const codeParam = order && order.order_code ? `&target_order_code=${encodeURIComponent(order.order_code)}` : "";
    window.location.href = `/chao-hang?target_order=${addLineBtn.dataset.id}${codeParam}`;
  } else if (saleDetailsBtn) {
    const order = currentOrders.find((o) => String(o.id) === saleDetailsBtn.dataset.id);
    if (order) await openSaleDetailsModal(saleDetailsBtn.dataset.id, order);
  } else if (revenueBtn) {
    const order = currentOrders.find((o) => String(o.id) === revenueBtn.dataset.id);
    if (order) await openRevenueModal(revenueBtn.dataset.id, order);
  } else if (quotationBtn) {
    window.open(`/api/orders/quotation.xlsx?ids=${quotationBtn.dataset.id}`, "_blank");
  } else if (removeLineBtn) {
    await removeOrderLine(removeLineBtn.dataset.orderId, removeLineBtn.dataset.lineId);
  } else if (deleteOrderBtn) {
    await deleteOrder(deleteOrderBtn.dataset.id);
  } else if (lockOrderBtn) {
    const order = currentOrders.find((o) => String(o.id) === lockOrderBtn.dataset.id);
    await lockOrder(lockOrderBtn.dataset.id, order && order.order_code);
  } else if (editLineBtn) {
    await editLine(editLineBtn.dataset.orderId, editLineBtn.dataset.lineId);
  } else if (addIncidentBtn) {
    openIncidentModal(addIncidentBtn.dataset.orderId, addIncidentBtn.dataset.lineId);
  } else if (addDeliveryBtn) {
    await openDeliveryModal(addDeliveryBtn.dataset.orderId, addDeliveryBtn.dataset.lineId);
  } else if (deleteDeliveryBtn) {
    await deleteDelivery(deleteDeliveryBtn.dataset.id);
  }
}

document.body.addEventListener("click", handleOrderListClick);
if (el("md-save")) el("md-save").addEventListener("click", saveMarkDone);
if (el("md-cancel")) el("md-cancel").addEventListener("click", closeMarkDoneModal);
if (el("sd-save")) el("sd-save").addEventListener("click", saveSaleDetails);
if (el("sd-cancel")) el("sd-cancel").addEventListener("click", closeSaleDetailsModal);
if (el("rv-save")) el("rv-save").addEventListener("click", saveRevenueDetails);
if (el("rv-cancel")) el("rv-cancel").addEventListener("click", closeRevenueModal);
if (el("ic-save")) el("ic-save").addEventListener("click", saveIncident);
if (el("ic-cancel")) el("ic-cancel").addEventListener("click", closeIncidentModal);
if (el("ic-kind-culled")) el("ic-kind-culled").addEventListener("click", () => selectIncidentKind("culled"));
if (el("ic-kind-cancelled")) el("ic-kind-cancelled").addEventListener("click", () => selectIncidentKind("cancelled"));
if (el("dv-save")) el("dv-save").addEventListener("click", saveDelivery);
if (el("dv-cancel")) el("dv-cancel").addEventListener("click", closeDeliveryModal);

if (el("order-filter-status")) el("order-filter-status").addEventListener("change", refreshOrdersView);
if (el("order-filter-search")) el("order-filter-search").addEventListener("input", refreshOrdersView);

// Đến từ link "Cần xử lý"/"Cảnh báo" trên Tổng quan (?highlight=<id>) —
// scroll tới đúng dòng bảng + tô sáng tạm thời rồi mở luôn modal chi tiết.
function highlightFromQuery() {
  const id = new URLSearchParams(location.search).get("highlight");
  if (!id) return;
  const row = document.querySelector(`#order-list tr[data-id="${id}"]`);
  if (!row) return;
  row.scrollIntoView({ behavior: "smooth", block: "center" });
  row.classList.add("is-highlighted");
  setTimeout(() => row.classList.remove("is-highlighted"), 3000);
  openOrderDetailModal(id);
}

if (el("order-list")) {
  (async function initChotBan() {
    await loadOrders();
    highlightFromQuery();
  })();
}
