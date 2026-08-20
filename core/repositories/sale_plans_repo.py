"""CRUD cho bảng sale_plans (kế hoạch trại — nguồn cung heo, BM01).

Kế hoạch bán (Phòng bán hàng "nhặt" số lượng/giá từ kế hoạch trại để bán cho
khách, BM02) nằm ở bảng/repo riêng: sale_orders_repo.py (đơn hàng + dòng
hàng, Giai đoạn 8 — 1 đơn có thể gồm nhiều dòng khác loại heo/kế hoạch trại)."""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from core.db import get_connection

# Trường hiển thị trên form/thẻ kế hoạch cho người dùng. created_by hiển thị
# để biết ai đã lập kế hoạch (phục vụ audit — nhiều người cùng dùng chung 1
# danh sách kế hoạch). farm/zone/pig_type là mã hiển thị lấy qua JOIN, không
# phải id nội bộ (farm_id/zone_id/pig_type_id) dùng để ghi/sửa dữ liệu.
# farm_id giữ lại (không chỉ mã hiển thị) để route /received kiểm tra kế
# hoạch có thuộc (các) trại user được gán hay không.
SALE_PLAN_VISIBLE_COLUMNS = [
    "id",
    "plan_code",
    "planned_date",
    "farm_id",
    "farm",
    "province",
    "zone_id",
    "zone",
    "shed",
    "lot",
    "pig_type_id",
    "pig_type",
    "pig_type_name",
    "quantity",
    "received_quantity",
    "received_at",
    "received_by",
    "allocated_quantity",
    "remaining_quantity",
    "actual_sold_quantity",
    "reconciled_quantity",
    "remaining_to_reconcile",
    "expected_avg_weight_kg",
    "planned_total_weight_kg",
    "actual_total_weight_kg",
    "weight_missing_delivery_count",
    "delivery_count",
    "last_delivered_date",
    "off_type_quantity",
    "note",
    "status",
    "created_by",
    "approved_by",
    "approved_at",
    "rejected_by",
    "rejected_at",
    "rejected_reason",
    "locked_at",
    "locked_by",
]

# Đầy đủ cả trường ẩn (created_at, created_ip, updated_at, updated_ip,
# updated_by) — dùng khi truy vết/đối soát hoặc xuất Excel cho quản lý,
# không hiển thị trên UI.
SALE_PLAN_ALL_COLUMNS = SALE_PLAN_VISIBLE_COLUMNS + [
    "created_at",
    "created_ip",
    "updated_at",
    "updated_ip",
    "updated_by",
]

_JOIN_SQL = """
    FROM sale_plans sp
    JOIN farms f ON f.id = sp.farm_id
    LEFT JOIN zones z ON z.id = sp.zone_id
    LEFT JOIN pig_types pt ON pt.id = sp.pig_type_id
"""

# allocated_quantity = tổng quantity của các dòng hàng thuộc đơn đang
# active/done tham chiếu tới kế hoạch trại này; remaining_quantity = quantity
# trại đăng ký - allocated_quantity. Tính động (subquery), không lưu cột
# riêng để tránh lệch dữ liệu khi đơn bị huỷ/vô hiệu hoá. Từ Giai đoạn 8,
# trạng thái nằm ở đơn hàng (sale_orders), không còn ở từng dòng
# (sale_allocations) nữa — phải JOIN qua order_id.
_ALLOCATED_SQL = (
    "COALESCE((SELECT SUM(sa.quantity) FROM sale_allocations sa "
    "JOIN sale_orders so ON so.id = sa.order_id "
    "WHERE sa.sale_plan_id = sp.id AND so.status IN ('active','done')), 0)"
)

# Bộ lọc đơn dùng chung cho MỌI rollup từ sale_deliveries — cố ý TRÙNG
# _ALLOCATED_SQL ('active','done') để allocated/actual không bao giờ nói về 2
# tập đơn khác nhau trên cùng 1 thẻ kế hoạch. KHÔNG dùng 'done' như bản trước:
# brief yêu cầu "1 kế hoạch xuất nhiều lần", tức việc xuất xảy ra khi đơn còn
# active — nếu chỉ đếm 'done' thì kế hoạch đã giao thật 80/100 vẫn hiện "Cần
# đối soát" cho cả 100. Đơn cancelled/disabled rơi khỏi cả hai; phần heo đã
# thật sự xuất trên đơn bị huỷ giải thích bằng sale_plan_reconciliations
# (kind='transferred'/'other'), không bằng cách nới bộ lọc này.
_DELIVERY_FROM_SQL = (
    "FROM sale_deliveries sd "
    "JOIN sale_allocations sa ON sa.id = sd.allocation_id "
    "JOIN sale_orders so ON so.id = sa.order_id "
    "WHERE sa.sale_plan_id = sp.id AND so.status IN ('active','done')"
)

# actual_sold_quantity = tổng số con ĐÃ XUẤT GIAO thực tế (nguồn:
# sale_deliveries — xem sale_deliveries_repo.py), KHÁC allocated_quantity (chỉ
# là số đã "nhặt" vào đơn, có thể chưa giao).
_ACTUAL_SOLD_SQL = f"COALESCE((SELECT SUM(sd.quantity) {_DELIVERY_FROM_SQL}), 0)"

# Trọng lượng: CỐ Ý không COALESCE về 0 (khác 3 field số lượng ở trên). NULL =
# "chưa nhập cân", 0 = "đã nhập và bằng 0" — gộp 2 nghĩa này lại sẽ khiến mọi
# kế hoạch chưa ai gõ cân hiện lệch -100% trên thẻ.
_PLANNED_WEIGHT_SQL = (
    "CASE WHEN sp.expected_avg_weight_kg IS NULL THEN NULL "
    "ELSE sp.quantity * sp.expected_avg_weight_kg END"
)
_ACTUAL_WEIGHT_SQL = f"(SELECT SUM(sd.total_weight_kg) {_DELIVERY_FROM_SQL})"
_WEIGHT_MISSING_SQL = f"COALESCE((SELECT COUNT(*) {_DELIVERY_FROM_SQL} AND sd.total_weight_kg IS NULL), 0)"
_DELIVERY_COUNT_SQL = f"COALESCE((SELECT COUNT(*) {_DELIVERY_FROM_SQL}), 0)"
_LAST_DELIVERED_DATE_SQL = f"(SELECT MAX(sd.delivered_date) {_DELIVERY_FROM_SQL})"
# Số con đã xuất nhưng KHÁC loại heo kế hoạch — chỉ số "lệch cơ cấu" gọn nhất,
# dùng cho badge trên thẻ; chi tiết theo từng loại xem delivery_mix.
_OFF_TYPE_QUANTITY_SQL = (
    f"COALESCE((SELECT SUM(sd.quantity) {_DELIVERY_FROM_SQL} AND sd.pig_type_id <> sp.pig_type_id), 0)"
)

# reconciled_quantity = tổng quantity các bản ghi đối soát "chốt" (transferred/
# culled/cancelled/other) — CHỈ 4 kind này, không gồm still_at_farm/
# continue_selling (ghi nhận, không đóng kế hoạch — xem plan_reconciliation_repo.py).
_RECONCILED_SQL = (
    "COALESCE((SELECT SUM(pr.quantity) FROM sale_plan_reconciliations pr "
    "WHERE pr.sale_plan_id = sp.id AND pr.kind IN ('transferred','culled','cancelled','other')), 0)"
)

# remaining_to_reconcile = quantity - actual_sold_quantity - reconciled_quantity.
# Khác remaining_quantity (= quantity - allocated_quantity, chỉ xét đã "nhặt"
# vào đơn hay chưa): số này là số CHƯA được giải thích bằng bán thật hoặc lý
# do đối soát hợp lệ, kể cả khi đã "nhặt" vào 1 đơn active nhưng đơn đó chưa
# "Đã bán" (chưa có actual_quantity thật).
_REMAINING_TO_RECONCILE_SQL = f"sp.quantity - {_ACTUAL_SOLD_SQL} - {_RECONCILED_SQL}"

_SELECT_VISIBLE = (
    "SELECT sp.id, sp.plan_code, sp.planned_date, sp.farm_id, f.code AS farm, f.province AS province, "
    "sp.zone_id, z.code AS zone, sp.shed, sp.lot, sp.pig_type_id, pt.code AS pig_type, pt.name AS pig_type_name, sp.quantity, "
    "sp.received_quantity, sp.received_at, sp.received_by, "
    f"{_ALLOCATED_SQL} AS allocated_quantity, sp.quantity - {_ALLOCATED_SQL} AS remaining_quantity, "
    f"{_ACTUAL_SOLD_SQL} AS actual_sold_quantity, {_RECONCILED_SQL} AS reconciled_quantity, "
    f"{_REMAINING_TO_RECONCILE_SQL} AS remaining_to_reconcile, "
    f"sp.expected_avg_weight_kg, {_PLANNED_WEIGHT_SQL} AS planned_total_weight_kg, "
    f"{_ACTUAL_WEIGHT_SQL} AS actual_total_weight_kg, "
    f"{_WEIGHT_MISSING_SQL} AS weight_missing_delivery_count, "
    f"{_DELIVERY_COUNT_SQL} AS delivery_count, {_LAST_DELIVERED_DATE_SQL} AS last_delivered_date, "
    f"{_OFF_TYPE_QUANTITY_SQL} AS off_type_quantity, "
    "sp.note, sp.status, sp.created_by, "
    "sp.approved_by, sp.approved_at, sp.rejected_by, sp.rejected_at, sp.rejected_reason, "
    "sp.locked_at, sp.locked_by"
    + _JOIN_SQL
)

_SELECT_ALL = (
    "SELECT sp.id, sp.plan_code, sp.planned_date, sp.farm_id, f.code AS farm, f.province AS province, "
    "sp.zone_id, z.code AS zone, sp.shed, sp.lot, sp.pig_type_id, pt.code AS pig_type, pt.name AS pig_type_name, sp.quantity, "
    "sp.received_quantity, sp.received_at, sp.received_by, "
    f"{_ALLOCATED_SQL} AS allocated_quantity, sp.quantity - {_ALLOCATED_SQL} AS remaining_quantity, "
    f"{_ACTUAL_SOLD_SQL} AS actual_sold_quantity, {_RECONCILED_SQL} AS reconciled_quantity, "
    f"{_REMAINING_TO_RECONCILE_SQL} AS remaining_to_reconcile, "
    f"sp.expected_avg_weight_kg, {_PLANNED_WEIGHT_SQL} AS planned_total_weight_kg, "
    f"{_ACTUAL_WEIGHT_SQL} AS actual_total_weight_kg, "
    f"{_WEIGHT_MISSING_SQL} AS weight_missing_delivery_count, "
    f"{_DELIVERY_COUNT_SQL} AS delivery_count, {_LAST_DELIVERED_DATE_SQL} AS last_delivered_date, "
    f"{_OFF_TYPE_QUANTITY_SQL} AS off_type_quantity, "
    "sp.note, sp.status, sp.created_by, "
    "sp.approved_by, sp.approved_at, sp.rejected_by, sp.rejected_at, sp.rejected_reason, "
    "sp.locked_at, sp.locked_by, "
    "sp.created_at, sp.created_ip, sp.updated_at, sp.updated_ip, sp.updated_by"
    + _JOIN_SQL
)


def _apply_reconciliation_status(row: dict) -> dict:
    """Gắn reconciliation_status (tính động, KHÔNG lưu DB, KHÔNG đụng
    sale_plans.status) — chỉ có ý nghĩa khi kế hoạch đã 'approved':
    'reconciled' (đã giải thích hết), 'needs_reconciliation' (còn chênh
    lệch VÀ đã quá ngày dự kiến — tránh báo động khi vẫn còn hạn bán bình
    thường), 'in_progress' (còn chênh lệch nhưng vẫn còn hạn)."""
    remaining = row.get("remaining_to_reconcile") or 0
    # Xuất DƯ so với kế hoạch (VD giao 120 con cho kế hoạch 100) — phải kiểm
    # TRƯỚC nhánh <= 0, nếu không remaining = -20 sẽ lọt vào "reconciled" và
    # hiện badge xanh "Đã đối soát" cho đúng tình huống cần cảnh báo nhất.
    row["over_delivered"] = remaining < 0
    if row.get("status") != "approved":
        row["reconciliation_status"] = None
        return row
    if row["over_delivered"]:
        row["reconciliation_status"] = "over_delivered"
    elif remaining <= 0:
        row["reconciliation_status"] = "reconciled"
    else:
        today = datetime.now().strftime("%Y-%m-%d")
        overdue = (row.get("planned_date") or "") < today
        row["reconciliation_status"] = "needs_reconciliation" if overdue else "in_progress"
    return row


def _reconciliation_breakdown_map(conn: sqlite3.Connection, plan_ids: list[int]) -> dict[int, list[dict]]:
    """1 query duy nhất cho cả trang (tránh N+1) — group theo kind, dùng để
    hiển thị breakdown kiểu 'Đã loại 3 / Khách hủy 3' trên thẻ kế hoạch."""
    if not plan_ids:
        return {}
    placeholders = ", ".join("?" * len(plan_ids))
    rows = conn.execute(
        f"SELECT sale_plan_id, kind, SUM(quantity) AS quantity FROM sale_plan_reconciliations "
        f"WHERE sale_plan_id IN ({placeholders}) GROUP BY sale_plan_id, kind",
        tuple(plan_ids),
    ).fetchall()
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(r["sale_plan_id"], []).append({"kind": r["kind"], "quantity": r["quantity"]})
    return out


def _delivery_mix_map(conn: sqlite3.Connection, plan_ids: list[int]) -> dict[int, list[dict]]:
    """Cơ cấu loại heo THỰC TẾ đã xuất, gộp theo pig_type_id — 1 query cho cả
    trang (cùng khuôn _reconciliation_breakdown_map, tránh N+1).

    Bộ lọc đơn ('active','done') phải TRÙNG _DELIVERY_FROM_SQL, nếu không tổng
    của mix sẽ không khớp actual_sold_quantity trên cùng 1 thẻ. LEFT JOIN
    pig_types (không phải inner) để 1 loại heo lỡ bị xoá không làm rơi nguyên
    1 nhóm khiến tổng lệch — mix không cộng đúng là lỗi tệ nhất ở đây."""
    if not plan_ids:
        return {}
    placeholders = ", ".join("?" * len(plan_ids))
    rows = conn.execute(
        f"""
        SELECT sa.sale_plan_id            AS plan_id,
               sd.pig_type_id             AS pig_type_id,
               pt.code                    AS pig_type,
               pt.name                    AS pig_type_name,
               SUM(sd.quantity)           AS quantity,
               SUM(sd.total_weight_kg)    AS total_weight_kg,
               COUNT(*)                   AS delivery_count,
               MIN(sd.delivered_date)     AS first_delivered_date,
               MAX(sd.delivered_date)     AS last_delivered_date,
               SUM(CASE WHEN sd.created_by = 'system:backfill' THEN 1 ELSE 0 END) AS backfilled_count
        FROM sale_deliveries sd
        JOIN sale_allocations sa ON sa.id = sd.allocation_id
        JOIN sale_orders so      ON so.id = sa.order_id
        LEFT JOIN pig_types pt   ON pt.id = sd.pig_type_id
        WHERE sa.sale_plan_id IN ({placeholders})
          AND so.status IN ('active','done')
        GROUP BY sa.sale_plan_id, sd.pig_type_id
        ORDER BY quantity DESC
        """,
        tuple(plan_ids),
    ).fetchall()
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(r["plan_id"], []).append(dict(r))
    return out


def _apply_delivery_mix(row: dict, mix: list[dict]) -> dict:
    """So cơ cấu KẾ HOẠCH (luôn đúng 1 loại: loại của kế hoạch × quantity) với
    cơ cấu THỰC TẾ đã xuất. Tách quantity_matches (tổng số con khớp) khỏi
    has_composition_variance (đúng tổng nhưng lệch loại) — đây chính là tình
    huống brief mô tả: kế hoạch 100 loại 1, thực tế 80 loại 1 + 20 loại 2,
    tổng vẫn 100 nhưng cơ cấu đã lệch."""
    planned_type_id = row.get("pig_type_id")
    total_actual = sum(m["quantity"] or 0 for m in mix)
    for m in mix:
        m["is_planned_type"] = m["pig_type_id"] == planned_type_id
        m["share_pct"] = round((m["quantity"] or 0) * 100 / total_actual, 1) if total_actual else None
    off_type = sum(m["quantity"] or 0 for m in mix if not m["is_planned_type"])
    row["delivery_mix"] = {
        "planned": {
            "pig_type_id": planned_type_id,
            "pig_type": row.get("pig_type"),
            "pig_type_name": row.get("pig_type_name"),
            "quantity": row.get("quantity"),
            "expected_avg_weight_kg": row.get("expected_avg_weight_kg"),
            "total_weight_kg": row.get("planned_total_weight_kg"),
        },
        "actual": mix,
        "total_actual_quantity": total_actual,
        "off_type_quantity": off_type,
        "quantity_matches": total_actual == row.get("quantity"),
        "has_composition_variance": off_type > 0,
        # Dòng sinh bởi backfill chỉ ĐOÁN loại heo theo kế hoạch (không ai xác
        # nhận cơ cấu thật) — cờ này để UI không hiện "khớp cơ cấu" một cách
        # tự tin cho dữ liệu chưa từng được kiểm.
        "unconfirmed_composition": any((m.get("backfilled_count") or 0) > 0 for m in mix),
    }
    return row


def _apply_reconciliation_extras(conn: sqlite3.Connection, rows: list[dict]) -> list[dict]:
    """Gắn reconciliation_status + reconciliation_breakdown + delivery_mix cho
    1 danh sách kế hoạch — dùng bởi list_sale_plans/get_sale_plan (nơi UI đối
    soát thực sự cần). Các khối "Cần xử lý" ở Tổng quan (list_pending_review/
    list_awaiting_receipt) không cần nên không gọi thêm; list_sale_plans_for_export
    cũng KHÔNG gọi — delivery_mix là dict lồng, pandas.to_excel không ghi được."""
    plan_ids = [r["id"] for r in rows]
    breakdown = _reconciliation_breakdown_map(conn, plan_ids)
    mix_map = _delivery_mix_map(conn, plan_ids)
    for row in rows:
        row["reconciliation_breakdown"] = breakdown.get(row["id"], [])
        _apply_reconciliation_status(row)
        _apply_delivery_mix(row, mix_map.get(row["id"], []))
    return rows


def _next_plan_code(conn: sqlite3.Connection, farm_id: int, planned_date: str) -> str:
    """Sinh mã kế hoạch <mã trại>-<ngày dự kiến>-<số thứ tự trong ngày của
    trại đó>, VD: XH1-20260820-01. An toàn không đụng hàng: create_sale_plan
    luôn chạy trong db_lock của cả app (xem data_access.py) nên không có 2
    lời gọi tạo kế hoạch chạy song song để đếm ra cùng 1 số thứ tự.

    Kiểm trùng bằng cách dò trực tiếp trên plan_code (không chỉ đếm số dòng
    có cùng planned_date) — vì từ khi có tính năng sửa kế hoạch trại
    (update_sale_plan_edit), planned_date của 1 dòng có thể đổi sau khi tạo
    trong khi plan_code giữ nguyên, nên đếm theo planned_date hiện tại có thể
    thiếu các mã đã cấp trước đó và sinh trùng mã."""
    farm_code = conn.execute("SELECT code FROM farms WHERE id = ?", (farm_id,)).fetchone()[0]
    date_part = planned_date.replace("-", "")
    seq = 1
    while True:
        code = f"{farm_code}-{date_part}-{seq:02d}"
        if conn.execute("SELECT 1 FROM sale_plans WHERE plan_code = ?", (code,)).fetchone() is None:
            return code
        seq += 1


def create_sale_plan(
    plan: dict,
    db_path: Path,
    ip: str | None = None,
    username: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> int:
    now = datetime.now().isoformat(timespec="seconds")

    own_connection = conn is None
    if own_connection:
        conn = get_connection(db_path)

    try:
        plan_code = _next_plan_code(
            conn,
            plan["farm_id"],
            plan["planned_date"],
        )

        cur = conn.execute(
            """
            INSERT INTO sale_plans (
                plan_code,
                planned_date,
                farm_id,
                zone_id,
                shed,
                lot,
                pig_type_id,
                quantity,
                expected_avg_weight_kg,
                note,
                status,
                created_at,
                created_ip,
                created_by,
                updated_at,
                updated_ip,
                updated_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_approval',
                    ?, ?, ?, ?, ?, ?)
            """,
            (
                plan_code,
                plan["planned_date"],
                plan["farm_id"],
                plan.get("zone_id"),
                plan.get("shed"),
                plan.get("lot"),
                plan["pig_type_id"],
                plan["quantity"],
                plan.get("expected_avg_weight_kg"),
                plan.get("note"),
                now,
                ip,
                username,
                now,
                ip,
                username,
            ),
        )

        if own_connection:
            conn.commit()

        return cur.lastrowid

    finally:
        if own_connection:
            conn.close()


def get_sale_plan(plan_id: int, db_path: Path) -> dict | None:
    if not db_path.exists():
        return None
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(_SELECT_ALL + " WHERE sp.id = ?", (plan_id,)).fetchone()
        if row is None:
            return None
        return _apply_reconciliation_extras(conn, [dict(row)])[0]
    finally:
        conn.close()


def list_sale_plans(db_path: Path, farm_ids: list[int] | None = None) -> list[dict]:
    """farm_ids=None: mọi trại (sales/accounting/admin/leadership). farm_ids=[...]:
    chỉ các trại đó (vai trò farm) — gọi hàm này với farm_ids=[] là lỗi (IN ()
    không hợp lệ trong SQLite), tầng route phải tự chặn trước và trả [] ngay."""
    if not db_path.exists():
        return []
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        sql = _SELECT_VISIBLE
        params: tuple = ()
        if farm_ids is not None:
            placeholders = ", ".join("?" * len(farm_ids))
            sql += f" WHERE sp.farm_id IN ({placeholders})"
            params = tuple(farm_ids)
        rows = conn.execute(sql + " ORDER BY sp.planned_date ASC", params).fetchall()
        return _apply_reconciliation_extras(conn, [dict(r) for r in rows])
    finally:
        conn.close()


def list_pending_review(db_path: Path, farm_ids: list[int] | None = None, limit: int = 5) -> dict:
    """Kế hoạch trại đang chờ duyệt — dùng cho khối "Cần xử lý" ở Tổng quan.
    Trả {"total": N, "items": [...]}, item cũ nhất (created_at ASC) lên đầu
    vì đó là việc cấp bách nhất. farm_ids theo đúng quy ước của
    list_sale_plans() — None = không giới hạn trại."""
    if not db_path.exists():
        return {"total": 0, "items": []}
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        where = "WHERE sp.status = 'pending_approval'"
        params: tuple = ()
        if farm_ids is not None:
            placeholders = ", ".join("?" * len(farm_ids))
            where += f" AND sp.farm_id IN ({placeholders})"
            params = tuple(farm_ids)
        total = conn.execute(f"SELECT COUNT(*) FROM sale_plans sp {where}", params).fetchone()[0]
        rows = conn.execute(
            f"{_SELECT_VISIBLE} {where} ORDER BY sp.created_at ASC LIMIT ?", (*params, limit)
        ).fetchall()
        return {"total": total, "items": [dict(r) for r in rows]}
    finally:
        conn.close()


def list_awaiting_receipt(db_path: Path, farm_ids: list[int] | None = None, limit: int = 5) -> dict:
    """Kế hoạch đã duyệt, đã tới/qua ngày dự kiến nhưng chưa ghi nhận xuất
    chuồng thực tế — dùng cho khối "Cần xử lý" ở Tổng quan."""
    if not db_path.exists():
        return {"total": 0, "items": []}
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        today = datetime.now().strftime("%Y-%m-%d")
        where = "WHERE sp.status = 'approved' AND sp.received_quantity IS NULL AND sp.planned_date <= ?"
        params: tuple = (today,)
        if farm_ids is not None:
            placeholders = ", ".join("?" * len(farm_ids))
            where += f" AND sp.farm_id IN ({placeholders})"
            params = (*params, *farm_ids)
        total = conn.execute(f"SELECT COUNT(*) FROM sale_plans sp {where}", params).fetchone()[0]
        rows = conn.execute(
            f"{_SELECT_VISIBLE} {where} ORDER BY sp.planned_date ASC LIMIT ?", (*params, limit)
        ).fetchall()
        return {"total": total, "items": [dict(r) for r in rows]}
    finally:
        conn.close()


def list_sale_plans_for_export(db_path: Path) -> list[dict]:
    """Như list_sale_plans nhưng kèm cả trường ẩn (created_at/ip, updated_at/ip,
    updated_by) — dùng riêng cho xuất Excel đối soát."""
    if not db_path.exists():
        return []
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(_SELECT_ALL + " ORDER BY sp.planned_date ASC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_sale_plan_status(
    plan_id: int,
    status: str,
    db_path: Path,
    ip: str | None = None,
    username: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    own_connection = conn is None
    if own_connection:
        conn = get_connection(db_path)
    try:
        conn.execute(
            """
            UPDATE sale_plans
            SET status = ?, updated_at = ?, updated_ip = ?, updated_by = ?
            WHERE id = ?
            """,
            (status, datetime.now().isoformat(timespec="seconds"), ip, username, plan_id),
        )
        if own_connection:
            conn.commit()
    finally:
        if own_connection:
            conn.close()


def approve_sale_plan(
    plan_id: int,
    db_path: Path,
    ip: str | None = None,
    username: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Duyệt kế hoạch đang chờ. Điều kiện status='pending_approval' trong
    WHERE là lớp bảo vệ thứ 2 (ngoài check ở route) chống duyệt trùng/duyệt
    sai trạng thái."""
    now = datetime.now().isoformat(timespec="seconds")
    own_connection = conn is None
    if own_connection:
        conn = get_connection(db_path)
    try:
        conn.execute(
            """
            UPDATE sale_plans
            SET status = 'approved', approved_by = ?, approved_at = ?,
                updated_at = ?, updated_ip = ?, updated_by = ?
            WHERE id = ? AND status = 'pending_approval'
            """,
            (username, now, now, ip, username, plan_id),
        )
        if own_connection:
            conn.commit()
    finally:
        if own_connection:
            conn.close()


def reject_sale_plan(
    plan_id: int,
    reason: str,
    db_path: Path,
    ip: str | None = None,
    username: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    own_connection = conn is None
    if own_connection:
        conn = get_connection(db_path)
    try:
        conn.execute(
            """
            UPDATE sale_plans
            SET status = 'rejected', rejected_by = ?, rejected_at = ?, rejected_reason = ?,
                updated_at = ?, updated_ip = ?, updated_by = ?
            WHERE id = ? AND status = 'pending_approval'
            """,
            (username, now, reason, now, ip, username, plan_id),
        )
        if own_connection:
            conn.commit()
    finally:
        if own_connection:
            conn.close()


def update_plan_received_quantity(
    plan_id: int,
    received_quantity: int,
    db_path: Path,
    ip: str | None = None,
    username: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Trại tự ghi nhận số lượng thực tế đã xuất chuồng/bàn giao ra nhà chờ
    bán (BM01/QT001 bước B6). Ghi đè giá trị (không cộng dồn) — mỗi lần trại
    xuất chuồng thêm thì tự nhập lại tổng số mới."""
    now = datetime.now().isoformat(timespec="seconds")
    own_connection = conn is None
    if own_connection:
        conn = get_connection(db_path)
    try:
        conn.execute(
            """
            UPDATE sale_plans
            SET received_quantity = ?, received_at = ?, received_by = ?,
                updated_at = ?, updated_ip = ?, updated_by = ?
            WHERE id = ?
            """,
            (received_quantity, now, username, now, ip, username, plan_id),
        )
        if own_connection:
            conn.commit()
    finally:
        if own_connection:
            conn.close()


def update_sale_plan_edit(
    plan_id: int,
    plan: dict,
    db_path: Path,
    ip: str | None = None,
    username: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> bool:
    """Sửa lại nội dung kế hoạch trại (trường hợp nhập nhầm). Đây là quyền
    admin-only-by-default (perm.PLAN_EDIT, xem route) nên KHÔNG còn ràng buộc
    status/allocated_quantity như bản đầu (Giai đoạn 7) — admin có thể sửa
    bất kể trạng thái, kể cả khi đã có kế hoạch bán "nhặt" từ đó. Rủi ro dữ
    liệu (kế hoạch bán tham chiếu loại heo/số lượng cũ) do người dùng có
    quyền này tự chịu trách nhiệm, có audit log đầy đủ (xem route). plan_code
    giữ nguyên, không sinh lại.

    Riêng `quantity` (số kế hoạch gốc): chặn sửa nếu đã có đơn hàng "nhặt"
    từ kế hoạch (allocated_quantity > 0) hoặc đã có bản ghi đối soát — sửa
    lúc đó sẽ làm sai lệch toàn bộ phép tính đối soát (planned - actual_sold
    - reconciled), đúng nguyên tắc "không âm thầm sửa số gốc" của tính năng
    đối soát kế hoạch trại. Raise ValueError (route bắt, trả 400) thay vì
    chặn từ đầu bằng status/permission vì đây là 1 ràng buộc dữ liệu cụ thể,
    không phải quy tắc phân quyền."""
    now = datetime.now().isoformat(timespec="seconds")
    own_connection = conn is None
    if own_connection:
        conn = get_connection(db_path)
    try:
        current = conn.execute("SELECT quantity FROM sale_plans WHERE id = ?", (plan_id,)).fetchone()
        if current is not None and plan["quantity"] != current[0]:
            allocated = conn.execute(
                "SELECT COALESCE(SUM(sa.quantity), 0) FROM sale_allocations sa "
                "JOIN sale_orders so ON so.id = sa.order_id "
                "WHERE sa.sale_plan_id = ? AND so.status IN ('active','done')",
                (plan_id,),
            ).fetchone()[0]
            has_reconciliation = (
                conn.execute(
                    "SELECT 1 FROM sale_plan_reconciliations WHERE sale_plan_id = ? LIMIT 1", (plan_id,)
                ).fetchone()
                is not None
            )
            if allocated > 0 or has_reconciliation:
                raise ValueError(
                    "Không thể sửa số lượng kế hoạch gốc: đã có đơn hàng hoặc bản ghi đối soát "
                    "tham chiếu kế hoạch này. Dùng chức năng \"Xử lý chênh lệch\" thay vì sửa trực tiếp."
                )
        cur = conn.execute(
            """
            UPDATE sale_plans
            SET planned_date = ?, farm_id = ?, zone_id = ?, shed = ?, lot = ?, pig_type_id = ?, quantity = ?,
                expected_avg_weight_kg = ?, note = ?, updated_at = ?, updated_ip = ?, updated_by = ?
            WHERE id = ?
            """,
            (
                plan["planned_date"],
                plan["farm_id"],
                plan.get("zone_id"),
                plan.get("shed"),
                plan.get("lot"),
                plan["pig_type_id"],
                plan["quantity"],
                plan.get("expected_avg_weight_kg"),
                plan.get("note"),
                now,
                ip,
                username,
                plan_id,
            ),
        )
        if own_connection:
            conn.commit()
        return cur.rowcount > 0
    finally:
        if own_connection:
            conn.close()


def delete_sale_plan(plan_id: int, db_path: Path, conn: sqlite3.Connection | None = None) -> bool:
    """Xoá vĩnh viễn 1 kế hoạch trại — chặn nếu còn BẤT KỲ kế hoạch bán nào
    (dòng hàng) từng "nhặt" từ đó, kể cả đã huỷ/vô hiệu hoá (giữ lịch sử đối
    soát toàn vẹn). Không cascade tự động — admin phải tự xử lý/xoá các dòng
    hàng liên quan trước nếu thật sự cần xoá."""
    own_connection = conn is None
    if own_connection:
        conn = get_connection(db_path)
    try:
        cur = conn.execute(
            "DELETE FROM sale_plans WHERE id = ? AND NOT EXISTS "
            "(SELECT 1 FROM sale_allocations WHERE sale_plan_id = sale_plans.id)",
            (plan_id,),
        )
        if own_connection:
            conn.commit()
        return cur.rowcount > 0
    finally:
        if own_connection:
            conn.close()


def count_plans_for_farm(farm_id: int, db_path: Path) -> int:
    """Số kế hoạch (mọi trạng thái) đang tham chiếu trang trại này — dùng để
    chặn admin xóa trang trại còn đang được dùng. Mọi kế hoạch đều gắn
    farm_id trực tiếp nên đếm này bao trùm luôn các khu con của trại."""
    conn = get_connection(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM sale_plans WHERE farm_id = ?", (farm_id,)
        ).fetchone()[0]
    finally:
        conn.close()


def count_plans_for_zone(zone_id: int, db_path: Path) -> int:
    conn = get_connection(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM sale_plans WHERE zone_id = ?", (zone_id,)
        ).fetchone()[0]
    finally:
        conn.close()


def count_plans_for_pig_type(pig_type_id: int, db_path: Path) -> int:
    conn = get_connection(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM sale_plans WHERE pig_type_id = ?", (pig_type_id,)
        ).fetchone()[0]
    finally:
        conn.close()


# --- Giai đoạn 3: dashboard mở rộng (KPI theo số con + biểu đồ) ---
# Khác hẳn dashboard_stats() ở trên (đếm theo ĐƠN, mốc "tháng này" cố
# định, phục vụ khối KPI cũ) — các hàm dưới đây tính theo SỐ CON, khoảng
# ngày chọn được, và cố ý dùng DUY NHẤT 1 mốc thời gian cho cả 3 vế kế
# hoạch/chốt/xuất: sale_plans.planned_date. Lý do chọn planned_date làm
# trục chung: đây là mốc DUY NHẤT tồn tại sẵn trên chính kế hoạch trại
# (nguồn của mọi số liệu), nên "kế hoạch/chốt/xuất của ngày X" luôn nói về
# cùng 1 lô hàng dự kiến ngày X — không lẫn với delivered_date (ngày giao
# THẬT, có thể khác ngày dự kiến) hay ngày tạo đơn.
_DASHBOARD_ALLOCATED_JOIN = (
    "FROM sale_allocations sa "
    "JOIN sale_orders so ON so.id = sa.order_id "
    "JOIN sale_plans sp ON sp.id = sa.sale_plan_id "
    "WHERE so.status IN ('active','done')"
)
_DASHBOARD_ACTUAL_JOIN = (
    "FROM sale_deliveries sd "
    "JOIN sale_allocations sa ON sa.id = sd.allocation_id "
    "JOIN sale_orders so ON so.id = sa.order_id "
    "JOIN sale_plans sp ON sp.id = sa.sale_plan_id "
    "WHERE so.status IN ('active','done')"
)

# Kế hoạch trại luôn dự kiến TRƯƠNG LAI GẦN (đăng ký hôm nay, xuất sau vài
# ngày) — nếu cửa sổ ngày chỉ nhìn NGƯỢC (today-days .. today) như
# gia_heo.html's "N ngày qua" thì kế hoạch vừa tạo cho vài ngày tới biến
# mất khỏi dashboard hoàn toàn. Xác nhận bằng dữ liệu thật: 3/4 kế hoạch
# đang có planned_date 1-3 ngày SAU hôm nay, chỉ 1/4 lọt qua cửa sổ nhìn-
# ngược. Cộng thêm buffer tới nhỏ, cố định (không cho chọn) — "N ngày"
# vẫn có nghĩa "nhìn ngược bao xa", chỉ thêm đủ để không bỏ sót kế hoạch
# vài ngày tới đã lên lịch.
_DASHBOARD_FORWARD_BUFFER_DAYS = 7


def _dashboard_date_range(days: int) -> tuple[str, str]:
    today = datetime.now().date()
    start = today - timedelta(days=days)
    end = today + timedelta(days=_DASHBOARD_FORWARD_BUFFER_DAYS)
    return start.isoformat(), end.isoformat()


def dashboard_summary(db_path: Path, farm_ids: list[int] | None = None, days: int = 30) -> dict:
    """5 KPI cho dashboard mới: kế hoạch/đã chốt/đã xuất thực tế/chưa xuất/
    sai lệch, theo số con, trong cửa sổ planned_date do _dashboard_date_range()
    quyết định (nhìn ngược `days` ngày + buffer tới gần cố định).

    not_shipped_qty = allocated - actual (đã chốt vào đơn nhưng chưa giao
    thật — con số "còn phải làm"). variance_qty = actual - planned (ÂM
    nghĩa là xuất ít hơn kế hoạch, khớp cách đọc trực quan "-105 con" thay
    vì phải tự suy ra dấu từ "kế hoạch trừ thực tế")."""
    if farm_ids is not None and not farm_ids:
        return {
            "planned_qty": 0, "allocated_qty": 0, "actual_qty": 0,
            "not_shipped_qty": 0, "variance_qty": 0,
            "allocated_pct": None, "actual_pct": None, "not_shipped_pct": None, "variance_pct": None,
        }
    conn = get_connection(db_path)
    try:
        farm_where, farm_params = "", ()
        if farm_ids is not None:
            farm_where = f" AND sp.farm_id IN ({', '.join('?' * len(farm_ids))})"
            farm_params = tuple(farm_ids)
        start, end = _dashboard_date_range(days)
        date_where = f" AND sp.planned_date BETWEEN ? AND ?{farm_where}"
        date_params = (start, end, *farm_params)

        planned_qty = conn.execute(
            f"SELECT COALESCE(SUM(sp.quantity), 0) FROM sale_plans sp WHERE 1=1{date_where}", date_params
        ).fetchone()[0]
        allocated_qty = conn.execute(
            f"SELECT COALESCE(SUM(sa.quantity), 0) {_DASHBOARD_ALLOCATED_JOIN}{date_where}", date_params
        ).fetchone()[0]
        actual_qty = conn.execute(
            f"SELECT COALESCE(SUM(sd.quantity), 0) {_DASHBOARD_ACTUAL_JOIN}{date_where}", date_params
        ).fetchone()[0]
        not_shipped_qty = allocated_qty - actual_qty
        variance_qty = actual_qty - planned_qty

        def pct(n):
            return round(n * 100 / planned_qty, 1) if planned_qty else None

        return {
            "planned_qty": planned_qty,
            "allocated_qty": allocated_qty,
            "actual_qty": actual_qty,
            "not_shipped_qty": not_shipped_qty,
            "variance_qty": variance_qty,
            "allocated_pct": pct(allocated_qty),
            "actual_pct": pct(actual_qty),
            "not_shipped_pct": pct(not_shipped_qty),
            "variance_pct": pct(variance_qty),
        }
    finally:
        conn.close()


def daily_reconciliation_series(db_path: Path, farm_ids: list[int] | None = None, days: int = 30) -> list[dict]:
    """1 dòng/ngày trong cửa sổ planned_date của _dashboard_date_range()
    (nhìn ngược `days` ngày + buffer tới gần) — dùng chung cho CẢ bảng
    "Kế hoạch - Chốt - Xuất theo ngày" LẪN dữ liệu biểu đồ xu hướng, tránh
    2 query cho cùng 1 dữ liệu. Trả về ĐẦY ĐỦ mọi ngày trong khoảng kể cả
    ngày không có kế hoạch nào (toàn 0) — cần thiết cho trục thời gian
    liền mạch của biểu đồ; phía bảng (không cần liền mạch) tự lọc bớt
    ngày toàn-0 ở tầng hiển thị."""
    if farm_ids is not None and not farm_ids:
        return []
    conn = get_connection(db_path)
    try:
        farm_where, farm_params = "", ()
        if farm_ids is not None:
            farm_where = f" AND sp.farm_id IN ({', '.join('?' * len(farm_ids))})"
            farm_params = tuple(farm_ids)
        start_iso, end_iso = _dashboard_date_range(days)
        start = datetime.fromisoformat(start_iso).date()
        end = datetime.fromisoformat(end_iso).date()
        range_params = (start_iso, end_iso, *farm_params)

        planned_by_date = dict(
            conn.execute(
                f"SELECT sp.planned_date, SUM(sp.quantity) FROM sale_plans sp "
                f"WHERE sp.planned_date BETWEEN ? AND ?{farm_where} GROUP BY sp.planned_date",
                range_params,
            ).fetchall()
        )
        allocated_by_date = dict(
            conn.execute(
                f"SELECT sp.planned_date, SUM(sa.quantity) {_DASHBOARD_ALLOCATED_JOIN} "
                f"AND sp.planned_date BETWEEN ? AND ?{farm_where} GROUP BY sp.planned_date",
                range_params,
            ).fetchall()
        )
        actual_by_date = dict(
            conn.execute(
                f"SELECT sp.planned_date, SUM(sd.quantity) {_DASHBOARD_ACTUAL_JOIN} "
                f"AND sp.planned_date BETWEEN ? AND ?{farm_where} GROUP BY sp.planned_date",
                range_params,
            ).fetchall()
        )

        result = []
        for i in range((end - start).days + 1):
            d = (start + timedelta(days=i)).isoformat()
            planned = planned_by_date.get(d, 0)
            allocated = allocated_by_date.get(d, 0)
            actual = actual_by_date.get(d, 0)
            result.append(
                {
                    "date": d,
                    "planned_qty": planned,
                    "allocated_qty": allocated,
                    "actual_qty": actual,
                    "variance_qty": actual - planned,
                }
            )
        return result
    finally:
        conn.close()


def pig_type_composition(db_path: Path, farm_ids: list[int] | None = None, days: int = 30) -> list[dict]:
    """Cơ cấu loại heo THỰC TẾ đã xuất (nguồn sale_deliveries — trả lời
    "đã bán cái gì thật", không phải kế hoạch định bán gì) trong cùng cửa
    sổ planned_date với dashboard_summary()/daily_reconciliation_series().
    Sort giảm dần theo số lượng, kèm % trên tổng."""
    if farm_ids is not None and not farm_ids:
        return []
    conn = get_connection(db_path)
    try:
        farm_where, farm_params = "", ()
        if farm_ids is not None:
            farm_where = f" AND sp.farm_id IN ({', '.join('?' * len(farm_ids))})"
            farm_params = tuple(farm_ids)
        start, end = _dashboard_date_range(days)
        rows = conn.execute(
            "SELECT pt.name AS pig_type_name, SUM(sd.quantity) AS quantity "
            "FROM sale_deliveries sd "
            "JOIN sale_allocations sa ON sa.id = sd.allocation_id "
            "JOIN sale_orders so ON so.id = sa.order_id "
            "JOIN sale_plans sp ON sp.id = sa.sale_plan_id "
            "LEFT JOIN pig_types pt ON pt.id = sd.pig_type_id "
            f"WHERE so.status IN ('active','done') AND sp.planned_date BETWEEN ? AND ?{farm_where} "
            "GROUP BY sd.pig_type_id ORDER BY quantity DESC",
            (start, end, *farm_params),
        ).fetchall()
        total = sum(r[1] for r in rows) or 1
        return [
            {"pig_type_name": r[0] or "—", "quantity": r[1], "pct": round(r[1] * 100 / total, 1)} for r in rows
        ]
    finally:
        conn.close()


def list_needs_reconciliation(db_path: Path, farm_ids: list[int] | None = None, limit: int = 5) -> dict:
    """Kế hoạch đang ở trạng thái 'needs_reconciliation' — khối "Cần xử
    lý" ở Tổng quan. Tái dùng list_sale_plans() (đã tính reconciliation_status
    qua _apply_reconciliation_status) thay vì viết lại điều kiện SQL riêng
    — tránh 2 nơi định nghĩa "thế nào là cần đối soát" lệch nhau theo thời
    gian. Số kế hoạch trong app còn nhỏ nên lọc ở Python chưa phải vấn đề
    hiệu năng; nếu dữ liệu lớn hơn nhiều về sau, cân nhắc viết lại thành
    điều kiện SQL trực tiếp."""
    all_plans = list_sale_plans(db_path, farm_ids=farm_ids)
    matching = [p for p in all_plans if p.get("reconciliation_status") == "needs_reconciliation"]
    matching.sort(key=lambda p: p["planned_date"])
    return {"total": len(matching), "items": matching[:limit]}


def list_idle_supply(db_path: Path, farm_ids: list[int] | None = None, days: int = 7, limit: int = 10) -> dict:
    """Exception Center (STEP 10): kế hoạch đã duyệt + đã xuất chuồng
    (received_at có giá trị) từ ÍT NHẤT `days` ngày mà vẫn còn
    remaining_quantity > 0 (chưa được đưa vào đơn hàng nào) — heo đã
    sẵn sàng bán nhưng ứ đọng lâu là rủi ro thật (chi phí nuôi giữ,
    chất lượng heo giảm). Tái dùng list_sale_plans() + lọc Python, đúng
    khuôn list_needs_reconciliation() ở trên — cùng lý do (dữ liệu nhỏ,
    tránh định nghĩa "remaining_quantity" lệch giữa 2 nơi)."""
    threshold = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    all_plans = list_sale_plans(db_path, farm_ids=farm_ids)
    matching = [
        p
        for p in all_plans
        if p.get("status") == "approved"
        and p.get("received_at")
        and p["received_at"] <= threshold
        and p.get("remaining_quantity", 0) > 0
    ]
    matching.sort(key=lambda p: p["received_at"])
    return {"total": len(matching), "items": matching[:limit]}


def get_plan_sale_breakdown(plan_id: int, db_path: Path) -> list[dict]:
    """Đối soát đa chiều (brief nghiệp vụ): 3 chiều Khách hàng/Giá/Phiếu cân
    KHÔNG rút gọn về 1 cột được vì 1 kế hoạch trại có thể tách nhiều đơn
    hàng/khách hàng/giá khác nhau (đúng tình huống "1 kế hoạch có thể phân
    bổ cho nhiều khách hàng" brief nêu) — trả về 1 danh sách, mỗi phần tử
    là 1 dòng hàng (sale_allocations) đã "nhặt" từ kế hoạch này, kèm khách
    hàng/giá chốt/giá thực tế của đơn chứa dòng đó + các phiếu cân
    (weighing_ref) đã ghi nhận qua các lần xuất giao của dòng đó."""
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        alloc_rows = conn.execute(
            """
            SELECT sa.id AS allocation_id, sa.quantity, sa.selling_price, sa.actual_price,
                   so.id AS order_id, so.order_code, so.status AS order_status,
                   c.name AS customer_name
            FROM sale_allocations sa
            JOIN sale_orders so ON so.id = sa.order_id
            LEFT JOIN customers c ON c.id = so.customer_id
            WHERE sa.sale_plan_id = ?
            ORDER BY so.created_at ASC, sa.id ASC
            """,
            (plan_id,),
        ).fetchall()
        if not alloc_rows:
            return []
        allocation_ids = [r["allocation_id"] for r in alloc_rows]
        placeholders = ", ".join("?" * len(allocation_ids))
        ticket_rows = conn.execute(
            f"SELECT allocation_id, weighing_ref FROM sale_deliveries "
            f"WHERE allocation_id IN ({placeholders}) AND weighing_ref IS NOT NULL AND weighing_ref != ''",
            tuple(allocation_ids),
        ).fetchall()
        tickets_by_allocation: dict[int, list[str]] = {}
        for t in ticket_rows:
            tickets_by_allocation.setdefault(t["allocation_id"], []).append(t["weighing_ref"])
        breakdown = []
        for r in alloc_rows:
            row = dict(r)
            row["weighing_refs"] = tickets_by_allocation.get(r["allocation_id"], [])
            breakdown.append(row)
        return breakdown
    finally:
        conn.close()
