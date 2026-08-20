// Badge số thông báo chưa đọc trên nav — load 1 LẦN lúc tải trang (Phase 5,
// brief nghiệp vụ, v1 cố ý đơn giản: không polling định kỳ). Tải global qua
// base.html nên không dùng el()/fetch helper của common.js (chỉ load theo
// trang, không phải mọi trang đều có).
(function () {
  const badge = document.getElementById("nav-notification-badge");
  if (!badge) return;
  fetch("/api/notifications/unread-count")
    .then((res) => (res.ok ? res.json() : null))
    .then((data) => {
      if (!data || !data.count) return;
      badge.textContent = data.count > 99 ? "99+" : String(data.count);
      badge.classList.remove("hidden");
    })
    .catch(() => {});
})();
