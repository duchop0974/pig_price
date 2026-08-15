"""CRUD cho bảng farms/zones."""
from datetime import datetime
from pathlib import Path

from core.db import get_connection


def list_farms(db_path: Path) -> list[dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute("SELECT id, code, province FROM farms ORDER BY id ASC").fetchall()
        return [{"id": r[0], "code": r[1], "province": r[2]} for r in rows]
    finally:
        conn.close()


def create_farm(code: str, province: str | None, db_path: Path) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO farms (code, province, created_at) VALUES (?, ?, ?)",
            (code, province, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()


def list_zones(farm_id: int, db_path: Path) -> list[dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT id, code FROM zones WHERE farm_id = ? ORDER BY id ASC", (farm_id,)
        ).fetchall()
        return [{"id": r[0], "code": r[1]} for r in rows]
    finally:
        conn.close()


def create_zone(farm_id: int, code: str, db_path: Path) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO zones (farm_id, code, created_at) VALUES (?, ?, ?)",
            (farm_id, code, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()


def get_farm(farm_id: int, db_path: Path) -> dict | None:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT id, code, province FROM farms WHERE id = ?", (farm_id,)
        ).fetchone()
        return {"id": row[0], "code": row[1], "province": row[2]} if row else None
    finally:
        conn.close()


def update_farm(farm_id: int, code: str, province: str | None, db_path: Path) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE farms SET code = ?, province = ? WHERE id = ?", (code, province, farm_id)
        )
        conn.commit()
    finally:
        conn.close()


def delete_farm(farm_id: int, db_path: Path) -> None:
    """Xóa trang trại và toàn bộ khu thuộc trang trại đó. Gọi hàm này chỉ
    sau khi đã xác nhận (ở tầng route) không còn kế hoạch xuất bán nào tham
    chiếu farm_id — mọi kế hoạch đều gắn farm_id trực tiếp nên kiểm tra đó
    đã bao trùm luôn các khu con."""
    conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM zones WHERE farm_id = ?", (farm_id,))
        conn.execute("DELETE FROM farms WHERE id = ?", (farm_id,))
        conn.commit()
    finally:
        conn.close()


def get_zone(zone_id: int, db_path: Path) -> dict | None:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT id, farm_id, code FROM zones WHERE id = ?", (zone_id,)
        ).fetchone()
        return {"id": row[0], "farm_id": row[1], "code": row[2]} if row else None
    finally:
        conn.close()


def update_zone(zone_id: int, code: str, db_path: Path) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute("UPDATE zones SET code = ? WHERE id = ?", (code, zone_id))
        conn.commit()
    finally:
        conn.close()


def delete_zone(zone_id: int, db_path: Path) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM zones WHERE id = ?", (zone_id,))
        conn.commit()
    finally:
        conn.close()
