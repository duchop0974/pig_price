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
    const code = (prompt("Mã loại heo:", editBtn.dataset.code) || "").trim();
    if (!code) return;
    const name = (prompt("Tên hiển thị:", editBtn.dataset.name) || "").trim();
    if (!name) return;
    const res = await fetch(`/api/admin/pig-types/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, name }),
    });
    const payload = await res.json();
    if (!res.ok) {
      alert(payload.error || "Lỗi khi sửa loại heo.");
      return;
    }
    location.reload();
  } else if (toggleBtn) {
    const id = toggleBtn.dataset.id;
    const currentlyActive = toggleBtn.dataset.active === "1";
    const label = currentlyActive ? "khoá" : "mở lại";
    if (!confirm(`Xác nhận ${label} loại heo này?`)) return;
    await fetch(`/api/admin/pig-types/${id}/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: !currentlyActive }),
    });
    location.reload();
  } else if (delBtn) {
    if (!confirm("Xóa loại heo này? (chỉ xóa được nếu chưa có kế hoạch nào dùng)")) return;
    const res = await fetch(`/api/admin/pig-types/${delBtn.dataset.id}`, { method: "DELETE" });
    const payload = await res.json();
    if (!res.ok) {
      alert(payload.error || "Lỗi khi xóa loại heo.");
      return;
    }
    location.reload();
  }
}

// vai trò leadership không có form thêm — el() trả null, không gắn listener
if (el("pig-type-form")) el("pig-type-form").addEventListener("submit", submitPigTypeForm);
el("pig-type-list").addEventListener("click", handlePigTypeListClick);
