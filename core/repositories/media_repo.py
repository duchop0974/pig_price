"""CRUD cho bảng media_proof (ảnh/video bằng chứng — cân bì, cân heo, biên
bản bàn giao, sự cố...), generic theo entity_type/entity_id.

Framework-agnostic: nhận bytes thay vì đối tượng FileStorage của Flask, vì
core/ dùng chung cho CLI và web (xem README). Tầng route chịu trách nhiệm
đọc file upload thành bytes trước khi gọi save_upload()."""
import hashlib
import mimetypes
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from core.db import get_connection

MEDIA_VISIBLE_COLUMNS = [
    "id",
    "entity_type",
    "entity_id",
    "kind",
    "file_path",
    "file_size",
    "mime_type",
    "checksum_sha256",
    "note",
    "uploaded_by",
    "uploaded_at",
    "uploaded_ip",
]

_SELECT = "SELECT " + ", ".join(MEDIA_VISIBLE_COLUMNS) + " FROM media_proof"


def _guess_extension(original_filename: str | None, mime_type: str | None) -> str:
    if original_filename and "." in original_filename:
        return "." + original_filename.rsplit(".", 1)[-1].lower()
    if mime_type:
        ext = mimetypes.guess_extension(mime_type)
        if ext:
            return ext
    return ".bin"


def _find_by_checksum(checksum: str, db_path: Path) -> list[dict]:
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            _SELECT + " WHERE checksum_sha256 = ? ORDER BY uploaded_at ASC",
            (checksum,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def save_upload(
    file_bytes: bytes,
    entity_type: str,
    entity_id: str | int,
    kind: str,
    media_root: Path,
    db_path: Path,
    uploaded_by: str | None = None,
    uploaded_ip: str | None = None,
    original_filename: str | None = None,
    mime_type: str | None = None,
    note: str | None = None,
) -> dict:
    """Ghi file xuống đĩa dưới media_root/<entity_type>/<entity_id>/, ghi
    dòng media_proof tương ứng, và báo nếu bytes trùng với ảnh đã upload
    trước đó (checksum_sha256) — chỉ CẢNH BÁO MỀM (is_duplicate), tầng route
    tự quyết định có chặn request hay không, hàm này không tự raise."""
    checksum = hashlib.sha256(file_bytes).hexdigest()
    duplicates = _find_by_checksum(checksum, db_path)

    ext = _guess_extension(original_filename, mime_type)
    filename = f"{uuid.uuid4().hex}_{kind}{ext}"
    relative_path = f"{entity_type}/{entity_id}/{filename}"
    absolute_path = media_root / relative_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    absolute_path.write_bytes(file_bytes)

    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO media_proof (entity_type, entity_id, kind, file_path, file_size, mime_type,
                                      checksum_sha256, note, uploaded_by, uploaded_at, uploaded_ip)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity_type,
                str(entity_id),
                kind,
                relative_path,
                len(file_bytes),
                mime_type,
                checksum,
                note,
                uploaded_by,
                now,
                uploaded_ip,
            ),
        )
        conn.commit()
        media_id = cur.lastrowid
    finally:
        conn.close()

    return {
        "id": media_id,
        "file_path": relative_path,
        "checksum_sha256": checksum,
        "is_duplicate": len(duplicates) > 0,
        "duplicate_media_ids": [d["id"] for d in duplicates],
    }


def get_media(media_id: int, db_path: Path) -> dict | None:
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(_SELECT + " WHERE id = ?", (media_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_media_for_entity(entity_type: str, entity_id: str | int, db_path: Path) -> list[dict]:
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            _SELECT + " WHERE entity_type = ? AND entity_id = ? ORDER BY uploaded_at ASC",
            (entity_type, str(entity_id)),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
