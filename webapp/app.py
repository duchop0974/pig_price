"""Web app xem & so sánh giá heo hơi trên điện thoại/trình duyệt."""
import secrets
import sys
import threading
from datetime import datetime, timedelta
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


def latest_date_in(df: pd.DataFrame) -> str | None:
    if df.empty:
        return None
    sort_key = pd.to_datetime(df["date"], format="%d/%m/%Y")
    return df.loc[sort_key.idxmax(), "date"]


def payload_from_subset(subset: pd.DataFrame, label_date: str | None, mode: str) -> dict:
    if subset is None or subset.empty:
        return {
            "date": label_date,
            "mode": mode,
            "sources": {},
            "rows": [],
            "source_order": src.SOURCE_ORDER,
        }

    records = subset.to_dict(orient="records")
    dates = src.dates_by_source(records)
    table = src.build_comparison_table(records)

    rows = []
    for province, row in table.iterrows():
        rows.append(
            {
                "province": province,
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
    }


def dmy_to_iso(date_str: str) -> str:
    d, m, y = date_str.split("/")
    return f"{y}-{m}-{d}"


def iso_to_dmy(iso_date: str) -> str:
    y, m, d = iso_date.split("-")
    return f"{d}/{m}/{y}"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/today")
def api_today():
    """Chỉ đọc cache, không fetch live. Chỉ hiện đúng 1 ngày gần nhất có
    dữ liệu — nguồn nào chưa cập nhật ngày đó sẽ hiện "không có dữ liệu"
    thay vì lộ ra giá cũ của ngày khác dễ gây hiểu nhầm là giá hiện tại."""
    df = load_df()
    label_date = latest_date_in(df)
    subset = df[df["date"] == label_date] if label_date else df
    return jsonify(payload_from_subset(subset, label_date, mode="exact_date"))


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
    return jsonify(payload_from_subset(subset, date_str, mode="exact_date"))


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
    return jsonify(payload_from_subset(subset, today_str, mode="exact_date"))


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
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
