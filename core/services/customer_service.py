"""Service layer cho danh mục khách hàng (customers) — khuôn 1:1
plan_service.py/order_service.py/delivery_service.py."""
from pathlib import Path

from core.db import run_in_transaction
from core.repositories import audit_repo, customers_repo
from core import audit_actions

_write = run_in_transaction


def create_customer(
    fields: dict,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> int:
    """Tạo khách hàng + audit trong cùng transaction. `fields` gồm
    name/phone/address/tax_code/note/email/contact_person/contact_title."""

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
    fields: dict,
    old_customer: dict,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> None:
    """Sửa khách hàng + audit trong cùng transaction."""

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
