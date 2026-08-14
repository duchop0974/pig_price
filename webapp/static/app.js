const SHORT_LABEL = {
  "nongnghiepmoitruong.vn": "NNMT",
  "vietnambiz.vn": "VietnamBiz",
  "greenfeed.com.vn": "GreenFeed",
  "vinanet.vn": "Vinanet",
  "baovanhoa.vn": "BaoVanHoa",
};

const el = (id) => document.getElementById(id);
const fmtPrice = (v) => (v === null || v === undefined ? "" : Math.round(v).toLocaleString("vi-VN"));

function dmyToIso(dmy) {
  const [d, m, y] = dmy.split("/");
  return `${y}-${m}-${d}`;
}

const WEEKDAY_NAMES = ["Chủ Nhật", "Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy"];

function getIsoWeek(date) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const dayNum = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  return Math.ceil(((d - yearStart) / 86400000 + 1) / 7);
}

function renderCurrentDate() {
  const now = new Date();
  const weekday = WEEKDAY_NAMES[now.getDay()];
  const dd = String(now.getDate()).padStart(2, "0");
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const yyyy = now.getFullYear();
  const week = getIsoWeek(now);
  el("current-date").textContent = `${weekday}, ${dd}/${mm}/${yyyy} · Tuần ${week}`;
}

let lastPayload = null;

function populateRegionSelect(payload) {
  const select = el("region-select");
  if (select.dataset.populated) return;
  const regions = payload.regions || [];
  select.innerHTML =
    `<option value="">Tất cả</option>` +
    regions.map((r) => `<option value="${r}">${r}</option>`).join("");
  select.dataset.populated = "1";
}

function renderCards() {
  const cards = el("price-cards");
  const payload = lastPayload;
  if (!payload || !payload.date) {
    cards.innerHTML = "";
    return;
  }

  const order = payload.source_order || Object.keys(payload.sources);
  const selectedRegion = el("region-select").value;
  const rows = selectedRegion
    ? payload.rows.filter((row) => row.region === selectedRegion)
    : payload.rows;

  if (!rows.length) {
    cards.innerHTML = `<p class="msg">Không có dữ liệu.</p>`;
    return;
  }

  cards.innerHTML = rows
    .map((row) => {
      const sourceRows = order
        .map((s) => {
          const v = row.prices[s];
          const valueHtml =
            v === null || v === undefined
              ? `<span class="source-value empty">-</span>`
              : `<span class="source-value">${fmtPrice(v)}</span>`;
          return `<div class="source-row"><span class="source-label">${SHORT_LABEL[s] || s}</span>${valueHtml}</div>`;
        })
        .join("");
      return `<article class="province-card"><h3 class="province-name">${row.province}</h3>${sourceRows}</article>`;
    })
    .join("");
}

const REGION_CLASS = {
  "Miền Bắc": "region-bac",
  "Miền Trung - Tây Nguyên": "region-trung",
  "Miền Nam": "region-nam",
};

function renderRegionSummary(payload) {
  const box = el("region-summary");
  if (!payload.date || !payload.rows.length) {
    box.innerHTML = "";
    return;
  }

  const regions = payload.regions || [];
  const items = regions
    .map((region) => {
      const values = payload.rows
        .filter((row) => row.region === region)
        .flatMap((row) => Object.values(row.prices))
        .filter((v) => v !== null && v !== undefined);
      if (!values.length) return null;
      const min = Math.min(...values);
      const max = Math.max(...values);
      const range =
        min === max
          ? `${fmtPrice(min)}<span class="unit"> đ/kg</span>`
          : `${fmtPrice(min)}–${fmtPrice(max)}<span class="unit"> đ/kg</span>`;
      const cls = REGION_CLASS[region] || "";
      return `<div class="region-summary-item ${cls}">
        <div class="region-name">${region}</div>
        <div class="region-range">${range}</div>
        <div class="region-date">Ngày ${payload.date}</div>
      </div>`;
    })
    .filter(Boolean)
    .join("");
  box.innerHTML = items
    ? `<h2>Tóm tắt giá theo miền</h2><div class="region-summary-grid">${items}</div>`
    : "";
}

function renderComparison(payload) {
  lastPayload = payload;
  const status = el("table-status");
  const sourcesBox = el("sources-updated");

  if (!payload.date) {
    status.textContent = "Chưa có dữ liệu.";
    sourcesBox.innerHTML = "";
    renderRegionSummary(payload);
    populateRegionSelect(payload);
    renderCards();
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

  renderRegionSummary(payload);
  populateRegionSelect(payload);
  renderCards();
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
    "baovanhoa.vn": "#c77c02",
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
      pointRadius: 1.5,
      pointHoverRadius: 4,
    }));

  const ctx = el("price-chart").getContext("2d");
  if (chart) chart.destroy();
  chart = new Chart(ctx, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { ticks: { maxTicksLimit: 6 } },
        y: { title: { display: true, text: "đ/kg" } },
      },
      plugins: {
        legend: { position: "bottom" },
        tooltip: { mode: "index", intersect: false },
      },
    },
  });
}

async function loadProvinces() {
  const res = await fetch("/api/provinces");
  const provinces = await res.json();
  const options = provinces.map((p) => `<option value="${p}">${p}</option>`).join("");
  const hanoi = provinces.find((p) => p.toLowerCase().includes("hà nội"));

  const select = el("province-select");
  const current = select.value;
  select.innerHTML = options;
  select.value = provinces.includes(current) ? current : hanoi || select.value;
}

el("btn-today").addEventListener("click", doRefresh);
el("btn-bydate-toggle").addEventListener("click", () => {
  const dateRow = el("date-row");
  const confirmRow = el("date-confirm-row");
  const showing = !dateRow.hidden;
  dateRow.hidden = showing;
  confirmRow.hidden = showing;
  if (!showing) el("date-picker").focus();
});
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
el("region-select").addEventListener("change", renderCards);

(async function init() {
  renderCurrentDate();
  await loadToday();
  await loadProvinces();
  await loadChart();
})();
