let editingCustomerId = null;

async function submitCustomerForm(e) {
  e.preventDefault();
  const msg = el("customer-msg");
  msg.className = "msg";
  msg.textContent = "Đang lưu...";
  const body = {
    name: el("new-cus-name").value,
    phone: el("new-cus-phone").value,
    address: el("new-cus-address").value,
    tax_code: el("new-cus-tax-code").value,
    email: el("new-cus-email").value,
    contact_person: el("new-cus-contact-person").value,
    contact_title: el("new-cus-contact-title").value,
    note: el("new-cus-note").value,
  };
  try {
    const res = await fetch("/api/customers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await res.json();
    if (!res.ok) {
      msg.className = "msg error";
      msg.textContent = payload.error || "Lỗi khi thêm khách hàng.";
      return;
    }
    msg.textContent = "Đã thêm khách hàng. Đang tải lại danh sách...";
    location.reload();
  } catch (err) {
    msg.className = "msg error";
    msg.textContent = "Lỗi khi thêm khách hàng: " + err;
  }
}

function openCustomerEditModal(btn) {
  editingCustomerId = btn.dataset.id;
  el("ce-name").value = btn.dataset.name;
  el("ce-phone").value = btn.dataset.phone;
  el("ce-address").value = btn.dataset.address;
  el("ce-tax-code").value = btn.dataset.taxCode;
  el("ce-email").value = btn.dataset.email;
  el("ce-contact-person").value = btn.dataset.contactPerson;
  el("ce-contact-title").value = btn.dataset.contactTitle;
  el("ce-note").value = btn.dataset.note;
  el("ce-msg").className = "msg";
  el("ce-msg").textContent = "";
  el("cus-edit-modal").classList.remove("hidden");
}

function closeCustomerEditModal() {
  editingCustomerId = null;
  el("cus-edit-modal").classList.add("hidden");
}

async function saveCustomerEdit() {
  const name = el("ce-name").value.trim();
  if (!name) {
    el("ce-msg").className = "msg error";
    el("ce-msg").textContent = "Vui lòng nhập tên khách hàng.";
    return;
  }
  const body = {
    name,
    phone: el("ce-phone").value,
    address: el("ce-address").value,
    tax_code: el("ce-tax-code").value,
    email: el("ce-email").value,
    contact_person: el("ce-contact-person").value,
    contact_title: el("ce-contact-title").value,
    note: el("ce-note").value,
  };
  const res = await fetch(`/api/customers/${editingCustomerId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) {
    el("ce-msg").className = "msg error";
    el("ce-msg").textContent = payload.error || "Lỗi khi sửa khách hàng.";
    return;
  }
  showToast("Đã lưu thông tin khách hàng.", "success");
  location.reload();
}

async function handleCustomerListClick(e) {
  const editBtn = e.target.closest(".btn-cus-edit");
  const toggleBtn = e.target.closest(".btn-cus-toggle");
  const delBtn = e.target.closest(".btn-cus-delete");

  if (editBtn) {
    openCustomerEditModal(editBtn);
  } else if (toggleBtn) {
    const id = toggleBtn.dataset.id;
    const currentlyActive = toggleBtn.dataset.active === "1";
    const label = currentlyActive ? "khoá" : "mở lại";
    const ok = await confirmModal({ title: `Xác nhận ${label} khách hàng?`, confirmLabel: currentlyActive ? "Khoá" : "Mở lại" });
    if (!ok) return;
    const res = await fetch(`/api/customers/${id}/toggle`, {
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
      title: "Xoá khách hàng?",
      body: "Chỉ xoá được nếu chưa có kế hoạch nào dùng khách hàng này.",
      confirmLabel: "Xoá vĩnh viễn",
    });
    if (!ok) return;
    const res = await fetch(`/api/customers/${delBtn.dataset.id}`, { method: "DELETE" });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      showToast(payload.error || "Lỗi khi xóa khách hàng.", "danger");
      return;
    }
    showToast("Đã xoá khách hàng.", "success");
    location.reload();
  }
}

// vai trò leadership không có form thêm — el() trả null, không gắn listener
if (el("customer-form")) el("customer-form").addEventListener("submit", submitCustomerForm);
el("customer-list").addEventListener("click", handleCustomerListClick);
if (el("ce-save")) el("ce-save").addEventListener("click", saveCustomerEdit);
if (el("ce-cancel")) el("ce-cancel").addEventListener("click", closeCustomerEditModal);
