const SHORT_LABEL = {
  "nongnghiepmoitruong.vn": "NNMT",
  "vietnambiz.vn": "VietnamBiz",
  "greenfeed.com.vn": "GreenFeed",
  "vinanet.vn": "Vinanet",
};

const el = (id) => document.getElementById(id);
const fmtPrice = (v) => (v === null || v === undefined ? "" : Math.round(v).toLocaleString("vi-VN"));

function dmyToIso(dmy) {
  const [d, m, y] = dmy.split("/");
  return `${y}-${m}-${d}`;
}

function renderComparison(payload) {
  const status = el("table-status");
  const sourcesBox = el("sources-updated");
  const head = el("table-head");
  const body = el("table-body");

  if (!payload.date) {
    status.textContent = "Chưa có dữ liệu.";
    sourcesBox.innerHTML = "";
    head.innerHTML = "";
    body.innerHTML = "";
    return;
  }

  status.textContent =
    payload.mode === "exact_date"
      ? `Dữ liệu ngày ${payload.date}`
      : `Giá mới nhất theo từng nguồn (tính đến ${payload.date})`;
  el("date-picker").value = dmyToIso(payload.date);

  const order = payload.source_order || Object.keys(payload.sources);
  const sourceItems = order
    .map((s) => {
      const d = payload.sources[s];
      return d
        ? `<li>${s}: <strong>${d}</strong></li>`
        : `<li class="missing">${s}: không có dữ liệu</li>`;
    })
    .join("");
  sourcesBox.innerHTML = `<strong>Ngày cập nhật theo nguồn:</strong><ul>${sourceItems}</ul>`;

  head.innerHTML =
    `<th>Địa phương</th>` +
    order.map((s) => `<th>${SHORT_LABEL[s] || s}</th>`).join("");

  if (!payload.rows.length) {
    body.innerHTML = `<tr><td colspan="${order.length + 1}">Không có dữ liệu.</td></tr>`;
    return;
  }

  body.innerHTML = payload.rows
    .map((row) => {
      const cells = order
        .map((s) => {
          const v = row.prices[s];
          return v === null || v === undefined
            ? `<td class="empty">-</td>`
            : `<td>${fmtPrice(v)}</td>`;
        })
        .join("");
      return `<tr><td>${row.province}</td>${cells}</tr>`;
    })
    .join("");
}

async function loadToday() {
  el("table-status").textContent = "Đang tải dữ liệu...";
  const res = await fetch("/api/today");
  const payload = await res.json();
  renderComparison(payload);
}

async function loadDate(iso) {
  el("table-status").textContent = "Đang tải dữ liệu...";
  const res = await fetch(`/api/date/${iso}`);
  const payload = await res.json();
  renderComparison(payload);
  await loadChart();
}

async function doRefresh() {
  const btn = el("btn-today");
  const msg = el("refresh-msg");
  btn.disabled = true;
  msg.className = "msg";
  msg.textContent = "Đang lấy giá mới từ các nguồn, vui lòng đợi...";
  try {
    const res = await fetch("/api/refresh", { method: "POST" });
    const payload = await res.json();
    if (res.status === 429) {
      msg.className = "msg error";
      msg.textContent = payload.error;
    } else {
      msg.textContent = "Đã cập nhật xong.";
      renderComparison(payload);
      await loadProvinces();
      await loadChart();
    }
  } catch (e) {
    msg.className = "msg error";
    msg.textContent = "Lỗi khi cập nhật: " + e;
  } finally {
    btn.disabled = false;
  }
}

let chart;
async function loadChart() {
  const province = el("province-select").value;
  const days = el("days-select").value;
  if (!province) return;

  const res = await fetch(`/api/history?province=${encodeURIComponent(province)}&days=${days}`);
  const payload = await res.json();

  const dateSet = new Set(payload.points.map((p) => p.date));
  const labels = [...dateSet].sort(
    (a, b) => new Date(dmyToIso(a)) - new Date(dmyToIso(b))
  );
  const labelIndex = new Map(labels.map((d, i) => [d, i]));

  const bySource = {};
  for (const p of payload.points) {
    if (!bySource[p.source]) bySource[p.source] = new Array(labels.length).fill(null);
    bySource[p.source][labelIndex.get(p.date)] = p.price;
  }

  const colors = {
    "nongnghiepmoitruong.vn": "#2f7a4f",
    "vietnambiz.vn": "#c0392b",
    "greenfeed.com.vn": "#2b6cc0",
    "vinanet.vn": "#8e44ad",
  };

  const datasets = (payload.source_order || Object.keys(bySource))
    .filter((s) => bySource[s])
    .map((s) => ({
      label: SHORT_LABEL[s] || s,
      data: bySource[s],
      borderColor: colors[s] || "#888",
      backgroundColor: colors[s] || "#888",
      tension: 0.2,
      spanGaps: true,
    }));

  const ctx = el("price-chart").getContext("2d");
  if (chart) chart.destroy();
  chart = new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      scales: {
        x: { ticks: { maxTicksLimit: 6 } },
        y: { title: { display: true, text: "đ/kg" } },
      },
      plugins: { legend: { position: "bottom" } },
    },
  });
}

async function loadProvinces() {
  const res = await fetch("/api/provinces");
  const provinces = await res.json();
  const select = el("province-select");
  const current = select.value;
  select.innerHTML = provinces.map((p) => `<option value="${p}">${p}</option>`).join("");
  if (provinces.includes(current)) {
    select.value = current;
  } else {
    const hanoi = provinces.find((p) => p.toLowerCase().includes("hà nội"));
    if (hanoi) select.value = hanoi;
  }
}

el("btn-today").addEventListener("click", doRefresh);
el("btn-bydate").addEventListener("click", () => {
  const iso = el("date-picker").value;
  if (!iso) {
    el("refresh-msg").className = "msg error";
    el("refresh-msg").textContent = "Vui lòng chọn một ngày.";
    return;
  }
  el("refresh-msg").className = "msg";
  el("refresh-msg").textContent = "";
  loadDate(iso);
});
el("province-select").addEventListener("change", loadChart);
el("days-select").addEventListener("change", loadChart);

(async function init() {
  await loadToday();
  await loadProvinces();
  await loadChart();
})();
