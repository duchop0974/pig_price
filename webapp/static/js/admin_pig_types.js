async function submitPigTypeForm(e) {
  e.preventDefault();
  const msg = el("pig-type-msg");
  msg.className = "msg";
  msg.textContent = "Đang lưu...";
  const body = {
    code: el("new-pt-code").value,
    name: el("new-pt-name").value,
  };
  try {
    const res = await fetch("/api/admin/pig-types", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await res.json();
    if (!res.ok) {
      msg.className = "msg error";
      msg.textContent = payload.error || "Lỗi khi thêm loại heo.";
      return;
    }
    msg.textContent = "Đã thêm loại heo. Đang tải lại danh sách...";
    location.reload();
  } catch (err) {
    msg.className = "msg error";
    msg.textContent = "Lỗi khi thêm loại heo: " + err;
  }
}

async function handlePigTypeListClick(e) {
  const editBtn = e.target.closest(".btn-pt-edit");
  const toggleBtn = e.target.closest(".btn-pt-toggle");
  const delBtn = e.target.closest(".btn-pt-delete");

  if (editBtn) {
    const id = editBtn.dataset.id;
    const code = await promptModal({ title: "Sửa loại heo", label: "Mã", initialValue: editBtn.dataset.code, required: true });
    if (code === null) return;
    const name = await promptModal({ title: "Sửa loại heo", label: "Tên hiển thị", initialValue: editBtn.dataset.name, required: true });
    if (name === null) return;
    const res = await fetch(`/api/admin/pig-types/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, name }),
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      showToast(payload.error || "Lỗi khi sửa loại heo.", "danger");
      return;
    }
    showToast("Đã lưu loại heo.", "success");
    location.reload();
  } else if (toggleBtn) {
    const id = toggleBtn.dataset.id;
    const currentlyActive = toggleBtn.dataset.active === "1";
    const label = currentlyActive ? "khoá" : "mở lại";
    const ok = await confirmModal({ title: `Xác nhận ${label} loại heo?`, confirmLabel: currentlyActive ? "Khoá" : "Mở lại" });
    if (!ok) return;
    const res = await fetch(`/api/admin/pig-types/${id}/toggle`, {
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
  } else if (delBtn) {
    const ok = await confirmModal({
      title: "Xoá loại heo?",
      body: "Chỉ xoá được nếu chưa có kế hoạch nào dùng.",
      confirmLabel: "Xoá vĩnh viễn",
    });
    if (!ok) return;
    const res = await fetch(`/api/admin/pig-types/${delBtn.dataset.id}`, { method: "DELETE" });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      showToast(payload.error || "Lỗi khi xóa loại heo.", "danger");
      return;
    }
    showToast("Đã xoá loại heo.", "success");
    location.reload();
  }
}

// vai trò leadership không có form thêm — el() trả null, không gắn listener
if (el("pig-type-form")) el("pig-type-form").addEventListener("submit", submitPigTypeForm);
el("pig-type-list").addEventListener("click", handlePigTypeListClick);
