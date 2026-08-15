"""CRUD cho bảng sale_allocations (kế hoạch bán — Phòng bán hàng "nhặt" số
lượng/loại heo từ MỘT kế hoạch trại (sale_plans) đã duyệt, gán giá chào bán,
BM02). 1 kế hoạch trại có thể sinh nhiều kế hoạch bán."""
import sqlite3
from datetime import datetime
from pathlib import Path

from core.db import get_connection

# pig_type/farm/zone/planned_date... lấy qua JOIN sang sale_plans (kế hoạch
# bán không tự lưu loại heo riêng — chỉ được nhặt đúng loại trại đã đăng ký).
SALE_ALLOCATION_VISIBLE_COLUMNS = [
    "id",
    "plan_code",
    "sale_plan_id",
    "sale_plan_code",
    "farm",
    "province",
    "zone",
    "shed",
    "lot",
    "pig_type",
    "pig_type_name",
    "planned_date",
    "quantity",
    "selling_price",
    "note",
    "status",
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
    "actual_price",
    "actual_quantity",
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

SALE_ALLOCATION_ALL_COLUMNS = SALE_ALLOCATION_VISIBLE_COLUMNS + [
    "created_at",
    "created_ip",
    "updated_at",
    "updated_ip",
    "updated_by",
]

_JOIN_SQL = """
    FROM sale_allocations sa
    JOIN sale_plans sp ON sp.id = sa.sale_plan_id
    JOIN farms f ON f.id = sp.farm_id
    LEFT JOIN zones z ON z.id = sp.zone_id
    LEFT JOIN pig_types pt ON pt.id = sp.pig_type_id
    LEFT JOIN customers c ON c.id = sa.customer_id
"""

_SELECT_VISIBLE = (
    "SELECT sa.id, sa.plan_code, sa.sale_plan_id, sp.plan_code AS sale_plan_code, "
    "f.code AS farm, f.province AS province, z.code AS zone, sp.shed, sp.lot, "
    "pt.code AS pig_type, pt.name AS pig_type_name, sp.planned_date, "
    "sa.quantity, sa.selling_price, sa.note, sa.status, "
    "sa.customer_id, c.name AS customer_name, c.phone AS customer_phone, "
    "c.email AS customer_email, c.contact_person AS customer_contact_person, "
    "sa.contacted_by, sa.contacted_at, sa.contact_note, sa.confirmed_sale_at, "
    "sa.delivery_time, sa.payment_method, sa.actual_price, sa.actual_quantity, "
    "sa.paid_amount, sa.paid_at, sa.weighing_ref, sa.revenue_recorded_by, sa.revenue_recorded_at, "
    "sa.invoice_number, sa.invoiced_by, sa.invoiced_at, sa.created_by"
    + _JOIN_SQL
)

_SELECT_ALL = (
    "SELECT sa.id, sa.plan_code, sa.sale_plan_id, sp.plan_code AS sale_plan_code, "
    "f.code AS farm, f.province AS province, z.code AS zone, sp.shed, sp.lot, "
    "pt.code AS pig_type, pt.name AS pig_type_name, sp.planned_date, "
    "sa.quantity, sa.selling_price, sa.note, sa.status, "
    "sa.customer_id, c.name AS customer_name, c.phone AS customer_phone, "
    "c.email AS customer_email, c.contact_person AS customer_contact_person, "
    "sa.contacted_by, sa.contacted_at, sa.contact_note, sa.confirmed_sale_at, "
    "sa.delivery_time, sa.payment_method, sa.actual_price, sa.actual_quantity, "
    "sa.paid_amount, sa.paid_at, sa.weighing_ref, sa.revenue_recorded_by, sa.revenue_recorded_at, "
    "sa.invoice_number, sa.invoiced_by, sa.invoiced_at, sa.created_by, "
    "sa.created_at, sa.created_ip, sa.updated_at, sa.updated_ip, sa.updated_by"
    + _JOIN_SQL
)


def _next_allocation_code(conn: sqlite3.Connection, sale_plan_id: int) -> str:
    """Sinh mã kế hoạch bán <mã kế hoạch trại>-B<số thứ tự>, VD:
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


def create_allocation(alloc: dict, db_path: Path, ip: str | None = None, username: str | None = None) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection(db_path)
    try:
        plan_code = _next_allocation_code(conn, alloc["sale_plan_id"])
        cur = conn.execute(
            """
            INSERT INTO sale_allocations (plan_code, sale_plan_id, quantity, selling_price, note,
                                           status, created_at, created_ip, created_by,
                                           updated_at, updated_ip, updated_by)
            VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
            """,
            (
                plan_code,
                alloc["sale_plan_id"],
                alloc["quantity"],
                alloc.get("selling_price"),
                alloc.get("note"),
                now,
                ip,
                username,
                now,
                ip,
                username,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_allocation(allocation_id: int, db_path: Path) -> dict | None:
    if not db_path.exists():
        return None
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(_SELECT_ALL + " WHERE sa.id = ?", (allocation_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_allocations(db_path: Path, sale_plan_id: int | None = None) -> list[dict]:
    if not db_path.exists():
        return []
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        sql = _SELECT_VISIBLE
        params: tuple = ()
        if sale_plan_id is not None:
            sql += " WHERE sa.sale_plan_id = ?"
            params = (sale_plan_id,)
        rows = conn.execute(sql + " ORDER BY sa.created_at ASC", params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_allocations_for_export(db_path: Path) -> list[dict]:
    if not db_path.exists():
        return []
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(_SELECT_ALL + " ORDER BY sa.created_at ASC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_allocation_status(
    allocation_id: int,
    status: str,
    db_path: Path,
    ip: str | None = None,
    username: str | None = None,
    actual_price: int | None = None,
    actual_quantity: int | None = None,
) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            UPDATE sale_allocations
            SET status = ?, actual_price = COALESCE(?, actual_price),
                actual_quantity = COALESCE(?, actual_quantity),
                updated_at = ?, updated_ip = ?, updated_by = ?
            WHERE id = ?
            """,
            (
                status,
                actual_price,
                actual_quantity,
                datetime.now().isoformat(timespec="seconds"),
                ip,
                username,
                allocation_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def update_allocation_sale_details(
    allocation_id: int, db_path: Path, ip: str | None, username: str | None, fields: dict
) -> None:
    """fields: dict con của {'customer_id','contact_note','confirmed_sale_at',
    'selling_price','delivery_time','payment_method'} — chỉ những khoá THỰC
    SỰ CÓ MẶT trong fields mới được UPDATE (xem lý do ở update_sale_plan_status
    thời còn gộp chung — không dùng COALESCE vì không phân biệt được "không
    truyền" (giữ nguyên) với "truyền None" (xoá giá trị)). Khi 'contact_note'
    có mặt và không rỗng, tự set contacted_by/contacted_at."""
    set_parts, params = [], []
    for col in ("customer_id", "contact_note", "confirmed_sale_at", "selling_price", "delivery_time", "payment_method"):
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
    params.append(allocation_id)
    conn = get_connection(db_path)
    try:
        conn.execute(f"UPDATE sale_allocations SET {', '.join(set_parts)} WHERE id = ?", params)
        conn.commit()
    finally:
        conn.close()


def update_allocation_revenue_details(
    allocation_id: int, db_path: Path, ip: str | None, username: str | None, fields: dict
) -> None:
    """fields: dict con của {'paid_amount','weighing_ref','invoice_number'} —
    cùng cách "chỉ set field có mặt" như update_allocation_sale_details. Khi
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
    params.append(allocation_id)
    conn = get_connection(db_path)
    try:
        conn.execute(f"UPDATE sale_allocations SET {', '.join(set_parts)} WHERE id = ?", params)
        conn.commit()
    finally:
        conn.close()


def count_allocations_for_customer(customer_id: int, db_path: Path) -> int:
    conn = get_connection(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM sale_allocations WHERE customer_id = ?", (customer_id,)
        ).fetchone()[0]
    finally:
        conn.close()
