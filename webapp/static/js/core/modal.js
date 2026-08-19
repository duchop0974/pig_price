// confirmModal({title, body, consequence, confirmLabel, cancelLabel}) — trả
// về Promise<boolean>, thay thế cho window.confirm() ở các thao tác quan
// trọng (Freeze, Reject, Delete...). Dựng trên .modal-overlay/.modal-box
// sẵn có + class .confirm-modal mới. Chưa page nào gọi ở Phase 0.
function confirmModal({ title, body, consequence, confirmLabel, cancelLabel } = {}) {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay confirm-modal";
    overlay.innerHTML = `
      <div class="modal-box" role="dialog" aria-modal="true">
        <h3 class="confirm-modal-title">${title || "Xác nhận"}</h3>
        ${body ? `<p class="confirm-modal-body">${body}</p>` : ""}
        ${consequence ? `<p class="confirm-modal-consequence">${consequence}</p>` : ""}
        <div class="confirm-modal-actions">
          <button type="button" class="btn btn-ghost" data-action="cancel">${cancelLabel || "Huỷ"}</button>
          <button type="button" class="btn btn-danger" data-action="confirm">${confirmLabel || "Xác nhận"}</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);

    function close(result) {
      overlay.remove();
      resolve(result);
    }
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close(false);
    });
    overlay.querySelector('[data-action="cancel"]').addEventListener("click", () => close(false));
    overlay.querySelector('[data-action="confirm"]').addEventListener("click", () => close(true));
  });
}

// promptModal({title, label, initialValue, inputType, required, confirmLabel, cancelLabel})
// — trả về Promise<string|null> (null nếu huỷ, hoặc để trống khi required),
// thay thế window.prompt() cho nhập liệu ngắn (lý do từ chối, số lượng...).
// Dùng lại .confirm-modal/.control-row sẵn có, không cần class CSS mới.
function promptModal({ title, label, initialValue, inputType, required, confirmLabel, cancelLabel } = {}) {
  return new Promise((resolve) => {
    const inputId = "prompt-modal-input-" + Math.random().toString(36).slice(2);
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay confirm-modal";
    overlay.innerHTML = `
      <div class="modal-box" role="dialog" aria-modal="true">
        <h3 class="confirm-modal-title">${title || "Nhập thông tin"}</h3>
        <div class="control-row">
          ${label ? `<label for="${inputId}">${label}</label>` : ""}
          <input id="${inputId}" type="${inputType || "text"}" value="${initialValue === undefined || initialValue === null ? "" : initialValue}">
        </div>
        <div class="confirm-modal-actions">
          <button type="button" class="btn btn-ghost" data-action="cancel">${cancelLabel || "Huỷ"}</button>
          <button type="button" class="btn btn-primary" data-action="confirm">${confirmLabel || "Xác nhận"}</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);

    const input = overlay.querySelector("input");
    input.focus();
    input.select();

    function close(result) {
      overlay.remove();
      resolve(result);
    }
    function tryConfirm() {
      const value = input.value.trim();
      if (required && !value) {
        input.focus();
        return;
      }
      close(value);
    }
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close(null);
    });
    overlay.querySelector('[data-action="cancel"]').addEventListener("click", () => close(null));
    overlay.querySelector('[data-action="confirm"]').addEventListener("click", tryConfirm);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        tryConfirm();
      } else if (e.key === "Escape") {
        close(null);
      }
    });
  });
}

// detailModal({title, bodyHtml, actionsHtml}) — modal ĐỌC (read-only) cho
// "Xem chi tiết" ở bảng Kế hoạch trại/Kế hoạch bán. Khác confirmModal/
// promptModal (action-oriented, body là 1 đoạn ngắn): box rộng hơn, bodyHtml
// là HTML tuỳ ý, có actionsHtml là action bar riêng — các nút trong đó vẫn
// dùng nguyên class hành động gốc (vd .plan-btn-approve) để
// handlePlanListClick/handleOrderListClick nhận diện y hệt lúc còn ở
// card/table row, không cần đổi gì ở logic dispatch.
// overlay._detailModalClose lưu lại hàm close ngay trên phần tử DOM — cho
// phép delegated click handler ở plan.js/allocation.js tự đóng modal trước
// khi xử lý 1 action bấm từ bên trong nó (bắt buộc — nếu không, modal hành
// động tĩnh như #reconcile-modal sẽ bị modal chi tiết này đè lên do đứng
// sau trong DOM order dù cùng z-index).
function detailModal({ title, bodyHtml, actionsHtml } = {}) {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay detail-modal";
  overlay.innerHTML = `
    <div class="modal-box" role="dialog" aria-modal="true">
      <div class="detail-modal-head">
        <h3 class="detail-modal-title">${title || ""}</h3>
        <button type="button" class="detail-modal-close" aria-label="Đóng">✕</button>
      </div>
      <div class="detail-modal-body">${bodyHtml || ""}</div>
      ${actionsHtml ? `<div class="detail-modal-actions">${actionsHtml}</div>` : ""}
    </div>`;
  document.body.appendChild(overlay);

  function close() {
    overlay.remove();
    document.removeEventListener("keydown", onKeydown);
  }
  function onKeydown(e) {
    if (e.key === "Escape") close();
  }
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) close();
  });
  overlay.querySelector(".detail-modal-close").addEventListener("click", close);
  document.addEventListener("keydown", onKeydown);

  overlay._detailModalClose = close;
  return { close, root: overlay };
}
