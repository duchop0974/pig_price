"""CRUD cho bảng sale_plan_reconciliations — đối soát phần chênh lệch giữa
kế hoạch trại (sale_plans.quantity) và thực tế đã bán (actual_sold_quantity,
xem core/repositories/sale_plans_repo.py). Khác incident_reports (gắn
allocation_id, 1 dòng hàng cụ thể): bảng này gắn thẳng sale_plan_id, dùng
cho cả phần số lượng CHƯA từng được đưa vào đơn nào (không có allocation_id
để gắn). Ảnh bằng chứng (bắt buộc với kind culled/cancelled) qua
media_proof dùng chung, entity_type='plan_reconciliation'.

kind chốt (transferred/culled/cancelled/other) tính vào reconciled_quantity
— đóng kế hoạch. kind ghi nhận (still_at_farm/continue_selling) KHÔNG tính
vào reconciled_quantity — vẫn còn heo/còn bán, chưa thể coi là xử lý xong."""
import sqlite3
from datetime import datetime
from pathlib import Path

from core.db import get_connection

KIND_STILL_AT_FARM = "still_at_farm"
KIND_CONTINUE_SELLING = "continue_selling"
KIND_TRANSFERRED = "transferred"
KIND_CULLED = "culled"
KIND_CANCELLED = "cancelled"
KIND_OTHER = "other"

VALID_KINDS = (
    KIND_STILL_AT_FARM,
    KIND_CONTINUE_SELLING,
    KIND_TRANSFERRED,
    KIND_CULLED,
    KIND_CANCELLED,
    KIND_OTHER,
)
# Kind "chốt" — tính vào reconciled_quantity, có thể khép kín kế hoạch.
TERMINAL_KINDS = (KIND_TRANSFERRED, KIND_CULLED, KIND_CANCELLED, KIND_OTHER)
# Kind bắt buộc ảnh bằng chứng — khớp quy tắc incident_reports hiện có.
PHOTO_REQUIRED_KINDS = (KIND_CULLED, KIND_CANCELLED)

RECONCILIATION_VISIBLE_COLUMNS = [
    "id",
    "sale_plan_id",
    "kind",
    "quantity",
    "reason",
    "reported_by",
    "reported_at",
]


def create_reconciliation(
    sale_plan_id: int,
    kind: str,
    quantity: int,
    reason: str,
    db_path: Path,
    reported_by: str | None = None,
    ip: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    own_connection = conn is None
    if own_connection:
        conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO sale_plan_reconciliations (sale_plan_id, kind, quantity, reason,
                                                     reported_by, reported_at, created_at, created_ip, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (sale_plan_id, kind, quantity, reason, reported_by, now, now, ip, reported_by),
        )
        if own_connection:
            conn.commit()
        reconciliation_id = cur.lastrowid
        # Đọc lại bằng CHÍNH conn vừa insert (không mở connection mới như
        # get_reconciliation() làm) — nếu conn là transaction dùng chung
        # (own_connection=False) và chưa commit, 1 connection khác sẽ KHÔNG
        # thấy được dòng vừa insert (WAL chỉ cho đọc dữ liệu ĐÃ commit).
        # Dùng dict(zip(...)) thay vì conn.row_factory=sqlite3.Row để không
        # làm lệch row_factory của connection dùng chung cho các lệnh khác
        # trong cùng transaction.
        row = conn.execute(
            "SELECT " + ", ".join(RECONCILIATION_VISIBLE_COLUMNS) + " FROM sale_plan_reconciliations WHERE id = ?",
            (reconciliation_id,),
        ).fetchone()
        return dict(zip(RECONCILIATION_VISIBLE_COLUMNS, row)) if row else None
    finally:
        if own_connection:
            conn.close()


def get_reconciliation(reconciliation_id: int, db_path: Path) -> dict | None:
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT " + ", ".join(RECONCILIATION_VISIBLE_COLUMNS) + " FROM sale_plan_reconciliations WHERE id = ?",
            (reconciliation_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_reconciliations_for_plan(sale_plan_id: int, db_path: Path) -> list[dict]:
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT " + ", ".join(RECONCILIATION_VISIBLE_COLUMNS)
            + " FROM sale_plan_reconciliations WHERE sale_plan_id = ? ORDER BY reported_at ASC",
            (sale_plan_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_reconciliation(
    reconciliation_id: int, db_path: Path, conn: sqlite3.Connection | None = None
) -> bool:
    """Xoá bản ghi đối soát — KHÔNG xoá ảnh media_proof/file trên đĩa đã gắn
    với nó (giữ evidence trail dù bản ghi chính bị xoá), khớp delete_incident."""
    own_connection = conn is None
    if own_connection:
        conn = get_connection(db_path)
    try:
        cur = conn.execute("DELETE FROM sale_plan_reconciliations WHERE id = ?", (reconciliation_id,))
        if own_connection:
            conn.commit()
        return cur.rowcount > 0
    finally:
        if own_connection:
            conn.close()
