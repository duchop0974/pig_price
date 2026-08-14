"""Cron nền: tự động cập nhật giá heo hơi hàng ngày lúc 7h sáng."""
from datetime import datetime

from core.scrapers.registry import fetch_latest_all
from data_access import save_records_locked
from extensions import refresh_state


def start_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler

    def daily_job():
        print("[scheduler] Đang tự động cập nhật giá heo hơi hàng ngày...")
        records = fetch_latest_all()
        if records:
            save_records_locked(records)
        refresh_state["last_run"] = datetime.now()

    scheduler = BackgroundScheduler()
    scheduler.add_job(daily_job, "cron", hour=7, minute=0)
    scheduler.start()
    return scheduler
