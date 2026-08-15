"""Bọc db_lock quanh mọi lời gọi vào core.repositories/core.services cần đọc/ghi DB."""
import pandas as pd

from core.repositories import (
    customers_repo,
    farms_repo,
    pig_types_repo,
    prices_repo,
    roles_repo,
    sale_allocations_repo,
    sale_plans_repo,
    users_repo,
)
from core.services import export_service
from extensions import DB_PATH, db_lock


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


def create_allocation_locked(alloc: dict, ip: str | None, username: str | None) -> int:
    with db_lock:
        return sale_allocations_repo.create_allocation(alloc, DB_PATH, ip, username)


def get_allocation_locked(allocation_id: int) -> dict | None:
    with db_lock:
        return sale_allocations_repo.get_allocation(allocation_id, DB_PATH)


def list_allocations_locked(sale_plan_id: int | None = None) -> list[dict]:
    with db_lock:
        return sale_allocations_repo.list_allocations(DB_PATH, sale_plan_id=sale_plan_id)


def list_allocations_for_export_locked() -> list[dict]:
    with db_lock:
        return sale_allocations_repo.list_allocations_for_export(DB_PATH)


def update_allocation_status_locked(
    allocation_id: int,
    status: str,
    ip: str | None,
    username: str | None,
    actual_price: int | None = None,
    actual_quantity: int | None = None,
) -> None:
    with db_lock:
        sale_allocations_repo.update_allocation_status(
            allocation_id, status, DB_PATH, ip, username, actual_price, actual_quantity
        )


def update_allocation_sale_details_locked(allocation_id: int, ip: str | None, username: str | None, fields: dict) -> None:
    with db_lock:
        sale_allocations_repo.update_allocation_sale_details(allocation_id, DB_PATH, ip, username, fields)


def update_allocation_revenue_details_locked(allocation_id: int, ip: str | None, username: str | None, fields: dict) -> None:
    with db_lock:
        sale_allocations_repo.update_allocation_revenue_details(allocation_id, DB_PATH, ip, username, fields)


def count_allocations_for_customer_locked(customer_id: int) -> int:
    with db_lock:
        return sale_allocations_repo.count_allocations_for_customer(customer_id, DB_PATH)


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


def dashboard_stats_locked(farm_ids: list[int] | None = None) -> dict:
    with db_lock:
        return sale_plans_repo.dashboard_stats(DB_PATH, farm_ids=farm_ids)


def update_user_role_locked(user_id: int, role: str) -> None:
    with db_lock:
        users_repo.update_user_role(user_id, role, DB_PATH)


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


def export_allocations_excel_locked(dest) -> None:
    with db_lock:
        export_service.export_sale_allocations_to_excel(DB_PATH, dest)


def export_allocation_quotation_excel_locked(dest, allocation_ids: list[int]) -> None:
    with db_lock:
        export_service.export_allocation_quotation_to_excel(DB_PATH, dest, allocation_ids)
