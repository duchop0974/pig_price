"""CRUD cho bảng incident_reports — hiện chỉ dùng để ghi nhận heo Loại/Hủy
(kind='culled'/'cancelled') gắn với 1 dòng hàng (sale_allocations), kèm ảnh
bằng chứng qua media_proof (entity_type='incident', entity_id=incident.id).
Không đụng tới sale_allocations.actual_quantity — chỉ ghi nhận độc lập để
đối chiếu trực quan ở tầng UI (kế hoạch − Σloại − Σhủy)."""
import sqlite3
from datetime import datetime
from pathlib import Path

from core.db import get_connection

KIND_CULLED = "culled"
KIND_CANCELLED = "cancelled"
VALID_KINDS = (KIND_CULLED, KIND_CANCELLED)

INCIDENT_VISIBLE_COLUMNS = [
    "id",
    "allocation_id",
    "kind",
    "quantity",
    "description",
    "status",
    "reported_by",
    "reported_at",
]


def get_allocation_for_incident(allocation_id: int, db_path: Path) -> dict | None:
    """order_id + quantity của 1 dòng hàng — route dùng để validate dòng
    hàng thuộc đúng đơn (URL truyền cả order_id lẫn line_id) và chặn nhập
    quantity loại/hủy vượt quá số lượng của dòng."""
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, order_id, quantity FROM sale_allocations WHERE id = ?", (allocation_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_incident(
    allocation_id: int,
    kind: str,
    quantity: int,
    description: str,
    db_path: Path,
    reported_by: str | None = None,
    ip: str | None = None,
) -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO incident_reports (allocation_id, kind, quantity, description, status,
                                           reported_by, reported_at, created_at, created_ip, updated_at, updated_ip)
            VALUES (?, ?, ?, ?, 'reported', ?, ?, ?, ?, ?, ?)
            """,
            (allocation_id, kind, quantity, description, reported_by, now, now, ip, now, ip),
        )
        conn.commit()
        incident_id = cur.lastrowid
    finally:
        conn.close()
    return get_incident(incident_id, db_path)


def get_incident(incident_id: int, db_path: Path) -> dict | None:
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT " + ", ".join(INCIDENT_VISIBLE_COLUMNS) + " FROM incident_reports WHERE id = ?",
            (incident_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_incidents_for_order(order_id: int, db_path: Path) -> list[dict]:
    """Mọi incident của mọi dòng hàng thuộc 1 đơn — 1 query, dùng render
    breakdown Loại/Hủy trên order card (mỗi dòng lọc lại theo allocation_id
    ở tầng JS)."""
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT " + ", ".join(f"ir.{c}" for c in INCIDENT_VISIBLE_COLUMNS)
            + " FROM incident_reports ir JOIN sale_allocations sa ON sa.id = ir.allocation_id"
            " WHERE sa.order_id = ? ORDER BY ir.reported_at ASC",
            (order_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_incident(incident_id: int, db_path: Path) -> bool:
    """Xoá bản ghi incident — KHÔNG xoá ảnh media_proof/file trên đĩa đã
    gắn với nó (giữ evidence trail dù bản ghi chính bị xoá)."""
    conn = get_connection(db_path)
    try:
        cur = conn.execute("DELETE FROM incident_reports WHERE id = ?", (incident_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
