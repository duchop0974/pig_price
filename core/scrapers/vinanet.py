"""Nguồn: vinanet.vn (trang tin hàng hoá/thị trường)."""
import re
import sys
from datetime import date as _date

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper
from .utils import REGION_KEYWORDS, date_str_to_sortkey, fetch, parse_vn_number

SOURCE = "vinanet.vn"
CATEGORY_URL = "https://vinanet.vn/thit-san-pham-thit/ic-21.html"
ARTICLE_RE = re.compile(r'href="(/[^"]*gia-heo-hoi-hom-nay[^"]*\.html)"')
DATE_RE = re.compile(r'property="article:published_time"\s+content="(\d{4}-\d{2}-\d{2})T')
SITEMAP_ENTRY_RE = re.compile(
    r"<loc>(https://vinanet\.vn/[^<]*gia-heo-hoi-hom-nay[^<]*)</loc>"
    r"<lastmod>(\d{4}-\d{2}-\d{2})T"
)


class VinanetScraper(BaseScraper):
    key = "vinanet"
    label = SOURCE

    def list_articles(self, max_pages: int = 3) -> list[str]:
        """Trả về danh sách URL bài viết (chưa biết ngày) từ trang danh mục,
        duyệt qua vài trang để có đủ bài cho backfill."""
        paths = set()
        for page in range(1, max_pages + 1):
            url = CATEGORY_URL if page == 1 else f"{CATEGORY_URL}?page={page}"
            html = fetch(url)
            found = set(ARTICLE_RE.findall(html))
            new_paths = found - paths
            if not new_paths and page > 1:
                break
            paths |= found
        return ["https://vinanet.vn" + p for p in paths]

    def parse(self, html: str, url: str) -> tuple[str | None, list[dict]]:
        m = DATE_RE.search(html)
        if not m:
            return None, []
        y, mo, d = m.group(1).split("-")
        date_str = f"{d}/{mo}/{y}"

        soup = BeautifulSoup(html, "lxml")
        content = soup.find(id="abody")
        if content is None:
            return date_str, []

        records = []
        current_region = None
        for el in content.find_all(["strong", "table"]):
            if el.name == "strong":
                text = el.get_text(" ", strip=True)
                for keyword, label in REGION_KEYWORDS:
                    if keyword.lower() in text.lower():
                        current_region = label
                        break
                continue
            for row in el.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) != 2:
                    continue
                province = cells[0].get_text(" ", strip=True)
                if province.lower().startswith("địa phương"):
                    continue
                price = parse_vn_number(cells[1].get_text(" ", strip=True))
                if price is None:
                    continue
                records.append(
                    {
                        "date": date_str,
                        "source": SOURCE,
                        "region": current_region,
                        "province": province,
                        "price_vnd_per_kg": price,
                        "change_vnd_per_kg": None,
                        "benchmark_price_vnd_per_kg": None,
                        "source_url": url,
                    }
                )
        return date_str, records

    def fetch_latest(self) -> list[dict]:
        return self.pick_latest(self.list_articles(max_pages=1), self.parse)

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

    def fetch_url(self, url: str) -> list[dict]:
        html = fetch(url)
        _, rows = self.parse(html, url)
        return rows

    def list_articles_from_sitemap(self, months_back: int = 6) -> list[tuple[str, str]]:
        """Dò bài viết cũ qua sitemap theo tháng (sitemaps/news-YYYY-M.xml, tháng
        không có số 0 đứng đầu). Sitemap có sẵn ngày đăng nên không cần tải từng
        bài chỉ để biết ngày như list_articles()."""
        today = _date.today()
        seen = {}
        for i in range(months_back):
            month_index = today.month - i
            year = today.year + (month_index - 1) // 12
            month = (month_index - 1) % 12 + 1
            sitemap_url = f"https://vinanet.vn/sitemaps/news-{year:04d}-{month}.xml"
            try:
                xml = fetch(sitemap_url)
            except requests.RequestException as e:
                print(f"[{SOURCE}] Lỗi khi tải sitemap {sitemap_url}: {e}", file=sys.stderr)
                continue
            for m in SITEMAP_ENTRY_RE.finditer(xml):
                url, iso_date = m.group(1), m.group(2)
                y, mo, d = iso_date.split("-")
                seen[url] = f"{d}/{mo}/{y}"
        items = sorted(seen.items(), key=lambda kv: date_str_to_sortkey(kv[1]), reverse=True)
        return items

    def fetch_sitemap_backfill(self, months_back: int = 6) -> list[dict]:
        records = []
        articles = self.list_articles_from_sitemap(months_back)
        print(f"[{SOURCE}] Tìm thấy {len(articles)} bài qua sitemap ({months_back} tháng gần đây).")
        for url, _expected_date in articles:
            try:
                html = fetch(url)
                _, rows = self.parse(html, url)
                records.extend(rows)
            except requests.RequestException as e:
                print(f"[{SOURCE}] Lỗi khi tải {url}: {e}", file=sys.stderr)
        return records
