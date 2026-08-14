"""CRUD cho bảng farms/zones."""
from datetime import datetime
from pathlib import Path

from core.db import get_connection


def list_farms(db_path: Path) -> list[str]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute("SELECT code FROM farms ORDER BY id ASC").fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def create_farm(code: str, db_path: Path) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO farms (code, created_at) VALUES (?, ?)",
            (code, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()


def list_zones(farm: str, db_path: Path) -> list[str]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT code FROM zones WHERE farm = ? ORDER BY id ASC", (farm,)
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def create_zone(farm: str, code: str, db_path: Path) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO zones (farm, code, created_at) VALUES (?, ?, ?)",
            (farm, code, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()
