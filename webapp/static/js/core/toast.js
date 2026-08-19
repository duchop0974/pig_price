// showToast(message, type) — hiển thị thông báo nổi góc màn hình, dùng
// ".toast-container" được mount sẵn trong base.html. Chưa page nào gọi ở
// Phase 0 — hạ tầng cho các phase sau thay dần alert()/msg text.
function showToast(message, type) {
  const container = document.querySelector(".toast-container");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = "toast" + (type ? ` toast-${type}` : "");
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 4000);
}
