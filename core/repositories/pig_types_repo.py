"""CRUD cho bảng pig_types (danh mục loại heo bán) — chỉ admin được thêm."""
import sqlite3
from datetime import datetime
from pathlib import Path

from core.db import get_connection


def list_pig_types(db_path: Path, active_only: bool = False) -> list[dict]:
    conn = get_connection(db_path)
    try:
        sql = "SELECT id, code, name, is_active, created_at FROM pig_types"
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY id ASC"
        rows = conn.execute(sql).fetchall()
        return [
            {"id": r[0], "code": r[1], "name": r[2], "is_active": bool(r[3]), "created_at": r[4]}
            for r in rows
        ]
    finally:
        conn.close()


def create_pig_type(code: str, name: str, db_path: Path) -> int:
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO pig_types (code, name, is_active, created_at) VALUES (?, ?, 1, ?)",
            (code, name, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def set_pig_type_active(pig_type_id: int, is_active: bool, db_path: Path) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE pig_types SET is_active = ? WHERE id = ?", (1 if is_active else 0, pig_type_id)
        )
        conn.commit()
    finally:
        conn.close()


def get_pig_type(pig_type_id: int, db_path: Path) -> dict | None:
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, code, name, is_active, created_at FROM pig_types WHERE id = ?",
            (pig_type_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_pig_type(pig_type_id: int, code: str, name: str, db_path: Path) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE pig_types SET code = ?, name = ? WHERE id = ?", (code, name, pig_type_id)
        )
        conn.commit()
    finally:
        conn.close()


def delete_pig_type(pig_type_id: int, db_path: Path) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM pig_types WHERE id = ?", (pig_type_id,))
        conn.commit()
    finally:
        conn.close()
