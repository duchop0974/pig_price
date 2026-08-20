// Trang Tổng quan — khối "Kế hoạch → Thực tế" mới (Giai đoạn 3): 5 KPI +
// biểu đồ xu hướng theo ngày + biểu đồ cơ cấu loại heo + bảng theo ngày.
// 1 fetch duy nhất /api/dashboard/summary?days=N nuôi cả 3 phần hiển thị,
// tránh gọi lại API khi vẽ nhiều nơi cùng 1 dữ liệu.

let trendChart = null;
let compositionChart = null;

function fmtSignedQty(n) {
  const sign = n > 0 ? "+" : "";
  return `${sign}${fmtPrice(n)}`;
}

function pctText(pct) {
  if (pct === null || pct === undefined) return "";
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct}% kế hoạch`;
}

function renderKpis(kpi) {
  el("kpi-planned-value").innerHTML = `${fmtPrice(kpi.planned_qty)}<span class="unit">con</span>`;
  el("kpi-allocated-value").innerHTML = `${fmtPrice(kpi.allocated_qty)}<span class="unit">con</span>`;
  el("kpi-allocated-sub").textContent = pctText(kpi.allocated_pct);
  el("kpi-actual-value").innerHTML = `${fmtPrice(kpi.actual_qty)}<span class="unit">con</span>`;
  el("kpi-actual-sub").textContent = pctText(kpi.actual_pct);
  el("kpi-not-shipped-value").innerHTML = `${fmtPrice(kpi.not_shipped_qty)}<span class="unit">con</span>`;
  el("kpi-not-shipped-sub").textContent = pctText(kpi.not_shipped_pct);

  const varianceEl = el("kpi-variance-value");
  varianceEl.innerHTML = `${fmtSignedQty(kpi.variance_qty)}<span class="unit">con</span>`;
  varianceEl.className = "kpi-value " + (kpi.variance_qty < 0 ? "text-danger" : kpi.variance_qty > 0 ? "text-success" : "");
  el("kpi-variance-sub").textContent = pctText(kpi.variance_pct);
}

// Trạng thái theo ngày — "Có sai lệch" chỉ tính khi ngày ĐÃ QUA (ngày
// tương lai/hôm nay chưa xuất hết là bình thường, không phải sai lệch),
// khớp đúng cách reconciliation_status phân biệt needs_reconciliation vs
// in_progress ở plan.js (planned_date < hôm nay).
function dailyStatusBadge(day, todayIso) {
  if (day.date >= todayIso) return "";
  if (day.variance_qty === 0) return `<span class="badge badge-success">Hoàn thành</span>`;
  return `<span class="badge badge-warning">Có sai lệch</span>`;
}

function renderDailyTable(daily) {
  const todayIso = new Date().toISOString().slice(0, 10);
  const nonEmpty = daily.filter((d) => d.planned_qty || d.allocated_qty || d.actual_qty);
  const body = el("daily-table-body");
  const emptyMsg = el("daily-table-empty");
  if (!nonEmpty.length) {
    body.innerHTML = "";
    emptyMsg.classList.remove("hidden");
    return;
  }
  emptyMsg.classList.add("hidden");
  body.innerHTML = nonEmpty
    .slice()
    .reverse()
    .map(
      (d) => `<tr>
        <td data-label="Ngày dự kiến">${fmtIsoDate(d.date)}</td>
        <td data-label="Kế hoạch (con)">${fmtPrice(d.planned_qty)}</td>
        <td data-label="Đã chốt (con)">${fmtPrice(d.allocated_qty)}</td>
        <td data-label="Đã xuất (con)">${fmtPrice(d.actual_qty)}</td>
        <td data-label="Lệch (con)" class="${d.variance_qty < 0 ? "text-danger" : d.variance_qty > 0 ? "text-success" : ""}">${fmtSignedQty(d.variance_qty)}</td>
        <td data-label="Trạng thái">${dailyStatusBadge(d, todayIso)}</td>
      </tr>`
    )
    .join("");
}

function renderTrendChart(daily) {
  const canvas = el("trend-chart");
  const emptyMsg = el("trend-chart-empty");

  const hasData = daily.some(
    (d) =>
      Number(d.planned_qty || 0) !== 0 ||
      Number(d.allocated_qty || 0) !== 0 ||
      Number(d.actual_qty || 0) !== 0 ||
      Number(d.variance_qty || 0) !== 0
  );

  // Huỷ biểu đồ cũ
  if (trendChart) {
    trendChart.destroy();
    trendChart = null;
  }

  // Không có dữ liệu
  if (!hasData) {
    canvas.classList.add("hidden");
    emptyMsg.classList.remove("hidden");
    return;
  }

  // Có dữ liệu
  canvas.classList.remove("hidden");
  emptyMsg.classList.add("hidden");

  const ctx = canvas.getContext("2d");

  const labels = daily.map((d) => fmtIsoDate(d.date));

  const datasets = [
    {
      label: "Kế hoạch",
      data: daily.map((d) => d.planned_qty),
      borderColor: "#0072b5",
      tension: 0.2,
    },
    {
      label: "Đã chốt",
      data: daily.map((d) => d.allocated_qty),
      borderColor: "#c77c02",
      tension: 0.2,
    },
    {
      label: "Đã xuất",
      data: daily.map((d) => d.actual_qty),
      borderColor: "#1f9d55",
      tension: 0.2,
    },
    {
      label: "Lệch",
      data: daily.map((d) => d.variance_qty),
      borderColor: "#d64545",
      tension: 0.2,
      borderDash: [4, 3],
    },
  ];

  trendChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,

      interaction: {
        mode: "index",
        intersect: false,
      },

      scales: {
        x: {
          ticks: {
            maxTicksLimit: 8,
          },
        },
        y: {
          title: {
            display: true,
            text: "con",
          },
        },
      },

      plugins: {
        legend: {
          position: "bottom",
        },
        tooltip: {
          mode: "index",
          intersect: false,
        },
      },
    },
  });
}

const COMPOSITION_COLORS = ["#0072b5", "#1f9d55", "#c77c02", "#7a3fc9", "#d64545", "#0aa5a8", "#8a8f98"];

function renderCompositionChart(composition) {
  const canvas = el("composition-chart");
  const emptyMsg = el("composition-empty");
  if (!composition.length) {
    if (compositionChart) {
      compositionChart.destroy();
      compositionChart = null;
    }
    canvas.classList.add("hidden");
    emptyMsg.classList.remove("hidden");
    return;
  }
  canvas.classList.remove("hidden");
  emptyMsg.classList.add("hidden");
  const ctx = canvas.getContext("2d");
  if (compositionChart) compositionChart.destroy();
  compositionChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: composition.map((c) => `${c.pig_type_name} (${c.pct}%)`),
      datasets: [
        {
          data: composition.map((c) => c.quantity),
          backgroundColor: composition.map((_, i) => COMPOSITION_COLORS[i % COMPOSITION_COLORS.length]),
        },
      ],
    },
    options: {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      position: "bottom",
    },
  },
},
  });
}

// Filter trại/khách hàng/loại heo (Phase 3, brief nghiệp vụ) — option lấy
// từ 3 API GET đã có sẵn (/api/farms, /api/customers, /api/pig-types),
// không tạo route mới. /api/customers có thể 403 (gate customers.view) —
// select đó chỉ render khi Jinja current_user_can() đúng, nhưng fetch vẫn
// bọc try/catch phòng trường hợp quyền đổi giữa lúc render/gọi API.
async function loadDashboardFilterOptions() {
  const farmSelect = el("dashboard-filter-farm");
  const customerSelect = el("dashboard-filter-customer");
  const typeSelect = el("dashboard-filter-pig-type");
  if (farmSelect) {
    const farms = await (await fetch("/api/farms")).json();
    farmSelect.innerHTML =
      `<option value="">Tất cả trại</option>` + farms.map((f) => `<option value="${f.id}">${f.code}</option>`).join("");
  }
  if (customerSelect) {
    try {
      const customers = await (await fetch("/api/customers?active_only=true")).json();
      customerSelect.innerHTML =
        `<option value="">Tất cả khách hàng</option>` +
        customers.map((c) => `<option value="${c.id}">${c.name}</option>`).join("");
    } catch (e) {
      /* không có quyền xem khách hàng — giữ nguyên chỉ "Tất cả khách hàng" */
    }
  }
  if (typeSelect) {
    const types = await (await fetch("/api/pig-types")).json();
    typeSelect.innerHTML =
      `<option value="">Tất cả loại heo</option>` + types.map((t) => `<option value="${t.id}">${t.name}</option>`).join("");
  }
}

function dashboardFilterParams() {
  const params = new URLSearchParams();
  params.set("days", el("dashboard-days").value);
  if (el("dashboard-filter-farm") && el("dashboard-filter-farm").value) {
    params.set("farm_id", el("dashboard-filter-farm").value);
  }
  if (el("dashboard-filter-customer") && el("dashboard-filter-customer").value) {
    params.set("customer_id", el("dashboard-filter-customer").value);
  }
  if (el("dashboard-filter-pig-type") && el("dashboard-filter-pig-type").value) {
    params.set("pig_type_id", el("dashboard-filter-pig-type").value);
  }
  return params;
}

async function loadDashboardSummary() {
  const res = await fetch(`/api/dashboard/summary?${dashboardFilterParams().toString()}`);
  if (!res.ok) return;
  const data = await res.json();
  renderKpis(data.kpi);
  renderDailyTable(data.daily);
  renderTrendChart(data.daily);
  renderCompositionChart(data.composition);
}

if (el("dashboard-days")) {
  ["dashboard-days", "dashboard-filter-farm", "dashboard-filter-customer", "dashboard-filter-pig-type"].forEach((id) => {
    if (el(id)) el(id).addEventListener("change", () => loadDashboardSummary());
  });
  loadDashboardFilterOptions().then(() => loadDashboardSummary());
}
