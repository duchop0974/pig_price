// Trang "Thông báo" (Phase 5, brief nghiệp vụ) — thuần fetch/render, khớp
// khuôn xuat_giao.js/doi_soat.js (1 fetch, render client-side).

function notificationItemHtml(n) {
  const unreadCls = n.is_read ? "" : " is-unread";
  const titleHtml = n.link_url ? `<a href="${n.link_url}">${n.title}</a>` : n.title;
  const readBtn = n.is_read ? "" : `<button type="button" class="btn btn-ghost btn-sm btn-mark-read" data-id="${n.id}">Đánh dấu đã đọc</button>`;
  return `<div class="timeline-item${unreadCls}">
    <div class="timeline-item-time">${n.created_at}</div>
    <div class="timeline-item-title">${titleHtml}</div>
    ${n.body ? `<div class="timeline-item-detail">${n.body}</div>` : ""}
    ${readBtn}
  </div>`;
}

function renderNotifications(items) {
  const box = el("notification-list");
  const emptyMsg = el("notification-empty");
  if (!items.length) {
    box.innerHTML = "";
    emptyMsg.classList.remove("hidden");
    return;
  }
  emptyMsg.classList.add("hidden");
  box.innerHTML = items.map(notificationItemHtml).join("");
}

async function loadNotifications() {
  const res = await fetch("/api/notifications");
  const items = await res.json();
  renderNotifications(items || []);
}

async function markRead(id) {
  await fetch(`/api/notifications/${id}/read`, { method: "POST" });
  await loadNotifications();
}

async function markAllRead() {
  await fetch("/api/notifications/read-all", { method: "POST" });
  await loadNotifications();
}

if (el("notification-list")) {
  el("notification-list").addEventListener("click", (e) => {
    const btn = e.target.closest(".btn-mark-read");
    if (btn) markRead(btn.dataset.id);
  });
  if (el("btn-mark-all-read")) el("btn-mark-all-read").addEventListener("click", markAllRead);
  loadNotifications();
}
