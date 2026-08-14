"""Blueprint trang giá heo hơi + API liên quan."""
from datetime import datetime, timedelta
from io import BytesIO

import pandas as pd
from flask import Blueprint, jsonify, render_template, request, send_file

from core.scrapers.registry import REGION_BUCKETS, SOURCE_ORDER, fetch_by_date_all
from core.scrapers.utils import normalize_province
from core.services.price_service import build_comparison_table, build_province_region_map, dates_by_source
from data_access import export_prices_excel_locked, load_df, save_records_locked
from extensions import REFRESH_COOLDOWN, refresh_state

prices_bp = Blueprint("prices", __name__)


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
            "source_order": SOURCE_ORDER,
            "regions": REGION_BUCKETS,
        }

    region_map = region_map or {}
    records = subset.to_dict(orient="records")
    dates = dates_by_source(records)
    table = build_comparison_table(records)

    rows = []
    for province, row in table.iterrows():
        rows.append(
            {
                "province": province,
                "region": region_map.get(normalize_province(province)),
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
        "source_order": SOURCE_ORDER,
        "regions": REGION_BUCKETS,
    }


def dmy_to_iso(date_str: str) -> str:
    d, m, y = date_str.split("/")
    return f"{y}-{m}-{d}"


def iso_to_dmy(iso_date: str) -> str:
    y, m, d = iso_date.split("-")
    return f"{d}/{m}/{y}"


@prices_bp.route("/")
def index():
    return render_template("index.html")


@prices_bp.route("/api/today")
def api_today():
    """Chỉ đọc cache, không fetch live. Chỉ hiện đúng 1 ngày gần nhất có
    dữ liệu — nguồn nào chưa cập nhật ngày đó sẽ hiện "không có dữ liệu"
    thay vì lộ ra giá cũ của ngày khác dễ gây hiểu nhầm là giá hiện tại."""
    df = load_df()
    label_date = latest_date_in(df)
    subset = df[df["date"] == label_date] if label_date else df
    region_map = build_province_region_map(df)
    return jsonify(payload_from_subset(subset, label_date, mode="exact_date", region_map=region_map))


@prices_bp.route("/api/date/<iso_date>")
def api_date(iso_date: str):
    try:
        date_str = iso_to_dmy(iso_date)
        datetime.strptime(date_str, "%d/%m/%Y")
    except ValueError:
        return jsonify({"error": "Ngày không hợp lệ, dùng định dạng YYYY-MM-DD"}), 400

    df = load_df()
    if df.empty or date_str not in set(df["date"]):
        records = fetch_by_date_all(date_str)
        if records:
            save_records_locked(records)
            df = load_df()

    subset = df[df["date"] == date_str] if not df.empty else df
    region_map = build_province_region_map(df)
    return jsonify(payload_from_subset(subset, date_str, mode="exact_date", region_map=region_map))


@prices_bp.route("/api/refresh", methods=["POST"])
def api_refresh():
    now = datetime.now()
    last = refresh_state["last_run"]
    if last and now - last < REFRESH_COOLDOWN:
        wait_seconds = int((REFRESH_COOLDOWN - (now - last)).total_seconds()) + 1
        return jsonify(
            {"error": f"Vui lòng đợi thêm {wait_seconds} giây trước khi cập nhật lại."}
        ), 429

    today_str = now.strftime("%d/%m/%Y")
    records = fetch_by_date_all(today_str)
    if records:
        save_records_locked(records)
    refresh_state["last_run"] = now

    df = load_df()
    subset = df[df["date"] == today_str] if not df.empty else df
    region_map = build_province_region_map(df)
    return jsonify(payload_from_subset(subset, today_str, mode="exact_date", region_map=region_map))


@prices_bp.route("/api/provinces")
def api_provinces():
    df = load_df()
    if df.empty:
        return jsonify([])
    df = df.copy()
    df["_key"] = df["province"].map(normalize_province)
    display = df.drop_duplicates("_key")[["_key", "province"]]
    result = sorted(display["province"].tolist(), key=lambda s: normalize_province(s))
    return jsonify(result)


@prices_bp.route("/api/history")
def api_history():
    province = request.args.get("province", "")
    days = int(request.args.get("days", 90))

    df = load_df()
    if df.empty:
        return jsonify({"points": []})

    df = df.copy()
    df["_date_sort"] = pd.to_datetime(df["date"], format="%d/%m/%Y")
    df["_key"] = df["province"].map(normalize_province)

    if province:
        df = df[df["_key"] == normalize_province(province)]

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
    return jsonify({"points": points, "source_order": SOURCE_ORDER})


@prices_bp.route("/api/export.xlsx")
def export_excel():
    buffer = BytesIO()
    try:
        export_prices_excel_locked(buffer)
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
