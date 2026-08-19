from pathlib import Path

from core.db import db_lock, get_connection, transaction
from core.repositories import audit_repo, sale_plans_repo
from core import audit_actions


def create_plan(
    plan: dict,
    db_path: Path,
    *,
    ip: str | None = None,
    username: str | None = None,
) -> int:
    """
    Tạo kế hoạch trại và audit trong cùng transaction.
    """
    with db_lock:
        conn = get_connection(db_path)

        try:
            with transaction(conn):
                plan_id = sale_plans_repo.create_sale_plan(
                    plan,
                    db_path,
                    ip,
                    username,
                    conn=conn,
                )

                audit_repo.log_action(
                    audit_actions.PLAN_CREATE,
                    db_path,
                    username=username,
                    ip=ip,
                    entity_type="sale_plan",
                    entity_id=plan_id,
                    new_value={
                        "planned_date": plan["planned_date"],
                        "farm_id": plan["farm_id"],
                        "zone_id": plan.get("zone_id"),
                        "shed": plan.get("shed"),
                        "lot": plan.get("lot"),
                        "pig_type_id": plan["pig_type_id"],
                        "quantity": plan["quantity"],
                        "expected_avg_weight_kg": plan.get(
                            "expected_avg_weight_kg"
                        ),
                        "note": plan.get("note"),
                    },
                    conn=conn,
                )

            return plan_id

        finally:
            conn.close()