"""CRUD cho bảng sale_plans (kế hoạch xuất bán)."""
import sqlite3
from datetime import datetime
from pathlib import Path

from core.db import get_connection

# Trường hiển thị trên form/thẻ kế hoạch cho người dùng. created_by hiển thị
# để biết ai đã lập kế hoạch (phục vụ audit — nhiều người cùng dùng chung 1
# danh sách kế hoạch).
SALE_PLAN_VISIBLE_COLUMNS = [
    "id",
    "planned_date",
    "farm",
    "zone",
    "quantity",
    "target_price",
    "note",
    "status",
    "created_by",
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


def create_sale_plan(plan: dict, db_path: Path, ip: str | None = None, username: str | None = None) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO sale_plans (planned_date, farm, zone, quantity, target_price, note,
                                     status, created_at, created_ip, created_by,
                                     updated_at, updated_ip, updated_by)
            VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
            """,
            (
                plan["planned_date"],
                plan["farm"],
                plan.get("zone"),
                plan["quantity"],
                plan["target_price"],
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
        row = conn.execute(
            f"SELECT {', '.join(SALE_PLAN_ALL_COLUMNS)} FROM sale_plans WHERE id = ?",
            (plan_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_sale_plans(db_path: Path) -> list[dict]:
    if not db_path.exists():
        return []
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT {', '.join(SALE_PLAN_VISIBLE_COLUMNS)} FROM sale_plans "
            "WHERE status != 'deleted' ORDER BY planned_date ASC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_sale_plan_status(
    plan_id: int, status: str, db_path: Path, ip: str | None = None, username: str | None = None
) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE sale_plans SET status = ?, updated_at = ?, updated_ip = ?, updated_by = ? WHERE id = ?",
            (status, datetime.now().isoformat(timespec="seconds"), ip, username, plan_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_sale_plan(plan_id: int, db_path: Path) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM sale_plans WHERE id = ?", (plan_id,))
        conn.commit()
    finally:
        conn.close()
