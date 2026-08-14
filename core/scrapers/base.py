"""Giao diện chung cho các scraper theo từng nguồn giá heo hơi."""
import sys
from abc import ABC, abstractmethod
from typing import Callable

import requests

from .utils import date_str_to_sortkey, fetch


class BaseScraper(ABC):
    key: str
    label: str

    @abstractmethod
    def fetch_latest(self) -> list[dict]:
        """Lấy dữ liệu mới nhất hiện có (không nhất thiết cùng ngày với nguồn khác)."""

    @abstractmethod
    def fetch_by_date(self, target_date: str) -> list[dict]:
        """Lấy dữ liệu đúng ngày target_date (dd/mm/yyyy), rỗng nếu không có."""

    def pick_latest(
        self, urls: list[str], parse_dated: Callable[[str, str], tuple[str | None, list[dict]]]
    ) -> list[dict]:
        """Duyệt qua danh sách URL bài viết (chưa biết ngày), tải + parse từng bài
        (parse_dated trả về (date_str, records)), chọn bài có ngày lớn nhất. Dùng
        chung cho các nguồn không biết trước ngày của từng bài trong danh sách."""
        best_date = None
        best_records: list[dict] | None = None
        for url in urls:
            try:
                html = fetch(url)
                date_str, rows = parse_dated(html, url)
            except requests.RequestException as e:
                print(f"[{self.label}] Lỗi khi tải {url}: {e}", file=sys.stderr)
                continue
            if date_str and (best_date is None or date_str_to_sortkey(date_str) > date_str_to_sortkey(best_date)):
                best_date, best_records = date_str, rows
        return best_records or []

    def find_by_date(
        self,
        urls: list[str],
        parse_dated: Callable[[str, str], tuple[str | None, list[dict]]],
        target_date: str,
    ) -> list[dict]:
        for url in urls:
            try:
                html = fetch(url)
                date_str, rows = parse_dated(html, url)
            except requests.RequestException as e:
                print(f"[{self.label}] Lỗi khi tải {url}: {e}", file=sys.stderr)
                continue
            if date_str == target_date:
                return rows
        return []
