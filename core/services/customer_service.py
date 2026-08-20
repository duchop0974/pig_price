"""Service layer cho danh mục khách hàng (customers) — khuôn 1:1
plan_service.py/order_service.py/delivery_service.py."""
from pathlib import Path

from core.db import run_in_transaction
from core.repositories import audit_repo, customers_repo
from core import audit_actions

_write = run_in_transaction


def _validate_customer_fields(data: dict, *, name_required_msg: str) -> dict:
    """STEP 7 (Route Refactor): validate + parse toàn bộ trường khách hàng
    — gộp 2 khối validate giống hệt nhau ở api_customers_create() và
    api_customers_update() (webapp/routes/plans.py) thành 1 chỗ. Message
    lỗi "thiếu tên" khác nhau giữa 2 route gốc (tạo mới vs sửa) nên giữ
    tham số riêng để không đổi hành vi. Raise ValueError(msg)."""
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip() or None
    address = (data.get("address") or "").strip() or None
    tax_code = (data.get("tax_code") or "").strip() or None
    note = (data.get("note") or "").strip() or None
    email = (data.get("email") or "").strip() or None
    contact_person = (data.get("contact_person") or "").strip() or None
    contact_title = (data.get("contact_title") or "").strip() or None

    if not name or len(name) > 150:
        raise ValueError(name_required_msg)
    if phone and len(phone) > 30:
        raise ValueError("Số điện thoại quá dài.")
    if tax_code and len(tax_code) > 20:
        raise ValueError("Mã số thuế quá dài.")
    if email and (len(email) > 100 or "@" not in email):
        raise ValueError("Email không hợp lệ.")
    if contact_person and len(contact_person) > 100:
        raise ValueError("Tên người liên hệ quá dài.")
    if contact_title and len(contact_title) > 100:
        raise ValueError("Chức vụ quá dài.")

    return {
        "name": name,
        "phone": phone,
        "address": address,
        "tax_code": tax_code,
        "note": note,
        "email": email,
        "contact_person": contact_person,
        "contact_title": contact_title,
    }


def create_customer(
    data: dict,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> int:
    """Validate input thô (STEP 7 Route Refactor) rồi tạo khách hàng +
    audit trong cùng transaction. Có thể raise ValueError."""
    fields = _validate_customer_fields(data, name_required_msg="Vui lòng nhập tên khách hàng hợp lệ.")

    def _do(conn):
        customer_id = customers_repo.create_customer(
            fields["name"],
            fields.get("phone"),
            fields.get("address"),
            fields.get("tax_code"),
            fields.get("note"),
            db_path,
            email=fields.get("email"),
            contact_person=fields.get("contact_person"),
            contact_title=fields.get("contact_title"),
            conn=conn,
        )
        audit_repo.log_action(
            audit_actions.CUSTOMER_CREATE,
            db_path,
            username=username,
            ip=ip,
            entity_type="customer",
            entity_id=customer_id,
            new_value={
                "name": fields["name"],
                "phone": fields.get("phone"),
                "address": fields.get("address"),
                "tax_code": fields.get("tax_code"),
                "email": fields.get("email"),
            },
            conn=conn,
        )
        return customer_id

    return _write(db_path, _do)


def update_customer(
    customer_id: int,
    data: dict,
    old_customer: dict,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> None:
    """Validate input thô (STEP 7 Route Refactor, dùng chung
    _validate_customer_fields() với create_customer()) rồi sửa khách hàng
    + audit trong cùng transaction. Có thể raise ValueError."""
    fields = _validate_customer_fields(data, name_required_msg="Tên khách hàng không hợp lệ.")

    def _do(conn):
        customers_repo.update_customer(
            customer_id,
            fields["name"],
            fields.get("phone"),
            fields.get("address"),
            fields.get("tax_code"),
            fields.get("note"),
            db_path,
            email=fields.get("email"),
            contact_person=fields.get("contact_person"),
            contact_title=fields.get("contact_title"),
            conn=conn,
        )
        audit_repo.log_action(
            audit_actions.CUSTOMER_UPDATE,
            db_path,
            username=username,
            ip=ip,
            entity_type="customer",
            entity_id=customer_id,
            old_value={
                "name": old_customer["name"],
                "phone": old_customer["phone"],
                "address": old_customer["address"],
                "tax_code": old_customer["tax_code"],
            },
            new_value={
                "name": fields["name"],
                "phone": fields.get("phone"),
                "address": fields.get("address"),
                "tax_code": fields.get("tax_code"),
                "email": fields.get("email"),
            },
            conn=conn,
        )

    _write(db_path, _do)


def set_active(
    customer_id: int,
    is_active: bool,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> None:
    """Kích hoạt/vô hiệu hoá khách hàng + audit trong cùng transaction."""

    def _do(conn):
        customers_repo.set_customer_active(customer_id, is_active, db_path, conn=conn)
        audit_repo.log_action(
            audit_actions.CUSTOMER_ACTIVATE if is_active else audit_actions.CUSTOMER_DEACTIVATE,
            db_path,
            username=username,
            ip=ip,
            entity_type="customer",
            entity_id=customer_id,
            conn=conn,
        )

    _write(db_path, _do)


def delete_customer(
    customer_id: int,
    old_customer: dict,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> None:
    """Xoá khách hàng + audit trong cùng transaction. Kiểm tra "còn dùng
    trong kế hoạch xuất bán hay không" vẫn do route thực hiện TRƯỚC khi
    gọi (count_orders_for_customer_locked), khớp hành vi cũ."""

    def _do(conn):
        customers_repo.delete_customer(customer_id, db_path, conn=conn)
        audit_repo.log_action(
            audit_actions.CUSTOMER_DELETE,
            db_path,
            username=username,
            ip=ip,
            entity_type="customer",
            entity_id=customer_id,
            old_value={"name": old_customer["name"], "phone": old_customer["phone"]},
            conn=conn,
        )

    _write(db_path, _do)
