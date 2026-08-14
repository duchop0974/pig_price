"""Điều phối theo nguồn: đăng ký các scraper và gọi thống nhất qua interface chung."""
import sys

import requests

from .baovanhoa import BaoVanHoaScraper
from .greenfeed import GreenfeedScraper
from .nongnghiepmoitruong import NongNghiepMoiTruongScraper
from .utils import REGION_BUCKETS
from .vietnambiz import VietnambizScraper
from .vinanet import VinanetScraper

SCRAPERS = {
    "nongnghiepmoitruong": NongNghiepMoiTruongScraper(),
    "vietnambiz": VietnambizScraper(),
    "greenfeed": GreenfeedScraper(),
    "vinanet": VinanetScraper(),
    "baovanhoa": BaoVanHoaScraper(),
}

SOURCES = list(SCRAPERS.keys())
SOURCE_LABELS = {key: s.label for key, s in SCRAPERS.items()}
SOURCE_ORDER = [SOURCE_LABELS[s] for s in SOURCES]
REGION_BUCKETS = REGION_BUCKETS


def get_scraper(key: str) -> object:
    return SCRAPERS[key]


def fetch_latest_all(sources: list[str] | None = None) -> list[dict]:
    """Lấy dữ liệu mới nhất hiện có của từng nguồn (không nhất thiết cùng ngày
    do các nguồn có độ trễ xuất bản khác nhau)."""
    sources = sources or SOURCES
    records = []
    for key in sources:
        scraper = SCRAPERS.get(key)
        if scraper is None:
            continue
        try:
            rows = scraper.fetch_latest()
            print(f"[{scraper.label}] lấy được {len(rows)} dòng")
            records.extend(rows)
        except requests.RequestException as e:
            print(f"[{scraper.label}] Lỗi khi tải dữ liệu: {e}", file=sys.stderr)
    return records


def fetch_by_date_all(target_date: str, sources: list[str] | None = None) -> list[dict]:
    """Lấy dữ liệu đúng ngày target_date (dd/mm/yyyy) từ từng nguồn nếu có."""
    sources = sources or SOURCES
    records = []
    for key in sources:
        scraper = SCRAPERS.get(key)
        if scraper is None:
            continue
        try:
            rows = scraper.fetch_by_date(target_date)
            if rows:
                print(f"[{scraper.label}] {target_date}: lấy được {len(rows)} dòng")
            else:
                print(f"[{scraper.label}] Không có dữ liệu cho ngày {target_date}.")
            records.extend(rows)
        except requests.RequestException as e:
            print(f"[{scraper.label}] Lỗi khi tải dữ liệu: {e}", file=sys.stderr)
    return records
