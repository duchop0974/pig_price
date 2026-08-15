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
  } else if (assignBtn) {
    await openFarmAssignModal(assignBtn.dataset.id);
  }
}

async function handleRoleChange(e) {
  const select = e.target.closest(".role-select");
  if (!select) return;
  const id = select.dataset.id;
  const role = select.value;
  if (!confirm(`Đổi vai trò tài khoản này thành "${select.options[select.selectedIndex].text}"?`)) {
    location.reload();
    return;
  }
  const res = await fetch(`/api/admin/users/${id}/role`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role }),
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    alert(payload.error || "Lỗi khi đổi vai trò.");
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
    alert(payload.error || "Lỗi khi gán trang trại.");
    return;
  }
  const userId = farmAssignUserId;
  closeFarmAssignModal();
  await loadFarmsList(userId);
}

el("user-form").addEventListener("submit", submitUserForm);
el("user-list").addEventListener("click", handleListClick);
el("user-list").addEventListener("change", handleRoleChange);
el("farm-assign-save").addEventListener("click", saveFarmAssign);
el("farm-assign-cancel").addEventListener("click", closeFarmAssignModal);

document.querySelectorAll(".farms-list").forEach((span) => loadFarmsList(span.dataset.id));
