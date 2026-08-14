"""Blueprint kế hoạch xuất bán + API liên quan (farms/zones/plans)."""
from datetime import date, datetime
from io import BytesIO

import pandas as pd
from flask import Blueprint, jsonify, render_template, request, send_file, session

from data_access import (
    create_farm_locked,
    create_plan_locked,
    create_zone_locked,
    delete_plan_locked,
    export_plans_excel_locked,
    get_plan_locked,
    list_farms_locked,
    list_plans_locked,
    list_zones_locked,
    load_df,
    update_plan_status_locked,
)
from extensions import log_audit

plans_bp = Blueprint("plans", __name__)


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


@plans_bp.route("/ke-hoach")
def plans_page():
    return render_template("plans.html")


@plans_bp.route("/api/farms", methods=["GET"])
def api_farms_list():
    return jsonify(list_farms_locked())


@plans_bp.route("/api/farms", methods=["POST"])
def api_farms_create():
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()
    if not code:
        return jsonify({"error": "Vui lòng nhập mã trang trại."}), 400
    if len(code) > 30:
        return jsonify({"error": "Mã trang trại quá dài."}), 400
    create_farm_locked(code)
    return jsonify(list_farms_locked()), 201


@plans_bp.route("/api/zones", methods=["GET"])
def api_zones_list():
    farm = (request.args.get("farm") or "").strip()
    if not farm:
        return jsonify([])
    return jsonify(list_zones_locked(farm))


@plans_bp.route("/api/zones", methods=["POST"])
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


@plans_bp.route("/api/plans", methods=["GET"])
def api_plans_list():
    df = load_df()
    cur = current_national_price(df)
    plans = list_plans_locked()
    return jsonify([plan_payload(p, cur) for p in plans])


@plans_bp.route("/api/plans", methods=["POST"])
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

    username = session["user"]["username"]
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
        username,
    )
    log_audit("tạo kế hoạch xuất bán", detail=f"plan_id={plan_id}, farm={farm}, zone={zone}")
    df = load_df()
    cur = current_national_price(df)
    plan = get_plan_locked(plan_id)
    return jsonify(plan_payload(plan, cur)), 201


@plans_bp.route("/api/plans/<int:plan_id>", methods=["PATCH"])
def api_plans_update(plan_id: int):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in ("active", "done", "cancelled"):
        return jsonify({"error": "Trạng thái không hợp lệ."}), 400
    if get_plan_locked(plan_id) is None:
        return jsonify({"error": "Không tìm thấy kế hoạch."}), 404
    username = session["user"]["username"]
    update_plan_status_locked(plan_id, status, request.remote_addr, username)
    log_audit("cập nhật kế hoạch xuất bán", detail=f"plan_id={plan_id}, status={status}")
    return jsonify({"ok": True})


@plans_bp.route("/api/plans/<int:plan_id>", methods=["DELETE"])
def api_plans_delete(plan_id: int):
    if get_plan_locked(plan_id) is None:
        return jsonify({"error": "Không tìm thấy kế hoạch."}), 404
    delete_plan_locked(plan_id)
    log_audit("xóa kế hoạch xuất bán", detail=f"plan_id={plan_id}")
    return jsonify({"ok": True})


@plans_bp.route("/api/plans/export.xlsx")
def export_plans_excel():
    buffer = BytesIO()
    try:
        export_plans_excel_locked(buffer)
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
