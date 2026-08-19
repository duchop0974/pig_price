"""Ghi & đọc lịch sử hoạt động (đăng nhập, tạo/sửa/xóa kế hoạch...)."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from core.db import get_connection


def _json_or_none(value: dict | None) -> str | None:
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def log_action(
    action: str,
    db_path: Path,
    username: str | None = None,
    detail: str | None = None,
    ip: str | None = None,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    old_value: dict | None = None,
    new_value: dict | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    own_connection = conn is None

    if own_connection:
        conn = get_connection(db_path)

    try:
        conn.execute(
            """
            INSERT INTO audit_log (
                at,
                username,
                action,
                entity_type,
                entity_id,
                old_value,
                new_value,
                detail,
                ip
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().astimezone().isoformat(timespec="seconds"),
                username,
                action,
                entity_type,
                str(entity_id) if entity_id is not None else None,
                _json_or_none(old_value),
                _json_or_none(new_value),
                detail,
                ip,
            ),
        )

        if own_connection:
            conn.commit()

    finally:
        if own_connection:
            conn.close()


def list_audit_log(
    db_path: Path,
    limit: int = 200,
    offset: int = 0,
    username: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """date_from/date_to: chuỗi 'YYYY-MM-DD', lọc theo cột at (ISO datetime nên
    so sánh chuỗi trực tiếp là đủ, không cần parse)."""
    where, params = _build_filter(username, action, entity_type, entity_id, date_from, date_to)
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT at, username, action, entity_type, entity_id, old_value, new_value, detail, ip "
            f"FROM audit_log{where} ORDER BY id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def count_audit_log(
    db_path: Path,
    username: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> int:
    where, params = _build_filter(username, action, entity_type, entity_id, date_from, date_to)
    conn = get_connection(db_path)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM audit_log{where}", params).fetchone()[0]
    finally:
        conn.close()


def _build_filter(
    username: str | None,
    action: str | None,
    entity_type: str | None,
    entity_id: int | str | None,
    date_from: str | None,
    date_to: str | None,
) -> tuple[str, list]:
    clauses = []
    params: list = []
    if username:
        clauses.append("username = ?")
        params.append(username)
    if action:
        clauses.append("action = ?")
        params.append(action)
    if entity_type:
        clauses.append("entity_type = ?")
        params.append(entity_type)
    if entity_id is not None:
        clauses.append("entity_id = ?")
        params.append(str(entity_id))
    if date_from:
        clauses.append("at >= ?")
        params.append(date_from)
    if date_to:
        # date_to là ngày (không giờ) — cộng thêm 'T23:59:59' để bao trọn cả
        # ngày đó thay vì chỉ khớp đúng lúc 00:00:00. So sánh chuỗi ISO vẫn
        # đúng thứ tự thời gian miễn offset timezone nhất quán giữa các dòng
        # (server không đổi timezone giữa chừng).
        clauses.append("at <= ?")
        params.append(f"{date_to}T23:59:59")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return where, params
