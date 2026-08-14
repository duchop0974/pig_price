"""Bọc db_lock quanh mọi lời gọi vào core.repositories/core.services cần đọc/ghi DB."""
import pandas as pd

from core.repositories import farms_repo, prices_repo, sale_plans_repo
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


def list_plans_locked() -> list[dict]:
    with db_lock:
        return sale_plans_repo.list_sale_plans(DB_PATH)


def update_plan_status_locked(plan_id: int, status: str, ip: str | None, username: str | None) -> None:
    with db_lock:
        sale_plans_repo.update_sale_plan_status(plan_id, status, DB_PATH, ip, username)


def delete_plan_locked(plan_id: int) -> None:
    with db_lock:
        sale_plans_repo.delete_sale_plan(plan_id, DB_PATH)


def list_farms_locked() -> list[str]:
    with db_lock:
        return farms_repo.list_farms(DB_PATH)


def create_farm_locked(code: str) -> None:
    with db_lock:
        farms_repo.create_farm(code, DB_PATH)


def list_zones_locked(farm: str) -> list[str]:
    with db_lock:
        return farms_repo.list_zones(farm, DB_PATH)


def create_zone_locked(farm: str, code: str) -> None:
    with db_lock:
        farms_repo.create_zone(farm, code, DB_PATH)


def export_prices_excel_locked(dest) -> None:
    with db_lock:
        export_service.export_to_excel(DB_PATH, dest)


def export_plans_excel_locked(dest) -> None:
    with db_lock:
        export_service.export_sale_plans_to_excel(DB_PATH, dest)
