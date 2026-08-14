const el = (id) => document.getElementById(id);
const fmtPrice = (v) => (v === null || v === undefined ? "" : Math.round(v).toLocaleString("vi-VN"));

function dmyToIso(dmy) {
  const [d, m, y] = dmy.split("/");
  return `${y}-${m}-${d}`;
}

function fmtIsoDate(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}
