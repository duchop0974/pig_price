"""Web app xem & so sánh giá heo hơi trên điện thoại/trình duyệt."""
import os
import secrets
import sys
import threading
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
import pig_sources as src  # noqa: E402

DB_PATH = BASE_DIR / "data" / "gia_heo_hoi.db"

PASSWORD_FILE = Path(__file__).resolve().parent / "password.txt"
ACCESS_LOG_PATH = Path(__file__).resolve().parent / "access.log"


def get_or_create_password() -> str:
    if PASSWORD_FILE.exists():
        return PASSWORD_FILE.read_text(encoding="utf-8").strip()
    password = secrets.token_urlsafe(6)
    PASSWORD_FILE.write_text(password, encoding="utf-8")
    return password


APP_PASSWORD = get_or_create_password()

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
# Cloudflare Tunnel gửi IP thật của khách qua header X-Forwarded-For; nếu
# không có ProxyFix thì request.remote_addr luôn chỉ thấy 127.0.0.1.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
db_lock = threading.Lock()

_refresh_state = {"last_run": None}
REFRESH_COOLDOWN = timedelta(minutes=1)

PUBLIC_ENDPOINTS = {"login", "static"}


def log_access(event: str) -> None:
    line = f"{datetime.now():%d/%m/%Y %H:%M:%S} - {request.remote_addr} - {event} - {request.path}\n"
    try:
        with open(ACCESS_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


@app.before_request
def require_login():
    if request.endpoint in ("index", "login"):
        log_access("truy cập" if session.get("authed") else "chưa đăng nhập")
    if request.endpoint in PUBLIC_ENDPOINTS:
        return
    if not session.get("authed"):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Chưa đăng nhập."}), 401
        return redirect(url_for("login", next=request.path))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        entered = request.form.get("password", "")
        if secrets.compare_digest(entered, APP_PASSWORD):
            session["authed"] = True
            log_access("đăng nhập thành công")
            return redirect(request.args.get("next") or url_for("index"))
        error = "Sai mật khẩu."
        log_access("đăng nhập SAI mật khẩu")
    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("authed", None)
    return redirect(url_for("login"))


def load_df() -> pd.DataFrame:
    with db_lock:
        return src.load_records_df(DB_PATH)


def save_records_locked(records: list[dict]) -> None:
    with db_lock:
        src.save_records(records, DB_PATH)


def create_plan_locked(plan: dict, ip: str | None) -> int:
    with db_lock:
        return src.create_sale_plan(plan, DB_PATH, ip)


def get_plan_locked(plan_id: int) -> dict | None:
    with db_lock:
        return src.get_sale_plan(plan_id, DB_PATH)


def list_plans_locked() -> list[dict]:
    with db_lock:
        return src.list_sale_plans(DB_PATH)


def update_plan_status_locked(plan_id: int, status: str, ip: str | None) -> None:
    with db_lock:
        src.update_sale_plan_status(plan_id, status, DB_PATH, ip)


def delete_plan_locked(plan_id: int) -> None:
    with db_lock:
        src.delete_sale_plan(plan_id, DB_PATH)


def list_farms_locked() -> list[str]:
    with db_lock:
        return src.list_farms(DB_PATH)


def create_farm_locked(code: str) -> None:
    with db_lock:
        src.create_farm(code, DB_PATH)


def list_zones_locked(farm: str) -> list[str]:
    with db_lock:
        return src.list_zones(farm, DB_PATH)


def create_zone_locked(farm: str, code: str) -> None:
    with db_lock:
        src.create_zone(farm, code, DB_PATH)


def latest_date_in(df: pd.DataFrame) -> str | None:
    if df.empty:
        return None
    sort_key = pd.to_datetime(df["date"], format="%d/%m/%Y")
    return df.loc[sort_key.idxmax(), "date"]


def payload_from_subset(
    subset: pd.DataFrame,
    label_date: str | None,
    mode: str,
    region_map: dict[str, str] | None = None,
) -> dict:
    if subset is None or subset.empty:
        return {
            "date": label_date,
            "mode": mode,
            "sources": {},
            "rows": [],
            "source_order": src.SOURCE_ORDER,
            "regions": src.REGION_BUCKETS,
        }

    region_map = region_map or {}
    records = subset.to_dict(orient="records")
    dates = src.dates_by_source(records)
    table = src.build_comparison_table(records)

    rows = []
    for province, row in table.iterrows():
        rows.append(
            {
                "province": province,
                "region": region_map.get(src.normalize_province(province)),
                "prices": {
                    col: (None if pd.isna(val) else val) for col, val in row.items()
                },
            }
        )

    return {
        "date": label_date,
        "mode": mode,
        "sources": dates,
        "rows": rows,
        "source_order": src.SOURCE_ORDER,
        "regions": src.REGION_BUCKETS,
    }


def dmy_to_iso(date_str: str) -> str:
    d, m, y = date_str.split("/")
    return f"{y}-{m}-{d}"


def iso_to_dmy(iso_date: str) -> str:
    y, m, d = iso_date.split("-")
    return f"{d}/{m}/{y}"


def current_national_price(df: pd.DataFrame) -> dict:
    """Giá heo hơi hiện tại (trung bình cả nước, mọi nguồn), lấy theo ngày
    gần nhất có dữ liệu — dùng làm mốc so sánh chung cho các kế hoạch xuất
    bán vì kế hoạch không gắn với 1 tỉnh/thành cụ thể."""
    if df.empty:
        return {"price": None, "date": None}
    sort_key = pd.to_datetime(df["date"], format="%d/%m/%Y")
    latest_date = df.loc[sort_key.idxmax(), "date"]
    prices = df.loc[df["date"] == latest_date, "price_vnd_per_kg"].dropna()
    avg_price = round(prices.mean()) if not prices.empty else None
    return {"price": avg_price, "date": latest_date}


def plan_payload(plan: dict, cur: dict) -> dict:
    reached = cur["price"] is not None and cur["price"] >= plan["target_price"]
    try:
        days_left = (date.fromisoformat(plan["planned_date"]) - date.today()).days
    except ValueError:
        days_left = None
    return {
        **plan,
        "current_price": cur["price"],
        "current_price_date": cur["date"],
        "reached_target": reached,
        "days_left": days_left,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/ke-hoach")
def plans_page():
    return render_template("plans.html")


@app.route("/api/today")
def api_today():
    """Chỉ đọc cache, không fetch live. Chỉ hiện đúng 1 ngày gần nhất có
    dữ liệu — nguồn nào chưa cập nhật ngày đó sẽ hiện "không có dữ liệu"
    thay vì lộ ra giá cũ của ngày khác dễ gây hiểu nhầm là giá hiện tại."""
    df = load_df()
    label_date = latest_date_in(df)
    subset = df[df["date"] == label_date] if label_date else df
    region_map = src.build_province_region_map(df)
    return jsonify(payload_from_subset(subset, label_date, mode="exact_date", region_map=region_map))


@app.route("/api/date/<iso_date>")
def api_date(iso_date: str):
    try:
        date_str = iso_to_dmy(iso_date)
        datetime.strptime(date_str, "%d/%m/%Y")
    except ValueError:
        return jsonify({"error": "Ngày không hợp lệ, dùng định dạng YYYY-MM-DD"}), 400

    df = load_df()
    if df.empty or date_str not in set(df["date"]):
        records = src.fetch_by_date_all(date_str)
        if records:
            save_records_locked(records)
            df = load_df()

    subset = df[df["date"] == date_str] if not df.empty else df
    region_map = src.build_province_region_map(df)
    return jsonify(payload_from_subset(subset, date_str, mode="exact_date", region_map=region_map))


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    now = datetime.now()
    last = _refresh_state["last_run"]
    if last and now - last < REFRESH_COOLDOWN:
        wait_seconds = int((REFRESH_COOLDOWN - (now - last)).total_seconds()) + 1
        return jsonify(
            {"error": f"Vui lòng đợi thêm {wait_seconds} giây trước khi cập nhật lại."}
        ), 429

    today_str = now.strftime("%d/%m/%Y")
    records = src.fetch_by_date_all(today_str)
    if records:
        save_records_locked(records)
    _refresh_state["last_run"] = now

    df = load_df()
    subset = df[df["date"] == today_str] if not df.empty else df
    region_map = src.build_province_region_map(df)
    return jsonify(payload_from_subset(subset, today_str, mode="exact_date", region_map=region_map))


@app.route("/api/provinces")
def api_provinces():
    df = load_df()
    if df.empty:
        return jsonify([])
    df = df.copy()
    df["_key"] = df["province"].map(src.normalize_province)
    display = df.drop_duplicates("_key")[["_key", "province"]]
    result = sorted(display["province"].tolist(), key=lambda s: src.normalize_province(s))
    return jsonify(result)


@app.route("/api/history")
def api_history():
    province = request.args.get("province", "")
    days = int(request.args.get("days", 90))

    df = load_df()
    if df.empty:
        return jsonify({"points": []})

    df = df.copy()
    df["_date_sort"] = pd.to_datetime(df["date"], format="%d/%m/%Y")
    df["_key"] = df["province"].map(src.normalize_province)

    if province:
        df = df[df["_key"] == src.normalize_province(province)]

    cutoff = df["_date_sort"].max() - timedelta(days=days)
    df = df[df["_date_sort"] >= cutoff]
    df = df.sort_values("_date_sort")

    points = [
        {
            "date": row["date"],
            "source": row["source"],
            "province": row["province"],
            "price": row["price_vnd_per_kg"],
        }
        for _, row in df.iterrows()
    ]
    return jsonify({"points": points, "source_order": src.SOURCE_ORDER})


@app.route("/api/farms", methods=["GET"])
def api_farms_list():
    return jsonify(list_farms_locked())


@app.route("/api/farms", methods=["POST"])
def api_farms_create():
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()
    if not code:
        return jsonify({"error": "Vui lòng nhập mã trang trại."}), 400
    if len(code) > 30:
        return jsonify({"error": "Mã trang trại quá dài."}), 400
    create_farm_locked(code)
    return jsonify(list_farms_locked()), 201


@app.route("/api/zones", methods=["GET"])
def api_zones_list():
    farm = (request.args.get("farm") or "").strip()
    if not farm:
        return jsonify([])
    return jsonify(list_zones_locked(farm))


@app.route("/api/zones", methods=["POST"])
def api_zones_create():
    data = request.get_json(silent=True) or {}
    farm = (data.get("farm") or "").strip()
    code = (data.get("code") or "").strip()
    if not farm:
        return jsonify({"error": "Thiếu trang trại."}), 400
    if not code:
        return jsonify({"error": "Vui lòng nhập tên khu."}), 400
    if len(code) > 30:
        return jsonify({"error": "Tên khu quá dài."}), 400
    create_zone_locked(farm, code)
    return jsonify(list_zones_locked(farm)), 201


@app.route("/api/plans", methods=["GET"])
def api_plans_list():
    df = load_df()
    cur = current_national_price(df)
    plans = list_plans_locked()
    return jsonify([plan_payload(p, cur) for p in plans])


@app.route("/api/plans", methods=["POST"])
def api_plans_create():
    data = request.get_json(silent=True) or {}
    planned_date = data.get("planned_date", "")
    farm = (data.get("farm") or "").strip()
    zone = (data.get("zone") or "").strip()
    note = (data.get("note") or "").strip() or None

    if not farm:
        return jsonify({"error": "Vui lòng chọn trang trại."}), 400
    if not zone:
        return jsonify({"error": "Vui lòng chọn khu."}), 400
    try:
        date.fromisoformat(planned_date)
    except (TypeError, ValueError):
        return jsonify({"error": "Ngày dự kiến không hợp lệ."}), 400
    try:
        quantity = int(data.get("quantity"))
        target_price = int(data.get("target_price"))
        if quantity <= 0 or target_price <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "Số lượng hoặc giá mong muốn không hợp lệ."}), 400

    plan_id = create_plan_locked(
        {
            "planned_date": planned_date,
            "farm": farm,
            "zone": zone,
            "quantity": quantity,
            "target_price": target_price,
            "note": note,
        },
        request.remote_addr,
    )
    df = load_df()
    cur = current_national_price(df)
    plan = get_plan_locked(plan_id)
    return jsonify(plan_payload(plan, cur)), 201


@app.route("/api/plans/<int:plan_id>", methods=["PATCH"])
def api_plans_update(plan_id: int):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in ("active", "done", "cancelled"):
        return jsonify({"error": "Trạng thái không hợp lệ."}), 400
    if get_plan_locked(plan_id) is None:
        return jsonify({"error": "Không tìm thấy kế hoạch."}), 404
    update_plan_status_locked(plan_id, status, request.remote_addr)
    return jsonify({"ok": True})


@app.route("/api/plans/<int:plan_id>", methods=["DELETE"])
def api_plans_delete(plan_id: int):
    if get_plan_locked(plan_id) is None:
        return jsonify({"error": "Không tìm thấy kế hoạch."}), 404
    delete_plan_locked(plan_id)
    return jsonify({"ok": True})


@app.route("/api/plans/export.xlsx")
def export_plans_excel():
    buffer = BytesIO()
    with db_lock:
        try:
            src.export_sale_plans_to_excel(DB_PATH, buffer)
        except ValueError as e:
            return jsonify({"error": str(e)}), 404
    buffer.seek(0)
    filename = f"ke_hoach_xuat_ban_{datetime.now():%Y%m%d}.xlsx"
    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


@app.route("/api/export.xlsx")
def export_excel():
    buffer = BytesIO()
    with db_lock:
        try:
            src.export_to_excel(DB_PATH, buffer)
        except ValueError as e:
            return jsonify({"error": str(e)}), 404
    buffer.seek(0)
    filename = f"gia_heo_hoi_{datetime.now():%Y%m%d}.xlsx"
    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


def start_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler

    def daily_job():
        print("[scheduler] Đang tự động cập nhật giá heo hơi hàng ngày...")
        records = src.fetch_latest_all()
        if records:
            save_records_locked(records)
        _refresh_state["last_run"] = datetime.now()

    scheduler = BackgroundScheduler()
    scheduler.add_job(daily_job, "cron", hour=7, minute=0)
    scheduler.start()
    return scheduler


if __name__ == "__main__":
    if sys.stdout is None or sys.stderr is None:
        # Chạy qua pythonw.exe (không có console): sys.stdout/sys.stderr là None,
        # print() sẽ crash ngay nếu không chuyển hướng ra file log trước.
        log_path = Path(__file__).resolve().parent / "server.log"
        log_file = open(log_path, "a", encoding="utf-8", buffering=1)
        sys.stdout = log_file
        sys.stderr = log_file
    elif sys.stdout.encoding is None or sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    print("=" * 50)
    print(f"Mật khẩu đăng nhập: {APP_PASSWORD}")
    print(f"(lưu tại {PASSWORD_FILE}, sửa file này để đổi mật khẩu)")
    print("=" * 50)
    start_scheduler()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
