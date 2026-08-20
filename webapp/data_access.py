"""Bọc db_lock quanh mọi lời gọi vào core.repositories/core.services cần đọc/ghi DB."""
import pandas as pd

from core.repositories import (
    customers_repo,
    farms_repo,
    incident_repo,
    media_repo,
    pig_types_repo,
    plan_reconciliation_repo,
    prices_repo,
    roles_repo,
    sale_deliveries_repo,
    sale_orders_repo,
    sale_plans_repo,
    users_repo,
    weighing_repo,
)
from core.services import export_service
from extensions import DB_PATH, MEDIA_ROOT, db_lock


def load_df() -> pd.DataFrame:
    with db_lock:
        return prices_repo.load_records_df(DB_PATH)


def save_records_locked(records: list[dict]) -> None:
    with db_lock:
        prices_repo.save_records(records, DB_PATH)


def create_plan_locked(plan: dict, ip: str | None, username: str | None) -> int:
    with db_lock:
        return sale_plans_repo.create_sale_plan(plan, DB_PATH, ip, username)


def get_plan_locked(plan_id: int) -> dict | None:
    with db_lock:
        return sale_plans_repo.get_sale_plan(plan_id, DB_PATH)


def list_plans_locked(farm_ids: list[int] | None = None) -> list[dict]:
    with db_lock:
        return sale_plans_repo.list_sale_plans(DB_PATH, farm_ids=farm_ids)


def approve_plan_locked(plan_id: int, ip: str | None, username: str | None) -> None:
    with db_lock:
        sale_plans_repo.approve_sale_plan(plan_id, DB_PATH, ip, username)


def reject_plan_locked(plan_id: int, reason: str, ip: str | None, username: str | None) -> None:
    with db_lock:
        sale_plans_repo.reject_sale_plan(plan_id, reason, DB_PATH, ip, username)


def update_plan_received_quantity_locked(plan_id: int, received_quantity: int, ip: str | None, username: str | None) -> None:
    with db_lock:
        sale_plans_repo.update_plan_received_quantity(plan_id, received_quantity, DB_PATH, ip, username)


def update_sale_plan_edit_locked(plan_id: int, plan: dict, ip: str | None, username: str | None) -> bool:
    with db_lock:
        return sale_plans_repo.update_sale_plan_edit(plan_id, plan, DB_PATH, ip, username)


def delete_plan_locked(plan_id: int) -> bool:
    with db_lock:
        return sale_plans_repo.delete_sale_plan(plan_id, DB_PATH)


def create_order_locked(lines: list[dict], ip: str | None, username: str | None) -> int:
    with db_lock:
        return sale_orders_repo.create_order(lines, DB_PATH, ip, username)


def add_order_line_locked(order_id: int, line: dict, ip: str | None, username: str | None) -> int:
    with db_lock:
        return sale_orders_repo.add_order_line(order_id, line, DB_PATH, ip, username)


def remove_order_line_locked(order_id: int, allocation_id: int, ip: str | None, username: str | None) -> bool:
    with db_lock:
        return sale_orders_repo.remove_order_line(order_id, allocation_id, DB_PATH, ip, username)


def get_order_locked(order_id: int) -> dict | None:
    with db_lock:
        return sale_orders_repo.get_order(order_id, DB_PATH)


def list_orders_locked() -> list[dict]:
    with db_lock:
        return sale_orders_repo.list_orders(DB_PATH)


def list_orders_for_export_locked() -> list[dict]:
    with db_lock:
        return sale_orders_repo.list_orders_for_export(DB_PATH)


def update_order_status_locked(order_id: int, status: str, ip: str | None, username: str | None) -> None:
    with db_lock:
        sale_orders_repo.update_order_status(order_id, status, DB_PATH, ip, username)


def mark_order_done_locked(order_id: int, line_actuals: list[dict], ip: str | None, username: str | None) -> None:
    with db_lock:
        sale_orders_repo.mark_order_done(order_id, line_actuals, DB_PATH, ip, username)


def update_order_sale_details_locked(order_id: int, ip: str | None, username: str | None, fields: dict) -> None:
    with db_lock:
        sale_orders_repo.update_order_sale_details(order_id, DB_PATH, ip, username, fields)


def update_order_revenue_details_locked(order_id: int, ip: str | None, username: str | None, fields: dict) -> None:
    with db_lock:
        sale_orders_repo.update_order_revenue_details(order_id, DB_PATH, ip, username, fields)


def count_orders_for_customer_locked(customer_id: int) -> int:
    with db_lock:
        return sale_orders_repo.count_orders_for_customer(customer_id, DB_PATH)


def update_order_line_locked(allocation_id: int, ip: str | None, username: str | None, fields: dict) -> bool:
    with db_lock:
        return sale_orders_repo.update_order_line(allocation_id, DB_PATH, ip, username, fields)


def delete_order_locked(order_id: int) -> tuple[bool, str | None]:
    with db_lock:
        return sale_orders_repo.delete_order(order_id, DB_PATH)


def list_customers_locked(active_only: bool = False) -> list[dict]:
    with db_lock:
        return customers_repo.list_customers(DB_PATH, active_only)


def get_customer_locked(customer_id: int) -> dict | None:
    with db_lock:
        return customers_repo.get_customer(customer_id, DB_PATH)


def create_customer_locked(
    name: str, phone, address, tax_code, note, email=None, contact_person=None, contact_title=None
) -> int:
    with db_lock:
        return customers_repo.create_customer(
            name, phone, address, tax_code, note, DB_PATH, email, contact_person, contact_title
        )


def update_customer_locked(
    customer_id: int, name: str, phone, address, tax_code, note, email=None, contact_person=None, contact_title=None
) -> None:
    with db_lock:
        customers_repo.update_customer(
            customer_id, name, phone, address, tax_code, note, DB_PATH, email, contact_person, contact_title
        )


def set_customer_active_locked(customer_id: int, is_active: bool) -> None:
    with db_lock:
        customers_repo.set_customer_active(customer_id, is_active, DB_PATH)


def delete_customer_locked(customer_id: int) -> None:
    with db_lock:
        customers_repo.delete_customer(customer_id, DB_PATH)


def update_plan_status_locked(plan_id: int, status: str, ip: str | None, username: str | None) -> None:
    with db_lock:
        sale_plans_repo.update_sale_plan_status(plan_id, status, DB_PATH, ip, username)


def list_farms_locked() -> list[dict]:
    with db_lock:
        return farms_repo.list_farms(DB_PATH)


def create_farm_locked(code: str, province: str | None) -> None:
    with db_lock:
        farms_repo.create_farm(code, province, DB_PATH)


def list_zones_locked(farm_id: int) -> list[dict]:
    with db_lock:
        return farms_repo.list_zones(farm_id, DB_PATH)


def create_zone_locked(farm_id: int, code: str) -> None:
    with db_lock:
        farms_repo.create_zone(farm_id, code, DB_PATH)


def get_farm_locked(farm_id: int) -> dict | None:
    with db_lock:
        return farms_repo.get_farm(farm_id, DB_PATH)


def update_farm_locked(farm_id: int, code: str, province: str | None) -> None:
    with db_lock:
        farms_repo.update_farm(farm_id, code, province, DB_PATH)


def delete_farm_locked(farm_id: int) -> None:
    with db_lock:
        farms_repo.delete_farm(farm_id, DB_PATH)


def get_zone_locked(zone_id: int) -> dict | None:
    with db_lock:
        return farms_repo.get_zone(zone_id, DB_PATH)


def update_zone_locked(zone_id: int, code: str) -> None:
    with db_lock:
        farms_repo.update_zone(zone_id, code, DB_PATH)


def delete_zone_locked(zone_id: int) -> None:
    with db_lock:
        farms_repo.delete_zone(zone_id, DB_PATH)


def list_pig_types_locked(active_only: bool = False) -> list[dict]:
    with db_lock:
        return pig_types_repo.list_pig_types(DB_PATH, active_only)


def get_pig_type_locked(pig_type_id: int) -> dict | None:
    with db_lock:
        return pig_types_repo.get_pig_type(pig_type_id, DB_PATH)


def create_pig_type_locked(code: str, name: str) -> int:
    with db_lock:
        return pig_types_repo.create_pig_type(code, name, DB_PATH)


def update_pig_type_locked(pig_type_id: int, code: str, name: str) -> None:
    with db_lock:
        pig_types_repo.update_pig_type(pig_type_id, code, name, DB_PATH)


def delete_pig_type_locked(pig_type_id: int) -> None:
    with db_lock:
        pig_types_repo.delete_pig_type(pig_type_id, DB_PATH)


def set_pig_type_active_locked(pig_type_id: int, is_active: bool) -> None:
    with db_lock:
        pig_types_repo.set_pig_type_active(pig_type_id, is_active, DB_PATH)


def count_plans_for_farm_locked(farm_id: int) -> int:
    with db_lock:
        return sale_plans_repo.count_plans_for_farm(farm_id, DB_PATH)


def count_plans_for_zone_locked(zone_id: int) -> int:
    with db_lock:
        return sale_plans_repo.count_plans_for_zone(zone_id, DB_PATH)


def count_plans_for_pig_type_locked(pig_type_id: int) -> int:
    with db_lock:
        return sale_plans_repo.count_plans_for_pig_type(pig_type_id, DB_PATH)


def dashboard_summary_locked(farm_ids: list[int] | None = None, days: int = 30) -> dict:
    with db_lock:
        return sale_plans_repo.dashboard_summary(DB_PATH, farm_ids=farm_ids, days=days)


def daily_reconciliation_series_locked(farm_ids: list[int] | None = None, days: int = 30) -> list[dict]:
    with db_lock:
        return sale_plans_repo.daily_reconciliation_series(DB_PATH, farm_ids=farm_ids, days=days)


def pig_type_composition_locked(farm_ids: list[int] | None = None, days: int = 30) -> list[dict]:
    with db_lock:
        return sale_plans_repo.pig_type_composition(DB_PATH, farm_ids=farm_ids, days=days)


def list_needs_reconciliation_locked(farm_ids: list[int] | None = None, limit: int = 5) -> dict:
    with db_lock:
        return sale_plans_repo.list_needs_reconciliation(DB_PATH, farm_ids=farm_ids, limit=limit)


def update_user_role_locked(user_id: int, role: str) -> None:
    with db_lock:
        users_repo.update_user_role(user_id, role, DB_PATH)


def delete_user_locked(user_id: int) -> None:
    with db_lock:
        users_repo.delete_user(user_id, DB_PATH)


def list_farm_ids_for_user_locked(user_id: int) -> list[int]:
    with db_lock:
        return users_repo.list_farm_ids_for_user(user_id, DB_PATH)


def list_farms_for_user_locked(user_id: int) -> list[dict]:
    with db_lock:
        return users_repo.list_farms_for_user(user_id, DB_PATH)


def assign_user_farms_locked(user_id: int, farm_ids: list[int]) -> None:
    with db_lock:
        users_repo.assign_user_farms(user_id, farm_ids, DB_PATH)


def list_roles_locked() -> list[dict]:
    with db_lock:
        return roles_repo.list_roles(DB_PATH)


def get_role_locked(role_key: str) -> dict | None:
    with db_lock:
        return roles_repo.get_role(role_key, DB_PATH)


def create_role_locked(key: str, name: str) -> None:
    with db_lock:
        roles_repo.create_role(key, name, DB_PATH)


def delete_role_locked(role_key: str) -> None:
    with db_lock:
        roles_repo.delete_role(role_key, DB_PATH)


def count_users_with_role_locked(role_key: str) -> int:
    with db_lock:
        return roles_repo.count_users_with_role(role_key, DB_PATH)


def list_permissions_for_role_locked(role_key: str) -> list[str]:
    with db_lock:
        return roles_repo.list_permissions_for_role(role_key, DB_PATH)


def set_permissions_for_role_locked(role_key: str, permission_keys: list[str]) -> None:
    with db_lock:
        roles_repo.set_permissions_for_role(role_key, permission_keys, DB_PATH)


def effective_permissions_locked(role_key: str) -> set[str]:
    with db_lock:
        return roles_repo.effective_permissions(role_key, DB_PATH)


def export_prices_excel_locked(dest) -> None:
    with db_lock:
        export_service.export_to_excel(DB_PATH, dest)


def export_plans_excel_locked(dest) -> None:
    with db_lock:
        export_service.export_sale_plans_to_excel(DB_PATH, dest)


def export_orders_excel_locked(dest) -> None:
    with db_lock:
        export_service.export_sale_orders_to_excel(DB_PATH, dest)


def export_order_quotation_excel_locked(dest, order_ids: list[int]) -> None:
    with db_lock:
        export_service.export_order_quotation_to_excel(DB_PATH, dest, order_ids)


def lock_order_locked(order_id: int, ip: str | None, username: str | None) -> bool:
    with db_lock:
        return weighing_repo.lock_record("sale_orders", order_id, DB_PATH, ip=ip, username=username)


# ---------------------------------------------------------------------------
# Cần xử lý (Operational Dashboard / Exception Center)
# ---------------------------------------------------------------------------


def list_pending_review_locked(farm_ids: list[int] | None = None, limit: int = 5) -> dict:
    with db_lock:
        return sale_plans_repo.list_pending_review(DB_PATH, farm_ids=farm_ids, limit=limit)


def list_awaiting_receipt_locked(farm_ids: list[int] | None = None, limit: int = 5) -> dict:
    with db_lock:
        return sale_plans_repo.list_awaiting_receipt(DB_PATH, farm_ids=farm_ids, limit=limit)


def list_awaiting_sale_details_locked(limit: int = 5) -> dict:
    with db_lock:
        return sale_orders_repo.list_awaiting_sale_details(DB_PATH, limit=limit)


def list_awaiting_revenue_locked(limit: int = 5) -> dict:
    with db_lock:
        return sale_orders_repo.list_awaiting_revenue(DB_PATH, limit=limit)


# ---------------------------------------------------------------------------
# Heo loại/hủy (incident_reports) + ảnh bằng chứng (media_proof)
# ---------------------------------------------------------------------------


def get_allocation_for_incident_locked(allocation_id: int) -> dict | None:
    with db_lock:
        return incident_repo.get_allocation_for_incident(allocation_id, DB_PATH)


def create_incident_locked(
    allocation_id: int, kind: str, quantity: int, description: str, ip: str | None, username: str | None
) -> dict:
    with db_lock:
        return incident_repo.create_incident(
            allocation_id, kind, quantity, description, DB_PATH, reported_by=username, ip=ip
        )


def get_incident_locked(incident_id: int) -> dict | None:
    with db_lock:
        return incident_repo.get_incident(incident_id, DB_PATH)


def list_incidents_for_order_locked(order_id: int) -> list[dict]:
    with db_lock:
        return incident_repo.list_incidents_for_order(order_id, DB_PATH)


def delete_incident_locked(incident_id: int) -> bool:
    with db_lock:
        return incident_repo.delete_incident(incident_id, DB_PATH)


def save_media_upload_locked(
    file_bytes: bytes,
    entity_type: str,
    entity_id,
    kind: str,
    uploaded_by: str | None,
    uploaded_ip: str | None,
    original_filename: str | None,
    mime_type: str | None,
) -> dict:
    with db_lock:
        return media_repo.save_upload(
            file_bytes,
            entity_type,
            entity_id,
            kind,
            MEDIA_ROOT,
            DB_PATH,
            uploaded_by=uploaded_by,
            uploaded_ip=uploaded_ip,
            original_filename=original_filename,
            mime_type=mime_type,
        )


def get_media_locked(media_id: int) -> dict | None:
    with db_lock:
        return media_repo.get_media(media_id, DB_PATH)


def list_media_for_entity_locked(entity_type: str, entity_id) -> list[dict]:
    with db_lock:
        return media_repo.list_media_for_entity(entity_type, entity_id, DB_PATH)


# ---------------------------------------------------------------------------
# Đối soát kế hoạch trại (sale_plan_reconciliations) + ảnh bằng chứng (media_proof)
# ---------------------------------------------------------------------------


def create_plan_reconciliation_locked(
    sale_plan_id: int, kind: str, quantity: int, reason: str, ip: str | None, username: str | None
) -> dict:
    with db_lock:
        return plan_reconciliation_repo.create_reconciliation(
            sale_plan_id, kind, quantity, reason, DB_PATH, reported_by=username, ip=ip
        )


def get_reconciliation_locked(reconciliation_id: int) -> dict | None:
    with db_lock:
        return plan_reconciliation_repo.get_reconciliation(reconciliation_id, DB_PATH)


def list_reconciliations_for_plan_locked(sale_plan_id: int) -> list[dict]:
    with db_lock:
        return plan_reconciliation_repo.list_reconciliations_for_plan(sale_plan_id, DB_PATH)


def delete_reconciliation_locked(reconciliation_id: int) -> bool:
    with db_lock:
        return plan_reconciliation_repo.delete_reconciliation(reconciliation_id, DB_PATH)


# ---------------------------------------------------------------------------
# Xuất giao thực tế (sale_deliveries) — loại heo/số lượng/kg/ngày xuất THẬT
# ---------------------------------------------------------------------------


def create_delivery_locked(allocation_id: int, delivery: dict, ip: str | None, username: str | None) -> dict:
    with db_lock:
        return sale_deliveries_repo.create_delivery(allocation_id, delivery, DB_PATH, ip, username)


def get_delivery_locked(delivery_id: int) -> dict | None:
    with db_lock:
        return sale_deliveries_repo.get_delivery(delivery_id, DB_PATH)


def list_deliveries_for_allocation_locked(allocation_id: int) -> list[dict]:
    with db_lock:
        return sale_deliveries_repo.list_deliveries_for_allocation(allocation_id, DB_PATH)


def list_deliveries_for_order_locked(order_id: int) -> list[dict]:
    with db_lock:
        return sale_deliveries_repo.list_deliveries_for_order(order_id, DB_PATH)


def list_deliveries_for_plan_locked(sale_plan_id: int) -> list[dict]:
    with db_lock:
        return sale_deliveries_repo.list_deliveries_for_plan(sale_plan_id, DB_PATH)


def list_deliveries_locked(farm_ids: list[int] | None = None) -> list[dict]:
    with db_lock:
        return sale_deliveries_repo.list_deliveries(DB_PATH, farm_ids=farm_ids)


def delete_delivery_locked(delivery_id: int) -> tuple[bool, str | None]:
    with db_lock:
        return sale_deliveries_repo.delete_delivery(delivery_id, DB_PATH)


def sum_delivered_for_plan_locked(sale_plan_id: int) -> int:
    with db_lock:
        return sale_deliveries_repo.sum_delivered_for_plan(sale_plan_id, DB_PATH)


def count_deliveries_for_pig_type_locked(pig_type_id: int) -> int:
    with db_lock:
        return sale_deliveries_repo.count_deliveries_for_pig_type(pig_type_id, DB_PATH)


def lock_delivery_locked(delivery_id: int, ip: str | None, username: str | None) -> bool:
    with db_lock:
        return weighing_repo.lock_record("sale_deliveries", delivery_id, DB_PATH, ip, username)
