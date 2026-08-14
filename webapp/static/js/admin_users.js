async function submitUserForm(e) {
  e.preventDefault();
  const msg = el("user-msg");
  msg.className = "msg";
  msg.textContent = "Đang tạo...";
  const body = {
    username: el("new-username").value,
    display_name: el("new-display-name").value,
    password: el("new-password").value,
    role: el("new-role").value,
  };
  try {
    const res = await fetch("/api/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await res.json();
    if (!res.ok) {
      msg.className = "msg error";
      msg.textContent = payload.error || "Lỗi khi tạo tài khoản.";
      return;
    }
    msg.textContent = "Đã tạo tài khoản. Đang tải lại danh sách...";
    location.reload();
  } catch (err) {
    msg.className = "msg error";
    msg.textContent = "Lỗi khi tạo tài khoản: " + err;
  }
}

async function handleListClick(e) {
  const toggleBtn = e.target.closest(".btn-toggle");
  const resetBtn = e.target.closest(".btn-reset");

  if (toggleBtn) {
    const id = toggleBtn.dataset.id;
    const currentlyActive = toggleBtn.dataset.active === "1";
    const label = currentlyActive ? "khoá" : "mở lại";
    if (!confirm(`Xác nhận ${label} tài khoản này?`)) return;
    await fetch(`/api/admin/users/${id}/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: !currentlyActive }),
    });
    location.reload();
  } else if (resetBtn) {
    const id = resetBtn.dataset.id;
    const password = prompt("Nhập mật khẩu mới (tối thiểu 6 ký tự):");
    if (!password) return;
    const res = await fetch(`/api/admin/users/${id}/reset-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    const payload = await res.json();
    if (!res.ok) {
      alert(payload.error || "Lỗi khi đặt lại mật khẩu.");
      return;
    }
    alert("Đã đặt lại mật khẩu.");
  }
}

el("user-form").addEventListener("submit", submitUserForm);
el("user-list").addEventListener("click", handleListClick);
