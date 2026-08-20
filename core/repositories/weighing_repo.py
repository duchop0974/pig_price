"""CRUD cho bảng weighing_records (cân bì không tải -> cân xe chở heo ->
chốt) và khoá vĩnh viễn (Data Freeze) dùng chung cho các bảng đã có trigger
BEFORE UPDATE (xem core/db.py: trg_weighing_records_lock_guard,
trg_sale_plans_lock_guard, trg_sale_allocations_lock_guard).

QUAN TRỌNG: công ty đã có phần mềm cân riêng ở trạm cân, tự lưu trữ mã cân +
chi tiết đầy đủ mỗi lần cân — app này CHƯA có API đọc trực tiếp từ đó. Vì
vậy *_ticket_code (mã phiếu cân bì/cân heo) là NGUỒN SỰ THẬT và bắt buộc
nhập; *_weight_kg (số cân gõ tay) và ảnh chụp chỉ là dữ liệu đối chiếu/bằng
chứng bổ sung, tuỳ chọn — không dùng để đối soát thay cho phần mềm cân.

Mỗi bước (record_tare/record_gross/confirm_weighing) tự chặn theo status
trong mệnh đề WHERE — cùng mẫu với sale_plans_repo.approve_sale_plan/
reject_sale_plan (WHERE status = 'pending_approval') — nên gọi sai thứ tự sẽ
không UPDATE được dòng nào (rowcount = 0) thay vì âm thầm ghi đè."""
import sqlite3
from datetime import datetime
from pathlib import Path

from core.db import get_connection

WEIGHING_RECORD_COLUMNS = [
    "id",
    "sale_allocation_id",
    "farm_id",
    "vehicle_plate",
    "tare_weight_kg",
    "tare_ticket_code",
    "tare_photo_media_id",
    "tare_recorded_by",
    "tare_recorded_at",
    "gross_weight_kg",
    "gross_ticket_code",
    "gross_photo_media_id",
    "gross_recorded_by",
    "gross_recorded_at",
    "net_weight_kg",
    "status",
    "locked_at",
    "locked_by",
    "created_at",
    "created_ip",
    "created_by",
    "updated_at",
    "updated_ip",
    "updated_by",
]

_SELECT = "SELECT " + ", ".join(WEIGHING_RECORD_COLUMNS) + " FROM weighing_records"

# Bảng có trigger BEFORE UPDATE khoá vĩnh viễn — whitelist tránh SQL
# injection qua tên bảng khi lock_record() build câu UPDATE bằng f-string.
LOCKABLE_TABLES = {"sale_plans", "sale_allocations", "weighing_records", "sale_orders", "sale_deliveries"}


def create_weighing_record(
    sale_allocation_id: int,
    farm_id: int,
    vehicle_plate: str | None,
    db_path: Path,
    ip: str | None = None,
    username: str | None = None,
) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO weighing_records (sale_allocation_id, farm_id, vehicle_plate, status,
                                           created_at, created_ip, created_by, updated_at, updated_ip, updated_by)
            VALUES (?, ?, ?, 'awaiting_tare', ?, ?, ?, ?, ?, ?)
            """,
            (sale_allocation_id, farm_id, vehicle_plate, now, ip, username, now, ip, username),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def record_tare(
    weighing_record_id: int,
    tare_ticket_code: str,
    db_path: Path,
    tare_weight_kg: int | None = None,
    tare_photo_media_id: int | None = None,
    ip: str | None = None,
    username: str | None = None,
) -> bool:
    """tare_ticket_code (mã phiếu cân bì từ phần mềm cân riêng của trạm cân)
    là NGUỒN SỰ THẬT, bắt buộc. tare_weight_kg/tare_photo_media_id chỉ là
    thông tin đối chiếu nhanh, tuỳ chọn — không thay thế phần mềm cân.
    Trả về False (không sửa gì) nếu dòng không ở status='awaiting_tare' —
    chặn ghi đè cân bì đã xác nhận hoặc bỏ qua bước cân bì."""
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """
            UPDATE weighing_records
            SET tare_weight_kg = ?, tare_ticket_code = ?, tare_photo_media_id = ?,
                tare_recorded_by = ?, tare_recorded_at = ?, status = 'tare_done',
                updated_at = ?, updated_ip = ?, updated_by = ?
            WHERE id = ? AND status = 'awaiting_tare'
            """,
            (tare_weight_kg, tare_ticket_code, tare_photo_media_id, username, now, now, ip, username, weighing_record_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def record_gross(
    weighing_record_id: int,
    gross_ticket_code: str,
    db_path: Path,
    gross_weight_kg: int | None = None,
    gross_photo_media_id: int | None = None,
    ip: str | None = None,
    username: str | None = None,
) -> bool:
    """gross_ticket_code (mã phiếu cân xe chở heo từ phần mềm cân riêng) là
    NGUỒN SỰ THẬT, bắt buộc. gross_weight_kg/gross_photo_media_id chỉ là
    thông tin đối chiếu nhanh, tuỳ chọn.
    Trả về False nếu dòng chưa ở status='tare_done' (chưa cân bì hoặc đã
    cân xe rồi) — chốt chặn bắt buộc cân bì trước cân xe (đặc biệt XH2/XH3)."""
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """
            UPDATE weighing_records
            SET gross_weight_kg = ?, gross_ticket_code = ?, gross_photo_media_id = ?,
                gross_recorded_by = ?, gross_recorded_at = ?, status = 'gross_done',
                updated_at = ?, updated_ip = ?, updated_by = ?
            WHERE id = ? AND status = 'tare_done'
            """,
            (gross_weight_kg, gross_ticket_code, gross_photo_media_id, username, now, now, ip, username, weighing_record_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def confirm_weighing(
    weighing_record_id: int,
    db_path: Path,
    ip: str | None = None,
    username: str | None = None,
) -> bool:
    """Chốt cân: tính net_weight_kg, chuyển status='confirmed' VÀ khoá vĩnh
    viễn (locked_at/locked_by) trong CÙNG một câu UPDATE — khoá có hiệu lực
    ngay khi chốt, không có khoảng hở giữa "confirmed" và "locked". Trả về
    False nếu dòng chưa ở status='gross_done' hoặc đã bị khoá từ trước."""
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """
            UPDATE weighing_records
            SET net_weight_kg = gross_weight_kg - tare_weight_kg, status = 'confirmed',
                locked_at = ?, locked_by = ?, updated_at = ?, updated_ip = ?, updated_by = ?
            WHERE id = ? AND status = 'gross_done' AND locked_at IS NULL
            """,
            (now, username, now, ip, username, weighing_record_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_weighing_record(weighing_record_id: int, db_path: Path) -> dict | None:
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(_SELECT + " WHERE id = ?", (weighing_record_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_weighing_records_for_allocation(sale_allocation_id: int, db_path: Path) -> list[dict]:
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            _SELECT + " WHERE sale_allocation_id = ? ORDER BY created_at ASC",
            (sale_allocation_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def lock_record(
    table: str,
    record_id: int,
    db_path: Path,
    ip: str | None = None,
    username: str | None = None,
    conn=None,
) -> bool:
    """Khoá vĩnh viễn dùng chung cho mọi bảng có trigger BEFORE UPDATE guard
    (sale_plans, sale_allocations, weighing_records, sale_orders — Data
    Freeze cho đơn hàng dùng thẳng hàm này, xem webapp/routes/plans.py
    api_orders_lock()). Dùng khi cần khoá thủ công một dòng chưa tự
    chốt-và-khoá qua luồng nghiệp vụ riêng (vd confirm_weighing() đã tự
    khoá, không cần gọi hàm này cho weighing_records ở luồng bình thường).
    Trả về False nếu dòng đã bị khoá từ trước."""
    if table not in LOCKABLE_TABLES:
        raise ValueError(f"Bảng '{table}' không nằm trong danh sách được phép khoá: {LOCKABLE_TABLES}")
    now = datetime.now().isoformat(timespec="seconds")
    own_connection = conn is None
    if own_connection:
        conn = get_connection(db_path)
    try:
        cur = conn.execute(
            f"UPDATE {table} SET locked_at = ?, locked_by = ? WHERE id = ? AND locked_at IS NULL",
            (now, username, record_id),
        )
        if own_connection:
            conn.commit()
        return cur.rowcount > 0
    finally:
        if own_connection:
            conn.close()
