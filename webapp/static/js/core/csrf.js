// Monkey-patch fetch() toàn cục để tự thêm header CSRF (X-CSRFToken, đúng
// tên flask-wtf đọc mặc định) cho mọi request same-origin — nhờ vậy 66+ chỗ
// gọi fetch() rải rác ở plan.js/allocation.js/admin_*.js/... không cần sửa
// dòng nào. Nạp TRƯỚC core/api.js, không defer (xem base.html).
(() => {
  const meta = document.querySelector('meta[name="csrf-token"]');
  const token = meta ? meta.content : "";
  const originalFetch = window.fetch.bind(window);

  window.fetch = (input, init) => {
    let url;
    if (typeof input === "string") {
      url = input;
    } else if (input instanceof Request) {
      url = input.url;
    } else {
      url = "";
    }

    let isSameOrigin = false;
    try {
      isSameOrigin = new URL(url, location.href).origin === location.origin;
    } catch (e) {
      isSameOrigin = false;
    }

    if (!isSameOrigin || !token) {
      return originalFetch(input, init);
    }

    const opts = init ? { ...init } : {};
    const headers = new Headers(opts.headers || (input instanceof Request ? input.headers : undefined));
    headers.set("X-CSRFToken", token);
    opts.headers = headers;
    return originalFetch(input, opts);
  };
})();
