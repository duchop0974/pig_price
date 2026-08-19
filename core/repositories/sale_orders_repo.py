"""CRUD cho "đơn hàng" (sale_orders, header — khách hàng/liên hệ/chốt bán/
giao nhận/thanh toán/doanh thu/hoá đơn, BM02) + "dòng hàng" (sale_allocations,
mỗi dòng "nhặt" số lượng/giá từ MỘT kế hoạch trại đã duyệt). 1 đơn cho 1 khách
hàng có thể gồm nhiều dòng khác loại heo/khác kế hoạch trại."""
import sqlite3
from datetime import datetime
from pathlib import Path

from core.db import get_connection

SALE_ORDER_VISIBLE_COLUMNS = [
    "id",
    "order_code",
    "customer_id",
    "customer_name",
    "customer_phone",
    "customer_email",
    "customer_contact_person",
    "contacted_by",
    "contacted_at",
    "contact_note",
    "confirmed_sale_at",
    "delivery_time",
    "payment_method",
    "status",
    "paid_amount",
    "paid_at",
    "weighing_ref",
    "revenue_recorded_by",
    "revenue_recorded_at",
    "invoice_number",
    "invoiced_by",
    "invoiced_at",
    "created_by",
]

SALE_ORDER_ALL_COLUMNS = SALE_ORDER_VISIBLE_COLUMNS + [
    "created_at",
    "created_ip",
    "updated_at",
    "updated_ip",
    "updated_by",
]

# pig_type/farm/zone/planned_date... lấy qua JOIN sang sale_plans (dòng hàng
# không tự lưu loại heo riêng — chỉ được nhặt đúng loại trại đã đăng ký).
SALE_ORDER_LINE_VISIBLE_COLUMNS = [
    "id",
    "order_id",
    "plan_code",
    "sale_plan_id",
    "sale_plan_code",
    "farm",
    "province",
    "zone",
    "shed",
    "lot",
    "pig_type_id",
    "pig_type",
    "pig_type_name",
    "planned_date",
    "quantity",
    "selling_price",
    "note",
    "actual_price",
    "actual_quantity",
    "locked_at",
    "locked_by",
]

_ORDER_JOIN_SQL = """
    FROM sale_orders so
    LEFT JOIN customers c ON c.id = so.customer_id
"""

_ORDER_SELECT_VISIBLE = (
    "SELECT so.id, so.order_code, so.customer_id, c.name AS customer_name, c.phone AS customer_phone, "
    "c.email AS customer_email, c.contact_person AS customer_contact_person, "
    "so.contacted_by, so.contacted_at, so.contact_note, so.confirmed_sale_at, "
    "so.delivery_time, so.payment_method, so.status, "
    "so.paid_amount, so.paid_at, so.weighing_ref, so.revenue_recorded_by, so.revenue_recorded_at, "
    "so.invoice_number, so.invoiced_by, so.invoiced_at, so.created_by, "
    "so.locked_at, so.locked_by"
    + _ORDER_JOIN_SQL
)

_ORDER_SELECT_ALL = (
    "SELECT so.id, so.order_code, so.customer_id, c.name AS customer_name, c.phone AS customer_phone, "
    "c.email AS customer_email, c.contact_person AS customer_contact_person, "
    "so.contacted_by, so.contacted_at, so.contact_note, so.confirmed_sale_at, "
    "so.delivery_time, so.payment_method, so.status, "
    "so.paid_amount, so.paid_at, so.weighing_ref, so.revenue_recorded_by, so.revenue_recorded_at, "
    "so.invoice_number, so.invoiced_by, so.invoiced_at, so.created_by, "
    "so.locked_at, so.locked_by, "
    "so.created_at, so.created_ip, so.updated_at, so.updated_ip, so.updated_by"
    + _ORDER_JOIN_SQL
)

_LINE_JOIN_SQL = """
    FROM sale_allocations sa
    JOIN sale_plans sp ON sp.id = sa.sale_plan_id
    JOIN farms f ON f.id = sp.farm_id
    LEFT JOIN zones z ON z.id = sp.zone_id
    LEFT JOIN pig_types pt ON pt.id = sp.pig_type_id
"""

_LINE_SELECT = (
    "SELECT sa.id, sa.order_id, sa.plan_code, sa.sale_plan_id, sp.plan_code AS sale_plan_code, "
    "f.code AS farm, f.province AS province, z.code AS zone, sp.shed, sp.lot, "
    "sp.pig_type_id AS pig_type_id, pt.code AS pig_type, pt.name AS pig_type_name, sp.planned_date, "
    "sa.quantity, sa.selling_price, sa.note, sa.actual_price, sa.actual_quantity, "
    "sa.locked_at, sa.locked_by"
    + _LINE_JOIN_SQL
)


def _next_order_code(conn: sqlite3.Connection, created_date: str) -> str:
    """Sinh mã đơn DH<YYYYMMDD>-<seq>, VD: DH20260820-01. Dò trùng trực tiếp
    trên order_code (không đếm số dòng theo ngày) — created_date không đổi
    sau khi tạo nên không gặp lớp lỗi đã sửa ở _next_plan_code (Giai đoạn 7:
    sinh mã dựa trên cột có thể sửa sau → trùng mã)."""
    date_part = created_date.replace("-", "")[:8]
    seq = 1
    while True:
        code = f"DH{date_part}-{seq:02d}"
        if conn.execute("SELECT 1 FROM sale_orders WHERE order_code = ?", (code,)).fetchone() is None:
            return code
        seq += 1


def _next_allocation_code(conn: sqlite3.Connection, sale_plan_id: int) -> str:
    """Sinh mã dòng hàng <mã kế hoạch trại>-B<số thứ tự>, VD:
    XH1-20260820-01-B01, ...-B02. Fallback SP<id>-B.. nếu trại chưa có mã."""
    row = conn.execute("SELECT plan_code FROM sale_plans WHERE id = ?", (sale_plan_id,)).fetchone()
    parent_code = row[0] if row and row[0] else f"SP{sale_plan_id}"
    seq = (
        conn.execute(
            "SELECT COUNT(*) FROM sale_allocations WHERE sale_plan_id = ?", (sale_plan_id,)
        ).fetchone()[0]
        + 1
    )
    return f"{parent_code}-B{seq:02d}"


def _insert_line(conn: sqlite3.Connection, order_id: int, line: dict, now: str, ip, username) -> int:
    plan_code = _next_allocation_code(conn, line["sale_plan_id"])
    cur = conn.execute(
        """
        INSERT INTO sale_allocations (plan_code, order_id, sale_plan_id, quantity, selling_price, note,
                                       created_at, created_ip, created_by, updated_at, updated_ip, updated_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            plan_code,
            order_id,
            line["sale_plan_id"],
            line["quantity"],
            line.get("selling_price"),
            line.get("note"),
            now,
            ip,
            username,
            now,
            ip,
            username,
        ),
    )
    return cur.lastrowid


def create_order(lines: list[dict], db_path: Path, ip: str | None = None, username: str | None = None) -> int:
    """Tạo 1 đơn hàng mới (status='active') kèm N dòng hàng ban đầu — 1
    transaction, đơn không bao giờ tồn tại mà chưa có dòng nào."""
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection(db_path)
    try:
        order_code = _next_order_code(conn, now[:10])
        cur = conn.execute(
            """
            INSERT INTO sale_orders (order_code, status, created_at, created_ip, created_by,
                                      updated_at, updated_ip, updated_by)
            VALUES (?, 'active', ?, ?, ?, ?, ?, ?)
            """,
            (order_code, now, ip, username, now, ip, username),
        )
        order_id = cur.lastrowid
        for line in lines:
            _insert_line(conn, order_id, line, now, ip, username)
        conn.commit()
        return order_id
    finally:
        conn.close()


def add_order_line(
    order_id: int, line: dict, db_path: Path, ip: str | None = None, username: str | None = None
) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection(db_path)
    try:
        line_id = _insert_line(conn, order_id, line, now, ip, username)
        conn.execute(
            "UPDATE sale_orders SET updated_at = ?, updated_ip = ?, updated_by = ? WHERE id = ?",
            (now, ip, username, order_id),
        )
        conn.commit()
        return line_id
    finally:
        conn.close()


def remove_order_line(
    order_id: int, allocation_id: int, db_path: Path, ip: str | None = None, username: str | None = None
) -> bool:
    """Xoá thẳng 1 dòng khỏi đơn (chỉ dùng khi đơn còn active — kiểm ở tầng
    route). Trả False nếu dòng không thuộc đơn này (điều kiện AND order_id
    trong WHERE là lớp bảo vệ thứ 2)."""
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection(db_path)
    try:
        cur = conn.execute("DELETE FROM sale_allocations WHERE id = ? AND order_id = ?", (allocation_id, order_id))
        if cur.rowcount > 0:
            conn.execute(
                "UPDATE sale_orders SET updated_at = ?, updated_ip = ?, updated_by = ? WHERE id = ?",
                (now, ip, username, order_id),
            )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def update_order_line(
    allocation_id: int, db_path: Path, ip: str | None, username: str | None, fields: dict
) -> bool:
    """Sửa số lượng/giá/ghi chú 1 dòng hàng ĐÃ TẠO — đường "ép buộc" dành
    riêng cho quyền admin-only-by-default perm.ORDER_EDIT_LINE (xem route),
    KHÔNG kiểm tra lại remaining_quantity của kế hoạch trại hay trạng thái
    đơn (khác hẳn create_order/add_order_line vốn luôn validate trước khi
    ghi) — người có quyền này tự chịu trách nhiệm về tính nhất quán số liệu,
    có audit log đầy đủ ở route. Cùng pattern "chỉ set field có mặt" như
    update_order_sale_details."""
    set_parts, params = [], []
    for col in ("quantity", "selling_price", "note"):
        if col in fields:
            set_parts.append(f"{col} = ?")
            params.append(fields[col])
    if not set_parts:
        return False
    set_parts += ["updated_at = ?", "updated_ip = ?", "updated_by = ?"]
    params += [datetime.now().isoformat(timespec="seconds"), ip, username]
    params.append(allocation_id)
    conn = get_connection(db_path)
    try:
        cur = conn.execute(f"UPDATE sale_allocations SET {', '.join(set_parts)} WHERE id = ?", params)
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_order(order_id: int, db_path: Path) -> tuple[bool, str | None]:
    """Xoá vĩnh viễn 1 đơn hàng + toàn bộ dòng hàng của nó — chặn nếu bất kỳ
    dòng nào đã có lần cân (weighing_records), sự cố (incident_reports) hoặc
    lần xuất giao thực tế (sale_deliveries) gắn vào (3 bảng tham chiếu thẳng
    sale_allocations.id — xoá dòng sẽ để lại bản ghi mồ côi nếu không chặn).
    Không cascade các bảng đó — admin phải tự xử lý trước. Với
    sale_deliveries đặc biệt quan trọng: đây chính là sổ ghi audit trail
    "xuất giao thực tế" mà tính năng đối soát dựa vào — cascade-xoá sẽ phá
    huỷ đúng cái bằng chứng tính năng này tồn tại để giữ lại."""
    conn = get_connection(db_path)
    try:
        line_ids = [r[0] for r in conn.execute("SELECT id FROM sale_allocations WHERE order_id = ?", (order_id,)).fetchall()]
        if line_ids:
            placeholders = ", ".join("?" * len(line_ids))
            has_weighing = conn.execute(
                f"SELECT 1 FROM weighing_records WHERE sale_allocation_id IN ({placeholders}) LIMIT 1", line_ids
            ).fetchone()
            has_incident = conn.execute(
                f"SELECT 1 FROM incident_reports WHERE allocation_id IN ({placeholders}) LIMIT 1", line_ids
            ).fetchone()
            has_delivery = conn.execute(
                f"SELECT 1 FROM sale_deliveries WHERE allocation_id IN ({placeholders}) LIMIT 1", line_ids
            ).fetchone()
            if has_weighing or has_incident or has_delivery:
                return False, "Không thể xoá: đã có lần cân, sự cố hoặc bản ghi xuất giao gắn với dòng hàng của đơn này."
        conn.execute("DELETE FROM sale_allocations WHERE order_id = ?", (order_id,))
        cur = conn.execute("DELETE FROM sale_orders WHERE id = ?", (order_id,))
        conn.commit()
        return cur.rowcount > 0, None
    finally:
        conn.close()


def _attach_lines(conn: sqlite3.Connection, orders: list[dict]) -> None:
    if not orders:
        return
    order_ids = [o["id"] for o in orders]
    placeholders = ", ".join("?" * len(order_ids))
    conn.row_factory = sqlite3.Row
    line_rows = conn.execute(
        _LINE_SELECT + f" WHERE sa.order_id IN ({placeholders}) ORDER BY sa.id ASC", order_ids
    ).fetchall()
    lines_by_order: dict[int, list[dict]] = {}
    for r in line_rows:
        d = dict(r)
        lines_by_order.setdefault(d["order_id"], []).append(d)
    for o in orders:
        o["lines"] = lines_by_order.get(o["id"], [])


def get_order(order_id: int, db_path: Path) -> dict | None:
    if not db_path.exists():
        return None
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(_ORDER_SELECT_ALL + " WHERE so.id = ?", (order_id,)).fetchone()
        if row is None:
            return None
        order = dict(row)
        _attach_lines(conn, [order])
        return order
    finally:
        conn.close()


def list_awaiting_sale_details(db_path: Path, limit: int = 5) -> dict:
    """Đơn đang xử lý nhưng chưa "Chốt bán hàng" (chưa gán khách hàng) —
    dùng cho khối "Cần xử lý" ở Tổng quan. Trả {"total": N, "items": [...]},
    đơn cũ nhất lên đầu (created_at ASC)."""
    if not db_path.exists():
        return {"total": 0, "items": []}
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        where = "WHERE so.status = 'active' AND so.customer_id IS NULL"
        total = conn.execute(f"SELECT COUNT(*) FROM sale_orders so {where}").fetchone()[0]
        rows = conn.execute(f"{_ORDER_SELECT_VISIBLE} {where} ORDER BY so.created_at ASC LIMIT ?", (limit,)).fetchall()
        return {"total": total, "items": [dict(r) for r in rows]}
    finally:
        conn.close()


def list_awaiting_revenue(db_path: Path, limit: int = 5) -> dict:
    """Đơn đã "Đã bán" nhưng chưa ghi nhận doanh thu — dùng cho khối "Cần
    xử lý" ở Tổng quan."""
    if not db_path.exists():
        return {"total": 0, "items": []}
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        where = "WHERE so.status = 'done' AND so.paid_amount IS NULL"
        total = conn.execute(f"SELECT COUNT(*) FROM sale_orders so {where}").fetchone()[0]
        rows = conn.execute(f"{_ORDER_SELECT_VISIBLE} {where} ORDER BY so.created_at ASC LIMIT ?", (limit,)).fetchall()
        return {"total": total, "items": [dict(r) for r in rows]}
    finally:
        conn.close()


def list_orders(db_path: Path) -> list[dict]:
    if not db_path.exists():
        return []
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(_ORDER_SELECT_VISIBLE + " ORDER BY so.created_at ASC").fetchall()
        orders = [dict(r) for r in rows]
        _attach_lines(conn, orders)
        return orders
    finally:
        conn.close()


def list_orders_for_export(db_path: Path) -> list[dict]:
    """Làm phẳng ra từng dòng hàng kèm mọi trường của đơn cha (1 dòng Excel =
    1 dòng hàng) — dùng cho xuất Excel/chào hàng."""
    if not db_path.exists():
        return []
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        orders = {r["id"]: dict(r) for r in conn.execute(_ORDER_SELECT_ALL).fetchall()}
        line_rows = conn.execute(_LINE_SELECT + " ORDER BY sa.id ASC").fetchall()
        flat = []
        for r in line_rows:
            line = dict(r)
            order = orders.get(line["order_id"], {})
            flat.append({**order, **line, "order_id": line["order_id"]})
        return flat
    finally:
        conn.close()


def update_order_status(
    order_id: int, status: str, db_path: Path, ip: str | None = None, username: str | None = None
) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE sale_orders SET status = ?, updated_at = ?, updated_ip = ?, updated_by = ? WHERE id = ?",
            (status, datetime.now().isoformat(timespec="seconds"), ip, username, order_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_order_done(
    order_id: int,
    line_actuals: list[dict],
    db_path: Path,
    ip: str | None = None,
    username: str | None = None,
) -> None:
    """Đánh dấu đơn 'Đã bán' + ghi giá/số lượng bán thực tế cho từng dòng.
    line_actuals: [{'allocation_id', 'actual_price', 'actual_quantity'}, ...]
    — 1 transaction, đơn + mọi dòng cùng chuyển trạng thái/số liệu 1 lần.

    Từ khi có sale_deliveries: NGUỒN SỰ THẬT của số thực tế là các lần xuất
    giao (sale_deliveries), còn sale_allocations.actual_quantity/actual_price
    chỉ là CACHE DẪN XUẤT (export Excel + UI cũ đang đọc). Signature giữ
    nguyên nên route/JS không phải sửa, nhưng bên trong xử lý 2 nhánh:

    - Dòng CHƯA có lần xuất nào -> tạo 1 delivery từ số liệu vừa nhập (luồng
      nhanh cũ: bán 1 lần, loại heo mặc định theo kế hoạch trại).
    - Dòng ĐÃ có lần xuất (người dùng ghi nhận xuất từng đợt trước đó, có thể
      đã tách loại heo) -> KHÔNG tạo thêm, chỉ đồng bộ lại cache từ tổng các
      lần xuất, để không cộng trùng và không xoá mất cơ cấu đã ghi.
    """
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE sale_orders SET status = 'done', updated_at = ?, updated_ip = ?, updated_by = ? WHERE id = ?",
            (now, ip, username, order_id),
        )
        for item in line_actuals:
            allocation_id = item["allocation_id"]
            has_delivery = conn.execute(
                "SELECT 1 FROM sale_deliveries WHERE allocation_id = ? LIMIT 1", (allocation_id,)
            ).fetchone()
            if has_delivery is None:
                pig_type_row = conn.execute(
                    "SELECT sp.pig_type_id FROM sale_allocations sa "
                    "JOIN sale_plans sp ON sp.id = sa.sale_plan_id WHERE sa.id = ?",
                    (allocation_id,),
                ).fetchone()
                conn.execute(
                    """
                    INSERT INTO sale_deliveries (allocation_id, pig_type_id, quantity, unit_price,
                                                  delivered_date, note,
                                                  created_at, created_ip, created_by,
                                                  updated_at, updated_ip, updated_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        allocation_id,
                        pig_type_row[0] if pig_type_row else None,
                        item["actual_quantity"],
                        item["actual_price"],
                        now[:10],
                        'Sinh tự động khi đánh dấu "Đã bán" — loại heo theo kế hoạch trại.',
                        now,
                        ip,
                        username,
                        now,
                        ip,
                        username,
                    ),
                )
            conn.execute(
                """
                UPDATE sale_allocations
                SET actual_quantity = (SELECT SUM(sd.quantity) FROM sale_deliveries sd WHERE sd.allocation_id = ?),
                    actual_price = (
                        SELECT CAST(ROUND(
                            SUM(sd.unit_price * sd.quantity) * 1.0
                            / NULLIF(SUM(CASE WHEN sd.unit_price IS NULL THEN 0 ELSE sd.quantity END), 0)
                        ) AS INTEGER)
                        FROM sale_deliveries sd WHERE sd.allocation_id = ? AND sd.unit_price IS NOT NULL
                    ),
                    updated_at = ?, updated_ip = ?, updated_by = ?
                WHERE id = ? AND order_id = ?
                """,
                (allocation_id, allocation_id, now, ip, username, allocation_id, order_id),
            )
        conn.commit()
    finally:
        conn.close()


def update_order_sale_details(
    order_id: int, db_path: Path, ip: str | None, username: str | None, fields: dict
) -> None:
    """fields: dict con của {'customer_id','contact_note','confirmed_sale_at',
    'delivery_time','payment_method'} — chỉ những khoá THỰC SỰ CÓ MẶT trong
    fields mới được UPDATE (không dùng COALESCE — không phân biệt được "không
    truyền" (giữ nguyên) với "truyền None" (xoá giá trị), xem
    update_allocation_sale_details cũ). Khi 'contact_note' có mặt và không
    rỗng, tự set contacted_by/contacted_at."""
    set_parts, params = [], []
    for col in ("customer_id", "contact_note", "confirmed_sale_at", "delivery_time", "payment_method"):
        if col in fields:
            set_parts.append(f"{col} = ?")
            params.append(fields[col])
    if "contact_note" in fields and (fields["contact_note"] or "").strip():
        set_parts += ["contacted_by = ?", "contacted_at = ?"]
        params += [username, datetime.now().isoformat(timespec="seconds")]
    if not set_parts:
        return
    set_parts += ["updated_at = ?", "updated_ip = ?", "updated_by = ?"]
    params += [datetime.now().isoformat(timespec="seconds"), ip, username]
    params.append(order_id)
    conn = get_connection(db_path)
    try:
        conn.execute(f"UPDATE sale_orders SET {', '.join(set_parts)} WHERE id = ?", params)
        conn.commit()
    finally:
        conn.close()


def update_order_revenue_details(
    order_id: int, db_path: Path, ip: str | None, username: str | None, fields: dict
) -> None:
    """fields: dict con của {'paid_amount','weighing_ref','invoice_number'} —
    cùng cách "chỉ set field có mặt" như update_order_sale_details. Khi
    'paid_amount' có mặt và > 0, tự set revenue_recorded_by/at. Khi
    'invoice_number' có mặt và không rỗng, tự set invoiced_by/at."""
    set_parts, params = [], []
    for col in ("paid_amount", "weighing_ref", "invoice_number"):
        if col in fields:
            set_parts.append(f"{col} = ?")
            params.append(fields[col])
    now = datetime.now().isoformat(timespec="seconds")
    if "paid_amount" in fields and (fields["paid_amount"] or 0) > 0:
        set_parts += ["paid_at = ?", "revenue_recorded_by = ?", "revenue_recorded_at = ?"]
        params += [now, username, now]
    if "invoice_number" in fields and (fields["invoice_number"] or "").strip():
        set_parts += ["invoiced_by = ?", "invoiced_at = ?"]
        params += [username, now]
    if not set_parts:
        return
    set_parts += ["updated_at = ?", "updated_ip = ?", "updated_by = ?"]
    params += [now, ip, username]
    params.append(order_id)
    conn = get_connection(db_path)
    try:
        conn.execute(f"UPDATE sale_orders SET {', '.join(set_parts)} WHERE id = ?", params)
        conn.commit()
    finally:
        conn.close()


def count_orders_for_customer(customer_id: int, db_path: Path) -> int:
    conn = get_connection(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM sale_orders WHERE customer_id = ?", (customer_id,)
        ).fetchone()[0]
    finally:
        conn.close()
