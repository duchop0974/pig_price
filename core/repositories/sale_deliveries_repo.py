"""CRUD cho bảng sale_deliveries — mỗi lần XUẤT GIAO THỰC TẾ của 1 dòng hàng
(sale_allocations). 1 dòng hàng -> N lần xuất, nên đây là chỗ duy nhất biểu
diễn được "kế hoạch 100 loại 1 / thực tế 80 loại 1 + 20 loại 2" và "1 kế
hoạch xuất nhiều lần", mà không phải sửa số kế hoạch gốc.

sale_deliveries là NGUỒN SỰ THẬT cho mọi phép tính thực tế (xem
sale_plans_repo.py). sale_allocations.actual_quantity/actual_price giữ lại
nhưng chỉ còn là CACHE DẪN XUẤT 1 CHIỀU (đọc bởi export Excel + UI cũ), được
ghi lại từ đây qua _sync_allocation_actuals() — không bao giờ đọc ngược để
tính toán."""
import sqlite3
from datetime import datetime
from pathlib import Path

from core.db import get_connection

DELIVERY_VISIBLE_COLUMNS = [
    "id",
    "allocation_id",
    "pig_type_id",
    "quantity",
    "total_weight_kg",
    "unit_price",
    "delivered_date",
    "weighing_ref",
    "note",
    "locked_at",
    "locked_by",
    "created_by",
    "created_at",
]

_SELECT_JOINED = (
    "SELECT sd.id, sd.allocation_id, sd.pig_type_id, sd.quantity, sd.total_weight_kg, "
    "sd.unit_price, sd.delivered_date, sd.weighing_ref, sd.note, sd.locked_at, sd.locked_by, "
    "sd.created_by, sd.created_at, "
    "pt.code AS pig_type, pt.name AS pig_type_name, "
    "sa.sale_plan_id, sa.plan_code, sa.quantity AS line_quantity, "
    "so.id AS order_id, so.order_code, c.name AS customer_name "
    "FROM sale_deliveries sd "
    "LEFT JOIN pig_types pt ON pt.id = sd.pig_type_id "
    "JOIN sale_allocations sa ON sa.id = sd.allocation_id "
    "JOIN sale_orders so ON so.id = sa.order_id "
    "LEFT JOIN customers c ON c.id = so.customer_id"
)


def _sync_allocation_actuals(conn: sqlite3.Connection, allocation_id: int) -> None:
    """Ghi lại actual_quantity/actual_price của dòng hàng từ tổng các lần xuất.
    1 CHIỀU (deliveries -> allocation), không bao giờ ngược lại.

    actual_price = đơn giá bình quân GIA QUYỀN theo số lượng (không phải trung
    bình cộng) — 2 lần xuất 80 con @61.000 và 20 con @50.000 phải ra 58.800,
    không phải 55.500.

    Có `AND locked_at IS NULL`: dòng đã Data Freeze thì trigger
    trg_sale_allocations_lock_guard sẽ ABORT mọi UPDATE. Tầng route đã chặn từ
    trước (không cho tạo/xoá delivery trên dòng đã khoá) nên nhánh này thực tế
    không chạy, giữ ở đây làm lớp bảo vệ thứ 2 để hàm không bao giờ tự làm
    hỏng 1 transaction đang chạy."""
    conn.execute(
        """
        UPDATE sale_allocations
        SET actual_quantity = (SELECT SUM(sd.quantity) FROM sale_deliveries sd WHERE sd.allocation_id = ?),
            actual_price = (
                SELECT CAST(ROUND(
                    SUM(sd.unit_price * sd.quantity) * 1.0 / NULLIF(SUM(CASE WHEN sd.unit_price IS NULL THEN 0 ELSE sd.quantity END), 0)
                ) AS INTEGER)
                FROM sale_deliveries sd WHERE sd.allocation_id = ? AND sd.unit_price IS NOT NULL
            )
        WHERE id = ? AND locked_at IS NULL
        """,
        (allocation_id, allocation_id, allocation_id),
    )


def create_delivery(
    allocation_id: int,
    delivery: dict,
    db_path: Path,
    ip: str | None = None,
    username: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    own_connection = conn is None
    if own_connection:
        conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO sale_deliveries (allocation_id, pig_type_id, quantity, total_weight_kg,
                                          unit_price, delivered_date, weighing_ref, note,
                                          created_at, created_ip, created_by,
                                          updated_at, updated_ip, updated_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                allocation_id,
                delivery["pig_type_id"],
                delivery["quantity"],
                delivery.get("total_weight_kg"),
                delivery.get("unit_price"),
                delivery.get("delivered_date"),
                delivery.get("weighing_ref"),
                delivery.get("note"),
                now,
                ip,
                username,
                now,
                ip,
                username,
            ),
        )
        delivery_id = cur.lastrowid
        _sync_allocation_actuals(conn, allocation_id)
        if own_connection:
            conn.commit()
            return get_delivery(delivery_id, db_path)
        # conn dùng chung, transaction NGOÀI (service layer) chưa commit —
        # get_delivery() mở connection MỚI sẽ không thấy dòng vừa insert
        # (WAL chỉ lộ dữ liệu đã commit cho connection khác). Đọc lại bằng
        # CHÍNH conn, tự khôi phục row_factory sau khi dùng để không làm
        # lệch state của conn dùng chung cho các lệnh khác trong transaction.
        prev_row_factory = conn.row_factory
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(_SELECT_JOINED + " WHERE sd.id = ?", (delivery_id,)).fetchone()
        finally:
            conn.row_factory = prev_row_factory
        return dict(row) if row else None
    finally:
        if own_connection:
            conn.close()


def get_delivery(delivery_id: int, db_path: Path) -> dict | None:
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(_SELECT_JOINED + " WHERE sd.id = ?", (delivery_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_deliveries_for_allocation(allocation_id: int, db_path: Path) -> list[dict]:
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            _SELECT_JOINED + " WHERE sd.allocation_id = ? ORDER BY sd.delivered_date ASC, sd.id ASC",
            (allocation_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_deliveries_for_order(order_id: int, db_path: Path) -> list[dict]:
    """Mọi lần xuất của mọi dòng hàng thuộc 1 đơn — 1 query, lọc lại theo
    allocation_id ở tầng JS (cùng khuôn incident_repo.list_incidents_for_order,
    tránh N+1)."""
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            _SELECT_JOINED + " WHERE so.id = ? ORDER BY sd.delivered_date ASC, sd.id ASC",
            (order_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_deliveries(db_path: Path, farm_ids: list[int] | None = None) -> list[dict]:
    """Mọi lần xuất giao trong toàn hệ thống — dùng cho trang "Xuất giao"
    độc lập. `farm_ids=None`: không giới hạn trại (sales/accounting/admin/
    leadership). `farm_ids=[...]`: chỉ các trại đó (vai trò farm) — gọi
    với `farm_ids=[]` là lỗi (IN () rỗng không hợp lệ trong SQLite), tầng
    route phải tự chặn trả `[]` ngay, khớp quy ước
    sale_plans_repo.list_sale_plans()."""
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        sql = _SELECT_JOINED.replace(
            "sa.sale_plan_id, sa.plan_code, sa.quantity AS line_quantity, ",
            "sa.sale_plan_id, sa.plan_code, sa.quantity AS line_quantity, sp.farm_id, f.code AS farm, ",
        ).replace(
            "JOIN sale_allocations sa ON sa.id = sd.allocation_id",
            "JOIN sale_allocations sa ON sa.id = sd.allocation_id "
            "JOIN sale_plans sp ON sp.id = sa.sale_plan_id "
            "LEFT JOIN farms f ON f.id = sp.farm_id",
        )
        params: tuple = ()
        if farm_ids is not None:
            placeholders = ", ".join("?" * len(farm_ids))
            sql += f" WHERE sp.farm_id IN ({placeholders})"
            params = tuple(farm_ids)
        rows = conn.execute(
            sql + " ORDER BY sd.delivered_date DESC, sd.id DESC", params
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_deliveries_missing_weight(db_path: Path, farm_ids: list[int] | None = None, limit: int = 10) -> dict:
    """Exception Center (STEP 10): bản ghi xuất giao thiếu trọng lượng
    (total_weight_kg IS NULL) — vi phạm nguyên tắc "dữ liệu bất di bất
    dịch phải căn cứ theo kết quả cân thực tế" (CLAUDE.md mục I.1), ảnh
    hưởng độ chính xác báo cáo/đối soát. Copy đúng khuôn JOIN
    farm_id/farm của list_deliveries() ở trên để lọc/hiển thị theo trại."""
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        sql = _SELECT_JOINED.replace(
            "sa.sale_plan_id, sa.plan_code, sa.quantity AS line_quantity, ",
            "sa.sale_plan_id, sa.plan_code, sa.quantity AS line_quantity, sp.farm_id, f.code AS farm, ",
        ).replace(
            "JOIN sale_allocations sa ON sa.id = sd.allocation_id",
            "JOIN sale_allocations sa ON sa.id = sd.allocation_id "
            "JOIN sale_plans sp ON sp.id = sa.sale_plan_id "
            "LEFT JOIN farms f ON f.id = sp.farm_id",
        )
        where = "WHERE sd.total_weight_kg IS NULL"
        params: tuple = ()
        if farm_ids is not None:
            placeholders = ", ".join("?" * len(farm_ids))
            where += f" AND sp.farm_id IN ({placeholders})"
            params = tuple(farm_ids)
        total = conn.execute(
            f"SELECT COUNT(*) FROM ({sql} {where})", params
        ).fetchone()[0]
        rows = conn.execute(
            f"{sql} {where} ORDER BY sd.delivered_date ASC, sd.id ASC LIMIT ?", (*params, limit)
        ).fetchall()
        return {"total": total, "items": [dict(r) for r in rows]}
    finally:
        conn.close()


def list_deliveries_for_plan(sale_plan_id: int, db_path: Path) -> list[dict]:
    """Mọi lần xuất thuộc 1 kế hoạch trại, xuyên qua mọi đơn/khách hàng —
    dùng cho panel đối soát chi tiết của kế hoạch."""
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            _SELECT_JOINED + " WHERE sa.sale_plan_id = ? ORDER BY sd.delivered_date ASC, sd.id ASC",
            (sale_plan_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_delivery(
    delivery_id: int, db_path: Path, conn: sqlite3.Connection | None = None
) -> tuple[bool, str | None]:
    """Trả (đã xoá, thông báo lỗi). Từ chối khi bản ghi đã Data Freeze —
    kiểm tra ở đây thay vì để trigger ABORT vì DELETE không bị
    trg_sale_deliveries_lock_guard chặn (trigger chỉ bắt BEFORE UPDATE)."""
    own_connection = conn is None
    if own_connection:
        conn = get_connection(db_path)
    try:
        prev_row_factory = conn.row_factory
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT allocation_id, locked_at FROM sale_deliveries WHERE id = ?", (delivery_id,)
        ).fetchone()
        conn.row_factory = prev_row_factory
        if row is None:
            return False, "Không tìm thấy bản ghi xuất giao."
        if row["locked_at"]:
            return False, "Bản ghi đã khoá vĩnh viễn, không thể xoá."
        allocation_id = row["allocation_id"]
        conn.execute("DELETE FROM sale_deliveries WHERE id = ?", (delivery_id,))
        _sync_allocation_actuals(conn, allocation_id)
        if own_connection:
            conn.commit()
        return True, None
    finally:
        if own_connection:
            conn.close()


def sum_delivered_for_plan(sale_plan_id: int, db_path: Path) -> int:
    """Tổng số con đã xuất của 1 kế hoạch (chỉ đơn active/done — trùng bộ lọc
    _DELIVERY_FROM_SQL ở sale_plans_repo.py). Route dùng để chặn xuất vượt kế
    hoạch trước khi ghi."""
    conn = get_connection(db_path)
    try:
        return conn.execute(
            "SELECT COALESCE(SUM(sd.quantity), 0) FROM sale_deliveries sd "
            "JOIN sale_allocations sa ON sa.id = sd.allocation_id "
            "JOIN sale_orders so ON so.id = sa.order_id "
            "WHERE sa.sale_plan_id = ? AND so.status IN ('active','done')",
            (sale_plan_id,),
        ).fetchone()[0]
    finally:
        conn.close()


def count_deliveries_for_pig_type(pig_type_id: int, db_path: Path) -> int:
    """Số lần xuất đang tham chiếu loại heo này — chặn admin xoá danh mục loại
    heo còn được dùng. Cần riêng (không gộp count_plans_for_pig_type) vì cả
    tính năng này sinh ra để delivery mang loại CHƯA từng có trong kế hoạch
    nào: loại đó có count_plans_for_pig_type = 0 nhưng vẫn đang được dùng thật."""
    conn = get_connection(db_path)
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM sale_deliveries WHERE pig_type_id = ?", (pig_type_id,)
        ).fetchone()[0]
    finally:
        conn.close()
