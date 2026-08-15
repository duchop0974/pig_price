"""CRUD cho bảng sale_plans (kế hoạch trại — nguồn cung heo, BM01).

Kế hoạch bán (Phòng bán hàng "nhặt" số lượng/giá từ kế hoạch trại để bán cho
khách, BM02) nằm ở bảng/repo riêng: sale_allocations_repo.py."""
import sqlite3
from datetime import datetime
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
    "zone",
    "shed",
    "lot",
    "pig_type",
    "pig_type_name",
    "quantity",
    "received_quantity",
    "received_at",
    "received_by",
    "allocated_quantity",
    "remaining_quantity",
    "note",
    "status",
    "created_by",
    "approved_by",
    "approved_at",
    "rejected_by",
    "rejected_at",
    "rejected_reason",
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

# allocated_quantity = tổng quantity của các kế hoạch bán đang active/done
# tham chiếu tới kế hoạch trại này; remaining_quantity = quantity trại đăng
# ký - allocated_quantity. Tính động (subquery), không lưu cột riêng để
# tránh lệch dữ liệu khi allocation bị huỷ/vô hiệu hoá.
_ALLOCATED_SQL = (
    "COALESCE((SELECT SUM(sa.quantity) FROM sale_allocations sa "
    "WHERE sa.sale_plan_id = sp.id AND sa.status IN ('active','done')), 0)"
)

_SELECT_VISIBLE = (
    "SELECT sp.id, sp.plan_code, sp.planned_date, sp.farm_id, f.code AS farm, f.province AS province, "
    "z.code AS zone, sp.shed, sp.lot, pt.code AS pig_type, pt.name AS pig_type_name, sp.quantity, "
    "sp.received_quantity, sp.received_at, sp.received_by, "
    f"{_ALLOCATED_SQL} AS allocated_quantity, sp.quantity - {_ALLOCATED_SQL} AS remaining_quantity, "
    "sp.note, sp.status, sp.created_by, "
    "sp.approved_by, sp.approved_at, sp.rejected_by, sp.rejected_at, sp.rejected_reason"
    + _JOIN_SQL
)

_SELECT_ALL = (
    "SELECT sp.id, sp.plan_code, sp.planned_date, sp.farm_id, f.code AS farm, f.province AS province, "
    "z.code AS zone, sp.shed, sp.lot, pt.code AS pig_type, pt.name AS pig_type_name, sp.quantity, "
    "sp.received_quantity, sp.received_at, sp.received_by, "
    f"{_ALLOCATED_SQL} AS allocated_quantity, sp.quantity - {_ALLOCATED_SQL} AS remaining_quantity, "
    "sp.note, sp.status, sp.created_by, "
    "sp.approved_by, sp.approved_at, sp.rejected_by, sp.rejected_at, sp.rejected_reason, "
    "sp.created_at, sp.created_ip, sp.updated_at, sp.updated_ip, sp.updated_by"
    + _JOIN_SQL
)


def _next_plan_code(conn: sqlite3.Connection, farm_id: int, planned_date: str) -> str:
    """Sinh mã kế hoạch <mã trại>-<ngày dự kiến>-<số thứ tự trong ngày của
    trại đó>, VD: XH1-20260820-01. An toàn không đụng hàng: create_sale_plan
    luôn chạy trong db_lock của cả app (xem data_access.py) nên không có 2
    lời gọi tạo kế hoạch chạy song song để đếm ra cùng 1 số thứ tự."""
    farm_code = conn.execute("SELECT code FROM farms WHERE id = ?", (farm_id,)).fetchone()[0]
    seq = (
        conn.execute(
            "SELECT COUNT(*) FROM sale_plans WHERE farm_id = ? AND planned_date = ?",
            (farm_id, planned_date),
        ).fetchone()[0]
        + 1
    )
    return f"{farm_code}-{planned_date.replace('-', '')}-{seq:02d}"


def create_sale_plan(plan: dict, db_path: Path, ip: str | None = None, username: str | None = None) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection(db_path)
    try:
        plan_code = _next_plan_code(conn, plan["farm_id"], plan["planned_date"])
        cur = conn.execute(
            """
            INSERT INTO sale_plans (plan_code, planned_date, farm_id, zone_id, shed, lot, pig_type_id, quantity,
                                     note, status, created_at, created_ip, created_by,
                                     updated_at, updated_ip, updated_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_approval', ?, ?, ?, ?, ?, ?)
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
                plan.get("note"),
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


def get_sale_plan(plan_id: int, db_path: Path) -> dict | None:
    if not db_path.exists():
        return None
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(_SELECT_ALL + " WHERE sp.id = ?", (plan_id,)).fetchone()
        return dict(row) if row else None
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
        return [dict(r) for r in rows]
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
) -> None:
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
        conn.commit()
    finally:
        conn.close()


def approve_sale_plan(plan_id: int, db_path: Path, ip: str | None = None, username: str | None = None) -> None:
    """Duyệt kế hoạch đang chờ. Điều kiện status='pending_approval' trong
    WHERE là lớp bảo vệ thứ 2 (ngoài check ở route) chống duyệt trùng/duyệt
    sai trạng thái."""
    now = datetime.now().isoformat(timespec="seconds")
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
        conn.commit()
    finally:
        conn.close()


def reject_sale_plan(
    plan_id: int, reason: str, db_path: Path, ip: str | None = None, username: str | None = None
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
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
        conn.commit()
    finally:
        conn.close()


def update_plan_received_quantity(
    plan_id: int, received_quantity: int, db_path: Path, ip: str | None = None, username: str | None = None
) -> None:
    """Trại tự ghi nhận số lượng thực tế đã xuất chuồng/bàn giao ra nhà chờ
    bán (BM01/QT001 bước B6). Ghi đè giá trị (không cộng dồn) — mỗi lần trại
    xuất chuồng thêm thì tự nhập lại tổng số mới."""
    now = datetime.now().isoformat(timespec="seconds")
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
        conn.commit()
    finally:
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


def dashboard_stats(db_path: Path, farm_ids: list[int] | None = None) -> dict:
    """Số liệu tổng quan cho trang chủ. farm_ids=None: không giới hạn theo
    trại (sales/accounting/admin/leadership). farm_ids=[]: vai trò farm chưa
    được gán trại nào -> trả toàn 0, khỏi query.

    sold_this_month/revenue_this_month giờ tính trên sale_allocations (kế
    hoạch bán) — "đã bán"/"doanh thu" không còn là khái niệm ở cấp kế hoạch
    trại nữa. approved_not_sold đổi nghĩa: kế hoạch trại đã duyệt còn
    remaining_quantity > 0 (chưa phân bổ hết cho kế hoạch bán nào)."""
    if farm_ids is not None and not farm_ids:
        return {
            "pending_approval": 0,
            "approved_not_sold": 0,
            "sold_this_month": 0,
            "revenue_this_month": 0,
        }
    conn = get_connection(db_path)
    try:
        where, params = "", ()
        if farm_ids is not None:
            where = f" AND sp.farm_id IN ({', '.join('?' * len(farm_ids))})"
            params = tuple(farm_ids)
        month = datetime.now().strftime("%Y-%m")
        pending_approval = conn.execute(
            f"SELECT COUNT(*) FROM sale_plans sp WHERE sp.status = 'pending_approval'{where}", params
        ).fetchone()[0]
        approved_not_sold = conn.execute(
            f"""
            SELECT COUNT(*) FROM sale_plans sp
            WHERE sp.status = 'approved'{where}
              AND sp.quantity - {_ALLOCATED_SQL} > 0
            """,
            params,
        ).fetchone()[0]
        sold_this_month = conn.execute(
            f"""
            SELECT COUNT(*) FROM sale_allocations sa
            JOIN sale_plans sp ON sp.id = sa.sale_plan_id
            WHERE sa.status = 'done' AND substr(sp.planned_date, 1, 7) = ?{where}
            """,
            (month, *params),
        ).fetchone()[0]
        revenue_this_month = conn.execute(
            f"""
            SELECT COALESCE(SUM(sa.paid_amount), 0) FROM sale_allocations sa
            JOIN sale_plans sp ON sp.id = sa.sale_plan_id
            WHERE sa.paid_amount IS NOT NULL AND substr(sa.paid_at, 1, 7) = ?{where}
            """,
            (month, *params),
        ).fetchone()[0]
        return {
            "pending_approval": pending_approval,
            "approved_not_sold": approved_not_sold,
            "sold_this_month": sold_this_month,
            "revenue_this_month": revenue_this_month,
        }
    finally:
        conn.close()
