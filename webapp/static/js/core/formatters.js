const el = (id) => document.getElementById(id);
const fmtPrice = (v) => (v === null || v === undefined ? "" : Math.round(v).toLocaleString("vi-VN"));

// Ô nhập giá dạng text (không phải type=number) để hiển thị được dấu chấm
// ngăn cách hàng nghìn trong lúc gõ — 2 hàm thuần, không đụng DOM, dùng cho
// mọi ô giá cần format-khi-gõ/parse-khi-submit trong toàn app.
function formatPriceInputValue(raw) {
  const digits = String(raw ?? "").replace(/\D/g, "");
  if (!digits) return "";
  return Number(digits).toLocaleString("vi-VN");
}
function parsePriceInputValue(str) {
  const digits = String(str ?? "").replace(/\D/g, "");
  return digits ? Number(digits) : null;
}

function dmyToIso(dmy) {
  const [d, m, y] = dmy.split("/");
  return `${y}-${m}-${d}`;
}

function fmtIsoDate(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}
