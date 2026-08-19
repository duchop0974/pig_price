// Thin fetch wrapper — chuẩn hoá parse JSON + xử lý lỗi non-2xx cho các
// trang sẽ migrate dần sang dùng api.get/post/put/delete thay vì fetch() rải rác.
// Chưa được page nào dùng ở Phase 0 — chỉ thêm hạ tầng.
const api = (() => {
  async function request(method, url, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(url, opts);
    let data = null;
    try {
      data = await res.json();
    } catch (e) {
      data = null;
    }
    if (!res.ok) {
      const message = (data && (data.error || data.message)) || `Lỗi ${res.status}`;
      const err = new Error(message);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  return {
    get: (url) => request("GET", url),
    post: (url, body) => request("POST", url, body),
    put: (url, body) => request("PUT", url, body),
    delete: (url, body) => request("DELETE", url, body),
  };
})();
