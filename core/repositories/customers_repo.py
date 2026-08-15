"""CRUD cho bảng customers (danh mục khách hàng mua heo) — sales/admin quản lý."""
import sqlite3
from datetime import datetime
from pathlib import Path

from core.db import get_connection

_COLUMNS = (
    "id, name, phone, address, tax_code, note, email, contact_person, contact_title, is_active, created_at"
)


def list_customers(db_path: Path, active_only: bool = False) -> list[dict]:
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        sql = f"SELECT {_COLUMNS} FROM customers"
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY name COLLATE NOCASE ASC"
        rows = conn.execute(sql).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_customer(
    name: str,
    phone: str | None,
    address: str | None,
    tax_code: str | None,
    note: str | None,
    db_path: Path,
    email: str | None = None,
    contact_person: str | None = None,
    contact_title: str | None = None,
) -> int:
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO customers (name, phone, address, tax_code, note, email, contact_person, "
            "contact_title, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
            (
                name,
                phone,
                address,
                tax_code,
                note,
                email,
                contact_person,
                contact_title,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_customer(customer_id: int, db_path: Path) -> dict | None:
    conn = get_connection(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(f"SELECT {_COLUMNS} FROM customers WHERE id = ?", (customer_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_customer(
    customer_id: int,
    name: str,
    phone: str | None,
    address: str | None,
    tax_code: str | None,
    note: str | None,
    db_path: Path,
    email: str | None = None,
    contact_person: str | None = None,
    contact_title: str | None = None,
) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE customers SET name = ?, phone = ?, address = ?, tax_code = ?, note = ?, "
            "email = ?, contact_person = ?, contact_title = ? WHERE id = ?",
            (name, phone, address, tax_code, note, email, contact_person, contact_title, customer_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_customer_active(customer_id: int, is_active: bool, db_path: Path) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE customers SET is_active = ? WHERE id = ?", (1 if is_active else 0, customer_id)
        )
        conn.commit()
    finally:
        conn.close()


def delete_customer(customer_id: int, db_path: Path) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
        conn.commit()
    finally:
        conn.close()
