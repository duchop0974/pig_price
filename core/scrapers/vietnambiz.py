"""Nguồn: vietnambiz.vn."""
import re
import sys

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper
from .utils import fetch, parse_3col_table

SOURCE = "vietnambiz.vn"
TAG_URL = "https://vietnambiz.vn/chu-de/gia-heo-hoi-80.htm"
ARTICLE_RE = re.compile(r'href="(/gia-heo-hoi-hom-nay[^"]*\.htm)"')
DATE_RE = re.compile(r'property="article:published_time" content="(\d{4}-\d{2}-\d{2})')


class VietnambizScraper(BaseScraper):
    key = "vietnambiz"
    label = SOURCE

    def list_articles(self, pages: int = 1) -> list[str]:
        """Trả về danh sách URL bài viết (chưa biết ngày, sẽ lấy khi tải từng bài).
        pages > 1 sẽ duyệt thêm các trang /chu-de/gia-heo-hoi-80/trang-N.htm để
        dò được bài cũ hơn (dùng cho backfill sâu)."""
        paths = set()
        for page in range(1, pages + 1):
            url = TAG_URL if page == 1 else f"https://vietnambiz.vn/chu-de/gia-heo-hoi-80/trang-{page}.htm"
            try:
                html = fetch(url)
            except requests.RequestException as e:
                print(f"[{SOURCE}] Lỗi khi tải {url}: {e}", file=sys.stderr)
                break
            found = set(ARTICLE_RE.findall(html))
            if not found and page > 1:
                break
            paths |= found
        return ["https://vietnambiz.vn" + p for p in paths]

    def parse(self, html: str, url: str) -> tuple[str | None, list[dict]]:
        m = DATE_RE.search(html)
        if not m:
            return None, []
        y, mo, d = m.group(1).split("-")
        date_str = f"{d}/{mo}/{y}"
        soup = BeautifulSoup(html, "lxml")
        content = soup.find("div", attrs={"data-role": "content"}) or soup
        return date_str, parse_3col_table(content, url, date_str, SOURCE)

    def fetch_latest(self) -> list[dict]:
        return self.pick_latest(self.list_articles(), self.parse)

    def fetch_by_date(self, target_date: str) -> list[dict]:
        return self.find_by_date(self.list_articles(), self.parse, target_date)

    def fetch_backfill(self, limit: int) -> list[dict]:
        records = []
        for url in self.list_articles()[:limit]:
            try:
                html = fetch(url)
                _, rows = self.parse(html, url)
                records.extend(rows)
            except requests.RequestException as e:
                print(f"[{SOURCE}] Lỗi khi tải {url}: {e}", file=sys.stderr)
        return records

    def fetch_deep_backfill(self, pages: int = 5) -> list[dict]:
        records = []
        articles = self.list_articles(pages=pages)
        print(f"[{SOURCE}] Tìm thấy {len(articles)} bài qua {pages} trang danh mục.")
        for url in articles:
            try:
                html = fetch(url)
                _, rows = self.parse(html, url)
                records.extend(rows)
            except requests.RequestException as e:
                print(f"[{SOURCE}] Lỗi khi tải {url}: {e}", file=sys.stderr)
        return records

    def fetch_url(self, url: str) -> list[dict]:
        html = fetch(url)
        _, rows = self.parse(html, url)
        return rows
