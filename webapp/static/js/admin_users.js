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
  const assignBtn = e.target.closest(".btn-assign-farms");
  const deleteBtn = e.target.closest(".btn-delete-user");

  if (deleteBtn) {
    const ok = await confirmModal({
      title: "Xoá vĩnh viễn tài khoản?",
      body: "Không thể hoàn tác.",
      confirmLabel: "Xoá vĩnh viễn",
    });
    if (!ok) return;
    const res = await fetch(`/api/admin/users/${deleteBtn.dataset.id}`, { method: "DELETE" });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      showToast(payload.error || "Lỗi khi xoá tài khoản.", "danger");
      return;
    }
    showToast("Đã xoá tài khoản.", "success");
    location.reload();
  } else if (toggleBtn) {
    const id = toggleBtn.dataset.id;
    const currentlyActive = toggleBtn.dataset.active === "1";
    const label = currentlyActive ? "khoá" : "mở lại";
    const ok = await confirmModal({ title: `Xác nhận ${label} tài khoản?`, confirmLabel: currentlyActive ? "Khoá" : "Mở lại" });
    if (!ok) return;
    const res = await fetch(`/api/admin/users/${id}/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: !currentlyActive }),
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      showToast(payload.error || "Lỗi khi cập nhật trạng thái.", "danger");
      return;
    }
    location.reload();
  } else if (resetBtn) {
    const id = resetBtn.dataset.id;
    const password = await promptModal({
      title: "Đặt lại mật khẩu",
      label: "Mật khẩu mới (tối thiểu 6 ký tự)",
      required: true,
    });
    if (password === null) return;
    const res = await fetch(`/api/admin/users/${id}/reset-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      showToast(payload.error || "Lỗi khi đặt lại mật khẩu.", "danger");
      return;
    }
    showToast("Đã đặt lại mật khẩu.", "success");
  } else if (assignBtn) {
    await openFarmAssignModal(assignBtn.dataset.id);
  }
}

async function handleRoleChange(e) {
  const select = e.target.closest(".role-select");
  if (!select) return;
  const id = select.dataset.id;
  const role = select.value;
  const previousValue = select.dataset.previousValue || role;
  const ok = await confirmModal({
    title: "Đổi vai trò tài khoản?",
    body: `Đổi vai trò tài khoản này thành "${select.options[select.selectedIndex].text}"?`,
    confirmLabel: "Đổi vai trò",
  });
  if (!ok) {
    select.value = previousValue;
    return;
  }
  const res = await fetch(`/api/admin/users/${id}/role`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role }),
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    showToast(payload.error || "Lỗi khi đổi vai trò.", "danger");
  }
  location.reload();
}

async function loadFarmsList(userId) {
  const span = document.querySelector(`.farms-list[data-id="${userId}"]`);
  if (!span) return;
  const res = await fetch(`/api/admin/users/${userId}/farms`);
  const farms = await res.json();
  span.textContent = farms.length ? farms.map((f) => f.code).join(", ") : "Chưa gán trại";
}

let farmAssignUserId = null;

async function openFarmAssignModal(userId) {
  farmAssignUserId = userId;
  const res = await fetch(`/api/admin/users/${userId}/farms`);
  const assigned = await res.json();
  const assignedIds = new Set(assigned.map((f) => f.id));
  const list = el("farm-assign-list");
  list.innerHTML = (window.ALL_FARMS || [])
    .map(
      (f) => `<label class="farm-assign-item">
        <input type="checkbox" value="${f.id}" ${assignedIds.has(f.id) ? "checked" : ""}>
        ${f.code}${f.province ? " · " + f.province : ""}
      </label>`
    )
    .join("");
  el("farm-assign-modal").classList.remove("hidden");
}

function closeFarmAssignModal() {
  farmAssignUserId = null;
  el("farm-assign-modal").classList.add("hidden");
}

async function saveFarmAssign() {
  const checked = [...el("farm-assign-list").querySelectorAll("input[type=checkbox]:checked")];
  const farmIds = checked.map((c) => Number(c.value));
  const res = await fetch(`/api/admin/users/${farmAssignUserId}/farms`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ farm_ids: farmIds }),
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    showToast(payload.error || "Lỗi khi gán trang trại.", "danger");
    return;
  }
  const userId = farmAssignUserId;
  closeFarmAssignModal();
  showToast("Đã gán trang trại.", "success");
  await loadFarmsList(userId);
}

el("user-form").addEventListener("submit", submitUserForm);
el("user-list").addEventListener("click", handleListClick);
el("user-list").addEventListener("change", handleRoleChange);
el("farm-assign-save").addEventListener("click", saveFarmAssign);
el("farm-assign-cancel").addEventListener("click", closeFarmAssignModal);

document.querySelectorAll(".farms-list").forEach((span) => loadFarmsList(span.dataset.id));
document.querySelectorAll(".role-select").forEach((select) => { select.dataset.previousValue = select.value; });
