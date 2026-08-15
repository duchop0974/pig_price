async function loadFarmSelect(selectId) {
  const res = await fetch("/api/farms");
  const farms = await res.json();
  const select = el("zone-farm-select");
  const current = selectId || select.value;
  if (!farms.length) {
    select.innerHTML = `<option value="" disabled selected>Chưa có trang trại nào</option>`;
    await loadZoneList();
    return;
  }
  select.innerHTML = farms
    .map((f) => `<option value="${f.id}">${f.code}${f.province ? " · " + f.province : ""}</option>`)
    .join("");
  if ([...select.options].some((o) => o.value === String(current))) select.value = current;
  await loadZoneList();
}

async function loadZoneList() {
  const farmId = el("zone-farm-select").value;
  const tbody = el("zone-list");
  if (!farmId) {
    tbody.innerHTML = "";
    return;
  }
  const res = await fetch(`/api/zones?farm_id=${encodeURIComponent(farmId)}`);
  const zones = await res.json();
  const canEdit = (window.CURRENT_USER_PERMISSIONS || []).includes("admin.farms.manage");
  tbody.innerHTML = zones.length
    ? zones
        .map(
          (z) => `<tr data-id="${z.id}">
        <td>${z.code}</td>
        <td>
          ${canEdit ? `<button type="button" class="btn btn-ghost btn-sm btn-zone-edit" data-id="${z.id}" data-code="${z.code}">Sửa</button>
          <button type="button" class="btn btn-ghost btn-sm btn-zone-delete" data-id="${z.id}">Xóa</button>` : ""}
        </td>
      </tr>`
        )
        .join("")
    : `<tr><td colspan="2" class="msg">Trang trại này chưa có khu nào.</td></tr>`;
}

async function submitFarmForm(e) {
  e.preventDefault();
  const msg = el("farm-msg");
  msg.className = "msg";
  msg.textContent = "Đang lưu...";
  const body = {
    code: el("new-farm-code").value,
    province: el("new-farm-province").value,
  };
  try {
    const res = await fetch("/api/admin/farms", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await res.json();
    if (!res.ok) {
      msg.className = "msg error";
      msg.textContent = payload.error || "Lỗi khi thêm trang trại.";
      return;
    }
    msg.textContent = "Đã thêm trang trại. Đang tải lại danh sách...";
    location.reload();
  } catch (err) {
    msg.className = "msg error";
    msg.textContent = "Lỗi khi thêm trang trại: " + err;
  }
}

async function handleFarmListClick(e) {
  const editBtn = e.target.closest(".btn-farm-edit");
  const delBtn = e.target.closest(".btn-farm-delete");

  if (editBtn) {
    const id = editBtn.dataset.id;
    const code = (prompt("Mã trang trại:", editBtn.dataset.code) || "").trim();
    if (!code) return;
    const province = (prompt("Tỉnh/thành:", editBtn.dataset.province) || "").trim();
    const res = await fetch(`/api/admin/farms/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, province }),
    });
    const payload = await res.json();
    if (!res.ok) {
      alert(payload.error || "Lỗi khi sửa trang trại.");
      return;
    }
    location.reload();
  } else if (delBtn) {
    if (!confirm("Xóa trang trại này? (chỉ xóa được nếu chưa có kế hoạch nào dùng, sẽ xóa luôn các khu bên trong)")) return;
    const res = await fetch(`/api/admin/farms/${delBtn.dataset.id}`, { method: "DELETE" });
    const payload = await res.json();
    if (!res.ok) {
      alert(payload.error || "Lỗi khi xóa trang trại.");
      return;
    }
    location.reload();
  }
}

async function submitZoneForm(e) {
  e.preventDefault();
  const farmId = el("zone-farm-select").value;
  const msg = el("zone-msg");
  msg.className = "msg";
  if (!farmId) {
    msg.className = "msg error";
    msg.textContent = "Vui lòng chọn trang trại.";
    return;
  }
  msg.textContent = "Đang lưu...";
  try {
    const res = await fetch("/api/admin/zones", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ farm_id: Number(farmId), code: el("new-zone-code").value }),
    });
    const payload = await res.json();
    if (!res.ok) {
      msg.className = "msg error";
      msg.textContent = payload.error || "Lỗi khi thêm khu.";
      return;
    }
    msg.textContent = "Đã thêm khu.";
    el("new-zone-code").value = "";
    await loadZoneList();
  } catch (err) {
    msg.className = "msg error";
    msg.textContent = "Lỗi khi thêm khu: " + err;
  }
}

async function handleZoneListClick(e) {
  const editBtn = e.target.closest(".btn-zone-edit");
  const delBtn = e.target.closest(".btn-zone-delete");

  if (editBtn) {
    const code = (prompt("Tên khu:", editBtn.dataset.code) || "").trim();
    if (!code) return;
    const res = await fetch(`/api/admin/zones/${editBtn.dataset.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });
    const payload = await res.json();
    if (!res.ok) {
      alert(payload.error || "Lỗi khi sửa khu.");
      return;
    }
    await loadZoneList();
  } else if (delBtn) {
    if (!confirm("Xóa khu này? (chỉ xóa được nếu chưa có kế hoạch nào dùng)")) return;
    const res = await fetch(`/api/admin/zones/${delBtn.dataset.id}`, { method: "DELETE" });
    const payload = await res.json();
    if (!res.ok) {
      alert(payload.error || "Lỗi khi xóa khu.");
      return;
    }
    await loadZoneList();
  }
}

// vai trò leadership không có form thêm/sửa — el() trả null, không gắn listener
if (el("farm-form")) el("farm-form").addEventListener("submit", submitFarmForm);
el("farm-list").addEventListener("click", handleFarmListClick);
if (el("zone-form")) el("zone-form").addEventListener("submit", submitZoneForm);
el("zone-list").addEventListener("click", handleZoneListClick);
el("zone-farm-select").addEventListener("change", loadZoneList);

loadFarmSelect();
