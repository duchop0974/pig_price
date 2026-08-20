// Trang "Xuất giao" — danh sách toàn bộ lần xuất giao thực tế trong hệ
// thống, không phân biệt kế hoạch/đơn hàng. Thuần đọc: 1 fetch
// /api/deliveries (đã lọc farm-scope ở backend), lọc client-side thêm
// theo trại/loại heo/ngày/tìm kiếm (khuôn applyDsFilters ở doi_soat.js).
// Xoá dùng lại DELETE /api/deliveries/<id> đã có sẵn (khoá thì ẩn nút xoá).

const CAN_DELETE_DELIVERIES = (window.CURRENT_USER_PERMISSIONS || []).includes("plans.delivery_delete");

let allDeliveries = [];

function fillXgFilterOptions(deliveries) {
  const farmSelect = el("xg-filter-farm");
  const typeSelect = el("xg-filter-pig-type");
  const farms = [...new Set(deliveries.map((d) => d.farm).filter(Boolean))].sort();
  const types = [...new Set(deliveries.map((d) => d.pig_type_name).filter(Boolean))].sort();
  const curFarm = farmSelect.value;
  const curType = typeSelect.value;
  farmSelect.innerHTML = `<option value="">Tất cả trại</option>` + farms.map((f) => `<option value="${f}">${f}</option>`).join("");
  typeSelect.innerHTML = `<option value="">Tất cả loại heo</option>` + types.map((t) => `<option value="${t}">${t}</option>`).join("");
  if (farms.includes(curFarm)) farmSelect.value = curFarm;
  if (types.includes(curType)) typeSelect.value = curType;
}

function renderXgSummary(deliveries) {
  const totalQuantity = deliveries.reduce((sum, d) => sum + (d.quantity || 0), 0);
  el("xg-count-total").innerHTML = `${deliveries.length}<span class="unit">lần</span>`;
  el("xg-count-quantity").innerHTML = `${fmtPrice(totalQuantity)}<span class="unit">con</span>`;
}

function applyXgFilters(deliveries) {
  const farm = el("xg-filter-farm").value;
  const pigType = el("xg-filter-pig-type").value;
  const dateFrom = el("xg-filter-date-from").value;
  const dateTo = el("xg-filter-date-to").value;
  const q = el("xg-filter-search").value.trim().toLowerCase();
  return deliveries.filter((d) => {
    if (farm && d.farm !== farm) return false;
    if (pigType && d.pig_type_name !== pigType) return false;
    if (dateFrom && d.delivered_date && d.delivered_date < dateFrom) return false;
    if (dateTo && d.delivered_date && d.delivered_date > dateTo) return false;
    if (q) {
      const hay = `${d.plan_code || ""} ${d.order_code || ""} ${d.customer_name || ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

function deliveryRowHtml(d) {
  const deleteBtn =
    !d.locked_at && CAN_DELETE_DELIVERIES
      ? `<button type="button" class="btn btn-ghost btn-sm btn-danger" onclick="deleteDelivery(${d.id})">Xoá</button>`
      : "";
  return `<tr>
    <td data-label="Ngày xuất">${fmtIsoDate(d.delivered_date)}</td>
    <td data-label="Kế hoạch">${d.plan_code || "—"}</td>
    <td data-label="Đơn hàng">${d.order_code || "—"}</td>
    <td data-label="Khách hàng">${d.customer_name || "—"}</td>
    <td data-label="Loại heo">${d.pig_type_name || "—"}</td>
    <td data-label="Số lượng">${fmtPrice(d.quantity)} con</td>
    <td data-label="Trọng lượng">${fmtWeight(d.total_weight_kg)} kg</td>
    <td data-label="Đơn giá">${d.unit_price ? fmtPrice(d.unit_price) + " đ" : "—"}</td>
    <td data-label="Trạng thái">${d.locked_at ? renderBadge("locked") : ""}</td>
    <td>${deleteBtn}</td>
  </tr>`;
}

function renderXgTable() {
  const filtered = applyXgFilters(allDeliveries);
  const body = el("xuat-giao-list");
  const emptyMsg = el("xuat-giao-empty");
  if (!filtered.length) {
    body.innerHTML = "";
    emptyMsg.classList.remove("hidden");
    return;
  }
  emptyMsg.classList.add("hidden");
  body.innerHTML = filtered.map(deliveryRowHtml).join("");
}

async function loadDeliveries() {
  const res = await fetch("/api/deliveries");
  const deliveries = await res.json();
  allDeliveries = deliveries || [];
  fillXgFilterOptions(allDeliveries);
  renderXgSummary(allDeliveries);
  renderXgTable();
}

async function deleteDelivery(deliveryId) {
  const d = allDeliveries.find((x) => x.id === deliveryId);
  const label = d && d.plan_code ? `lần xuất giao của ${d.plan_code}` : "lần xuất giao này";
  const ok = await confirmModal({
    title: "Xoá bản ghi xuất giao?",
    body: `Xoá ${label} sẽ không thể khôi phục.`,
    confirmLabel: "Xoá vĩnh viễn",
  });
  if (!ok) return;
  const res = await fetch(`/api/deliveries/${deliveryId}`, { method: "DELETE" });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    showToast(payload.error || "Lỗi khi xoá bản ghi xuất giao.", "danger");
    return;
  }
  showToast("Đã xoá bản ghi xuất giao.", "success");
  await loadDeliveries();
}

["xg-filter-farm", "xg-filter-pig-type", "xg-filter-date-from", "xg-filter-date-to"].forEach((id) => {
  if (el(id)) el(id).addEventListener("change", renderXgTable);
});
if (el("xg-filter-search")) el("xg-filter-search").addEventListener("input", renderXgTable);

if (el("xuat-giao-list")) loadDeliveries();
