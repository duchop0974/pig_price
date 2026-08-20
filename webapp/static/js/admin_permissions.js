async function submitRoleForm(e) {
  e.preventDefault();
  const msg = el("role-msg");
  msg.className = "msg";
  msg.textContent = "Đang tạo...";
  const body = {
    key: el("new-role-key").value.trim().toLowerCase(),
    name: el("new-role-name").value.trim(),
  };
  try {
    const res = await fetch("/api/admin/roles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await res.json();
    if (!res.ok) {
      msg.className = "msg error";
      msg.textContent = payload.error || "Lỗi khi tạo vai trò.";
      return;
    }
    msg.textContent = "Đã tạo vai trò. Đang tải lại...";
    location.reload();
  } catch (err) {
    msg.className = "msg error";
    msg.textContent = "Lỗi khi tạo vai trò: " + err;
  }
}

async function handleRoleDelete(e) {
  const btn = e.target.closest(".btn-role-delete");
  if (!btn) return;
  const key = btn.dataset.key;
  const ok = await confirmModal({
    title: `Xoá vai trò "${key}"?`,
    body: "Chỉ xoá được nếu không còn tài khoản nào dùng.",
    confirmLabel: "Xoá vĩnh viễn",
  });
  if (!ok) return;
  const res = await fetch(`/api/admin/roles/${key}`, { method: "DELETE" });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    showToast(payload.error || "Lỗi khi xóa vai trò.", "danger");
    return;
  }
  showToast("Đã xoá vai trò.", "success");
  location.reload();
}

async function saveAllPermissions() {
  const msg = el("permission-msg");
  msg.className = "msg";
  msg.textContent = "Đang lưu...";

  const roleKeys = [...new Set([...document.querySelectorAll(".perm-checkbox")].map((c) => c.dataset.role))];
  try {
    for (const roleKey of roleKeys) {
      const checked = [...document.querySelectorAll(`.perm-checkbox[data-role="${roleKey}"]:checked`)];
      const permissionKeys = checked.map((c) => c.dataset.permission);
      const res = await fetch(`/api/admin/roles/${roleKey}/permissions`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ permission_keys: permissionKeys }),
      });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(payload.error || `Lỗi khi lưu quyền cho vai trò "${roleKey}".`);
      }
    }
    msg.textContent = "Đã lưu thay đổi.";
  } catch (err) {
    msg.className = "msg error";
    msg.textContent = err.message || String(err);
  }
}

el("role-form").addEventListener("submit", submitRoleForm);
document.querySelector(".permission-matrix").addEventListener("click", handleRoleDelete);
el("permission-save").addEventListener("click", saveAllPermissions);
