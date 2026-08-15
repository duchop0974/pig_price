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

async function handleCustomerListClick(e) {
  const editBtn = e.target.closest(".btn-cus-edit");
  const toggleBtn = e.target.closest(".btn-cus-toggle");
  const delBtn = e.target.closest(".btn-cus-delete");

  if (editBtn) {
    const id = editBtn.dataset.id;
    const name = (prompt("Tên khách hàng:", editBtn.dataset.name) || "").trim();
    if (!name) return;
    const phone = prompt("Số điện thoại:", editBtn.dataset.phone) || "";
    const address = prompt("Địa chỉ:", editBtn.dataset.address) || "";
    const taxCode = prompt("Mã số thuế:", editBtn.dataset.taxCode) || "";
    const email = prompt("Email:", editBtn.dataset.email) || "";
    const contactPerson = prompt("Người liên hệ:", editBtn.dataset.contactPerson) || "";
    const contactTitle = prompt("Chức vụ người liên hệ:", editBtn.dataset.contactTitle) || "";
    const note = prompt("Ghi chú:", editBtn.dataset.note) || "";
    const res = await fetch(`/api/customers/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        phone,
        address,
        tax_code: taxCode,
        email,
        contact_person: contactPerson,
        contact_title: contactTitle,
        note,
      }),
    });
    const payload = await res.json();
    if (!res.ok) {
      alert(payload.error || "Lỗi khi sửa khách hàng.");
      return;
    }
    location.reload();
  } else if (toggleBtn) {
    const id = toggleBtn.dataset.id;
    const currentlyActive = toggleBtn.dataset.active === "1";
    const label = currentlyActive ? "khoá" : "mở lại";
    if (!confirm(`Xác nhận ${label} khách hàng này?`)) return;
    await fetch(`/api/customers/${id}/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: !currentlyActive }),
    });
    location.reload();
  } else if (delBtn) {
    if (!confirm("Xóa khách hàng này? (chỉ xóa được nếu chưa có kế hoạch nào dùng)")) return;
    const res = await fetch(`/api/customers/${delBtn.dataset.id}`, { method: "DELETE" });
    const payload = await res.json();
    if (!res.ok) {
      alert(payload.error || "Lỗi khi xóa khách hàng.");
      return;
    }
    location.reload();
  }
}

// vai trò leadership không có form thêm — el() trả null, không gắn listener
if (el("customer-form")) el("customer-form").addEventListener("submit", submitCustomerForm);
el("customer-list").addEventListener("click", handleCustomerListClick);
