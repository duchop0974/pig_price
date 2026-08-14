"""Nguồn: greenfeed.com.vn (bảng giá thị trường của công ty thức ăn chăn nuôi).

Trang chỉ hiển thị đúng 1 ngày cập nhật gần nhất (đã kiểm chứng: query
?date=YYYY-MM-DD với ngày khác ngày cache hiện tại trả về rỗng), nên chỉ hỗ
trợ lấy dữ liệu mới nhất một cách chắc chắn; theo-ngày chỉ thành công nếu
đúng ngày trang đang cache. Không có khái niệm "bài viết" như các nguồn khác
nên không dùng list_articles/pick_latest của BaseScraper.
"""
import re

from bs4 import BeautifulSoup

from .base import BaseScraper
from .utils import fetch, parse_vn_number

SOURCE = "greenfeed.com.vn"
URL = (
    "https://www.greenfeed.com.vn/thuc-an-chan-nuoi-gia-suc-gia-cam/"
    "bang-gia-thi-truong/heo-hoi/?type=vat-nuoi-price"
)
DATE_RE = re.compile(r"Cập nhật ngày\s*(\d{2}/\d{2}/\d{4})")


class GreenfeedScraper(BaseScraper):
    key = "greenfeed"
    label = SOURCE

    def parse(self, html: str) -> tuple[str | None, list[dict]]:
        m = DATE_RE.search(html)
        date_str = m.group(1) if m else None
        if not date_str:
            return None, []

        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table", class_="table")
        if table is None:
            return date_str, []

        records = []
        current_region = None
        for row in table.find("tbody").find_all("tr"):
            classes = row.get("class") or []
            if "d-sm-none" in classes:
                continue  # dòng tiêu đề rút gọn cho mobile, trùng dữ liệu với dòng chính
            cells = row.find_all("td")
            if len(cells) < 4:
                continue
            market = cells[0].get_text(" ", strip=True)
            greenfeed_price = parse_vn_number(cells[1].get_text(" ", strip=True))
            heo_hoi_price = parse_vn_number(cells[2].get_text(" ", strip=True))
            heo_hoi_change = parse_vn_number(cells[3].get_text(" ", strip=True))
            if heo_hoi_price is None:
                continue

            is_region_row = "region" in classes
            if is_region_row:
                current_region = market

            records.append(
                {
                    "date": date_str,
                    "source": SOURCE,
                    "region": current_region,
                    "province": market,
                    "price_vnd_per_kg": heo_hoi_price,
                    "change_vnd_per_kg": heo_hoi_change,
                    "benchmark_price_vnd_per_kg": greenfeed_price,
                    "source_url": URL,
                }
            )
        return date_str, records

    def fetch_latest(self) -> list[dict]:
        html = fetch(URL)
        _, records = self.parse(html)
        return records

    def fetch_by_date(self, target_date: str) -> list[dict]:
        d, m, y = target_date.split("/")
        iso_date = f"{y}-{m}-{d}"
        html = fetch(URL + "&date=" + iso_date)
        date_str, records = self.parse(html)
        if date_str != target_date:
            return []
        return records
