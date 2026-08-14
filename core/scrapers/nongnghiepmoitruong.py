"""Nguồn: nongnghiepmoitruong.vn (báo Nông nghiệp và Môi trường)."""
import re
import sys
from datetime import date as _date

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper
from .utils import date_str_to_sortkey, fetch, parse_3col_table

SOURCE = "nongnghiepmoitruong.vn"
TAG_URL = "https://nongnghiepmoitruong.vn/gia-heo-hoi-hom-nay-tag90954/"
ARTICLE_RE = re.compile(
    r"https://nongnghiepmoitruong\.vn/gia-heo-hoi-hom-nay-(\d{1,2})-(\d{1,2})-(\d{4})[^\"'\s]*\.html"
)


class NongNghiepMoiTruongScraper(BaseScraper):
    key = "nongnghiepmoitruong"
    label = SOURCE

    def list_articles(self) -> list[tuple[str, str]]:
        """Trả về danh sách (url, ngày dd/mm/yyyy) duy nhất, mới nhất trước."""
        html = fetch(TAG_URL)
        seen = {}
        for m in ARTICLE_RE.finditer(html):
            url = m.group(0)
            day, month, year = m.group(1), m.group(2), m.group(3)
            date_str = f"{int(day):02d}/{int(month):02d}/{year}"
            seen[url] = (date_str, (int(year), int(month), int(day)))
        items = sorted(seen.items(), key=lambda kv: kv[1][1], reverse=True)
        return [(url, date_str) for url, (date_str, _) in items]

    def parse(self, html: str, url: str, date_str: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        content = soup.find("div", class_="detail-content") or soup
        return parse_3col_table(content, url, date_str, SOURCE)

    def fetch_latest(self) -> list[dict]:
        articles = self.list_articles()
        if not articles:
            return []
        url, date_str = articles[0]
        html = fetch(url)
        return self.parse(html, url, date_str)

    def fetch_by_date(self, target_date: str) -> list[dict]:
        for url, date_str in self.list_articles():
            if date_str == target_date:
                html = fetch(url)
                return self.parse(html, url, date_str)
        return []

    def fetch_backfill(self, limit: int) -> list[dict]:
        records = []
        for url, date_str in self.list_articles()[:limit]:
            try:
                html = fetch(url)
                records.extend(self.parse(html, url, date_str))
            except requests.RequestException as e:
                print(f"[{SOURCE}] Lỗi khi tải {url}: {e}", file=sys.stderr)
        return records

    def fetch_url(self, url: str) -> list[dict]:
        m = ARTICLE_RE.search(url)
        date_str = f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}" if m else "unknown"
        html = fetch(url)
        return self.parse(html, url, date_str)

    def list_articles_from_sitemap(self, months_back: int = 6) -> list[tuple[str, str]]:
        """Dò bài viết cũ qua sitemap theo tháng (sitemap-post-YYYY-MM.xml), không
        bị giới hạn 'cửa sổ trượt' như trang danh sách (list_articles)."""
        today = _date.today()
        seen = {}
        for i in range(months_back):
            month_index = today.month - i
            year = today.year + (month_index - 1) // 12
            month = (month_index - 1) % 12 + 1
            sitemap_url = f"https://nongnghiepmoitruong.vn/sitemap-post-{year:04d}-{month:02d}.xml"
            try:
                xml = fetch(sitemap_url)
            except requests.RequestException as e:
                print(f"[{SOURCE}] Lỗi khi tải sitemap {sitemap_url}: {e}", file=sys.stderr)
                continue
            for m in ARTICLE_RE.finditer(xml):
                url = m.group(0)
                d, mo, y = m.group(1), m.group(2), m.group(3)
                date_str = f"{int(d):02d}/{int(mo):02d}/{y}"
                seen[url] = date_str
        items = sorted(seen.items(), key=lambda kv: date_str_to_sortkey(kv[1]), reverse=True)
        return [(url, date_str) for url, date_str in items]

    def fetch_sitemap_backfill(self, months_back: int = 6) -> list[dict]:
        records = []
        articles = self.list_articles_from_sitemap(months_back)
        print(f"[{SOURCE}] Tìm thấy {len(articles)} bài qua sitemap ({months_back} tháng gần đây).")
        for url, date_str in articles:
            try:
                html = fetch(url)
                records.extend(self.parse(html, url, date_str))
            except requests.RequestException as e:
                print(f"[{SOURCE}] Lỗi khi tải {url}: {e}", file=sys.stderr)
        return records
