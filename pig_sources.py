"""Logic lấy & chuẩn hoá giá heo hơi từ nhiều nguồn, dùng chung cho CLI và web app."""
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

REGION_KEYWORDS = [
    ("Bắc", "Miền Bắc"),
    ("Trung", "Miền Trung - Tây Nguyên"),
    ("Nam", "Miền Nam"),
]

SOURCES = ["nongnghiepmoitruong", "vietnambiz", "greenfeed", "vinanet"]
SOURCE_LABELS = {
    "nongnghiepmoitruong": "nongnghiepmoitruong.vn",
    "vietnambiz": "vietnambiz.vn",
    "greenfeed": "greenfeed.com.vn",
    "vinanet": "vinanet.vn",
}
SOURCE_ORDER = [SOURCE_LABELS[s] for s in SOURCES]


def fetch(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def guess_region(heading_text: str) -> str:
    for keyword, label in REGION_KEYWORDS:
        if keyword.lower() in heading_text.lower():
            return label
    return heading_text.strip()


def parse_vn_number(text: str) -> int | None:
    """Chuyển '59.000' hoặc '59,000' hoặc '-1.000' thành số nguyên."""
    text = text.strip().replace("\xa0", "")
    if text in ("", "-", "—"):
        return 0 if text in ("-", "—") else None
    cleaned = re.sub(r"[^\d-]", "", text)
    if cleaned in ("", "-"):
        return None
    return int(cleaned)


_PROVINCE_PREFIX_RE = re.compile(
    r"^(TP\.?\s*|T\.P\.?\s*|TỈNH\s+|THÀNH PHỐ\s+)", re.IGNORECASE
)
_PROVINCE_ALIASES = {
    "HCM": "HO CHI MINH",
    "TPHCM": "HO CHI MINH",
}


def normalize_province(name: str) -> str:
    """Chuẩn hoá tên tỉnh để so khớp giữa các nguồn khác định dạng nhau
    (vd. 'Hà Nội' và 'TP HÀ NỘI' cùng ra 'HA NOI')."""
    name = _PROVINCE_PREFIX_RE.sub("", name.strip())
    decomposed = unicodedata.normalize("NFKD", name)
    no_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    no_marks = no_marks.replace("Đ", "D").replace("đ", "d")
    cleaned = re.sub(r"[^A-Za-z ]", " ", no_marks)
    key = re.sub(r"\s+", " ", cleaned).strip().upper()
    return _PROVINCE_ALIASES.get(key, key)


def parse_3col_table(content, url: str, date_str: str, source: str) -> list[dict]:
    """Parse các bảng 3 cột (Địa phương / Giá / Biến động), dùng chung cho
    nongnghiepmoitruong.vn và vietnambiz.vn vì hai trang này cùng một định dạng."""
    records = []
    current_region = None
    for el in content.find_all(["h2", "table"]):
        if el.name == "h2":
            current_region = guess_region(el.get_text(" ", strip=True))
            continue
        for row in el.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
            if len(cells) != 3:
                continue
            province, price_text, change_text = cells
            if province.lower().startswith("địa phương"):
                continue
            price = parse_vn_number(price_text)
            change = parse_vn_number(change_text)
            if price is None:
                continue
            records.append(
                {
                    "date": date_str,
                    "source": source,
                    "region": current_region,
                    "province": province,
                    "price_vnd_per_kg": price,
                    "change_vnd_per_kg": change,
                    "benchmark_price_vnd_per_kg": None,
                    "source_url": url,
                }
            )
    return records


# ---------------------------------------------------------------------------
# Nguồn 1: nongnghiepmoitruong.vn (báo Nông nghiệp và Môi trường)
# ---------------------------------------------------------------------------
NNMT_SOURCE = SOURCE_LABELS["nongnghiepmoitruong"]
NNMT_TAG_URL = "https://nongnghiepmoitruong.vn/gia-heo-hoi-hom-nay-tag90954/"
NNMT_ARTICLE_RE = re.compile(
    r"https://nongnghiepmoitruong\.vn/gia-heo-hoi-hom-nay-(\d{1,2})-(\d{1,2})-(\d{4})[^\"'\s]*\.html"
)


def nnmt_list_articles() -> list[tuple[str, str]]:
    """Trả về danh sách (url, ngày dd/mm/yyyy) duy nhất, mới nhất trước."""
    html = fetch(NNMT_TAG_URL)
    seen = {}
    for m in NNMT_ARTICLE_RE.finditer(html):
        url = m.group(0)
        day, month, year = m.group(1), m.group(2), m.group(3)
        date_str = f"{int(day):02d}/{int(month):02d}/{year}"
        seen[url] = (date_str, (int(year), int(month), int(day)))
    items = sorted(seen.items(), key=lambda kv: kv[1][1], reverse=True)
    return [(url, date_str) for url, (date_str, _) in items]


def nnmt_parse(html: str, url: str, date_str: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    content = soup.find("div", class_="detail-content") or soup
    return parse_3col_table(content, url, date_str, NNMT_SOURCE)


def nnmt_fetch_latest() -> list[dict]:
    articles = nnmt_list_articles()
    if not articles:
        return []
    url, date_str = articles[0]
    html = fetch(url)
    return nnmt_parse(html, url, date_str)


def nnmt_fetch_by_date(target_date: str) -> list[dict]:
    for url, date_str in nnmt_list_articles():
        if date_str == target_date:
            html = fetch(url)
            return nnmt_parse(html, url, date_str)
    return []


def nnmt_fetch_backfill(limit: int) -> list[dict]:
    records = []
    for url, date_str in nnmt_list_articles()[:limit]:
        try:
            html = fetch(url)
            records.extend(nnmt_parse(html, url, date_str))
        except requests.RequestException as e:
            print(f"[{NNMT_SOURCE}] Lỗi khi tải {url}: {e}", file=sys.stderr)
    return records


def nnmt_fetch_url(url: str) -> list[dict]:
    m = NNMT_ARTICLE_RE.search(url)
    date_str = f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}" if m else "unknown"
    html = fetch(url)
    return nnmt_parse(html, url, date_str)


def nnmt_list_articles_from_sitemap(months_back: int = 6) -> list[tuple[str, str]]:
    """Dò bài viết cũ qua sitemap theo tháng (sitemap-post-YYYY-MM.xml), không
    bị giới hạn 'cửa sổ trượt' như trang danh sách (nnmt_list_articles)."""
    from datetime import date

    today = date.today()
    seen = {}
    for i in range(months_back):
        month_index = today.month - i
        year = today.year + (month_index - 1) // 12
        month = (month_index - 1) % 12 + 1
        sitemap_url = f"https://nongnghiepmoitruong.vn/sitemap-post-{year:04d}-{month:02d}.xml"
        try:
            xml = fetch(sitemap_url)
        except requests.RequestException as e:
            print(f"[{NNMT_SOURCE}] Lỗi khi tải sitemap {sitemap_url}: {e}", file=sys.stderr)
            continue
        for m in NNMT_ARTICLE_RE.finditer(xml):
            url = m.group(0)
            d, mo, y = m.group(1), m.group(2), m.group(3)
            date_str = f"{int(d):02d}/{int(mo):02d}/{y}"
            seen[url] = date_str
    items = sorted(seen.items(), key=lambda kv: date_str_to_sortkey(kv[1]), reverse=True)
    return [(url, date_str) for url, date_str in items]


def nnmt_fetch_sitemap_backfill(months_back: int = 6) -> list[dict]:
    records = []
    articles = nnmt_list_articles_from_sitemap(months_back)
    print(f"[{NNMT_SOURCE}] Tìm thấy {len(articles)} bài qua sitemap ({months_back} tháng gần đây).")
    for url, date_str in articles:
        try:
            html = fetch(url)
            records.extend(nnmt_parse(html, url, date_str))
        except requests.RequestException as e:
            print(f"[{NNMT_SOURCE}] Lỗi khi tải {url}: {e}", file=sys.stderr)
    return records


# ---------------------------------------------------------------------------
# Nguồn 2: vietnambiz.vn
# ---------------------------------------------------------------------------
VNB_SOURCE = SOURCE_LABELS["vietnambiz"]
VNB_TAG_URL = "https://vietnambiz.vn/chu-de/gia-heo-hoi-80.htm"
VNB_ARTICLE_RE = re.compile(r'href="(/gia-heo-hoi-hom-nay[^"]*\.htm)"')
VNB_DATE_RE = re.compile(r'property="article:published_time" content="(\d{4}-\d{2}-\d{2})')


def vnb_list_articles(pages: int = 1) -> list[str]:
    """Trả về danh sách URL bài viết (chưa biết ngày, sẽ lấy khi tải từng bài).
    pages > 1 sẽ duyệt thêm các trang /chu-de/gia-heo-hoi-80/trang-N.htm để
    dò được bài cũ hơn (dùng cho backfill sâu)."""
    paths = set()
    for page in range(1, pages + 1):
        url = VNB_TAG_URL if page == 1 else f"https://vietnambiz.vn/chu-de/gia-heo-hoi-80/trang-{page}.htm"
        try:
            html = fetch(url)
        except requests.RequestException as e:
            print(f"[{VNB_SOURCE}] Lỗi khi tải {url}: {e}", file=sys.stderr)
            break
        found = set(VNB_ARTICLE_RE.findall(html))
        if not found and page > 1:
            break
        paths |= found
    return ["https://vietnambiz.vn" + p for p in paths]


def vnb_parse(html: str, url: str) -> tuple[str | None, list[dict]]:
    m = VNB_DATE_RE.search(html)
    if not m:
        return None, []
    y, mo, d = m.group(1).split("-")
    date_str = f"{d}/{mo}/{y}"
    soup = BeautifulSoup(html, "lxml")
    content = soup.find("div", attrs={"data-role": "content"}) or soup
    return date_str, parse_3col_table(content, url, date_str, VNB_SOURCE)


def vnb_fetch_latest() -> list[dict]:
    best_date = None
    best_records = None
    for url in vnb_list_articles():
        try:
            html = fetch(url)
            date_str, rows = vnb_parse(html, url)
        except requests.RequestException as e:
            print(f"[{VNB_SOURCE}] Lỗi khi tải {url}: {e}", file=sys.stderr)
            continue
        if date_str and (best_date is None or date_str_to_sortkey(date_str) > date_str_to_sortkey(best_date)):
            best_date, best_records = date_str, rows
    return best_records or []


def vnb_fetch_by_date(target_date: str) -> list[dict]:
    for url in vnb_list_articles():
        try:
            html = fetch(url)
            date_str, rows = vnb_parse(html, url)
        except requests.RequestException as e:
            print(f"[{VNB_SOURCE}] Lỗi khi tải {url}: {e}", file=sys.stderr)
            continue
        if date_str == target_date:
            return rows
    return []


def vnb_fetch_backfill(limit: int) -> list[dict]:
    records = []
    for url in vnb_list_articles()[:limit]:
        try:
            html = fetch(url)
            _, rows = vnb_parse(html, url)
            records.extend(rows)
        except requests.RequestException as e:
            print(f"[{VNB_SOURCE}] Lỗi khi tải {url}: {e}", file=sys.stderr)
    return records


def vnb_fetch_deep_backfill(pages: int = 5) -> list[dict]:
    records = []
    articles = vnb_list_articles(pages=pages)
    print(f"[{VNB_SOURCE}] Tìm thấy {len(articles)} bài qua {pages} trang danh mục.")
    for url in articles:
        try:
            html = fetch(url)
            _, rows = vnb_parse(html, url)
            records.extend(rows)
        except requests.RequestException as e:
            print(f"[{VNB_SOURCE}] Lỗi khi tải {url}: {e}", file=sys.stderr)
    return records


def vnb_fetch_url(url: str) -> list[dict]:
    html = fetch(url)
    _, rows = vnb_parse(html, url)
    return rows


def date_str_to_sortkey(date_str: str) -> tuple[int, int, int]:
    d, m, y = date_str.split("/")
    return (int(y), int(m), int(d))


# ---------------------------------------------------------------------------
# Nguồn 3: greenfeed.com.vn (bảng giá thị trường của công ty thức ăn chăn nuôi)
# Trang chỉ hiển thị đúng 1 ngày cập nhật gần nhất (đã kiểm chứng: query
# ?date=YYYY-MM-DD với ngày khác ngày cache hiện tại trả về rỗng), nên chỉ hỗ
# trợ lấy dữ liệu mới nhất một cách chắc chắn; theo-ngày chỉ thành công nếu
# đúng ngày trang đang cache.
# ---------------------------------------------------------------------------
GF_SOURCE = SOURCE_LABELS["greenfeed"]
GF_URL = (
    "https://www.greenfeed.com.vn/thuc-an-chan-nuoi-gia-suc-gia-cam/"
    "bang-gia-thi-truong/heo-hoi/?type=vat-nuoi-price"
)
GF_DATE_RE = re.compile(r"Cập nhật ngày\s*(\d{2}/\d{2}/\d{4})")


def gf_parse(html: str) -> tuple[str | None, list[dict]]:
    m = GF_DATE_RE.search(html)
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
                "source": GF_SOURCE,
                "region": current_region,
                "province": market,
                "price_vnd_per_kg": heo_hoi_price,
                "change_vnd_per_kg": heo_hoi_change,
                "benchmark_price_vnd_per_kg": greenfeed_price,
                "source_url": GF_URL,
            }
        )
    return date_str, records


def gf_fetch_latest() -> list[dict]:
    html = fetch(GF_URL)
    _, records = gf_parse(html)
    return records


def gf_fetch_by_date(target_date: str) -> list[dict]:
    d, m, y = target_date.split("/")
    iso_date = f"{y}-{m}-{d}"
    html = fetch(GF_URL + "&date=" + iso_date)
    date_str, records = gf_parse(html)
    if date_str != target_date:
        return []
    return records


# ---------------------------------------------------------------------------
# Nguồn 4: vinanet.vn (trang tin hàng hoá/thị trường)
# ---------------------------------------------------------------------------
VNN_SOURCE = SOURCE_LABELS["vinanet"]
VNN_CATEGORY_URL = "https://vinanet.vn/thit-san-pham-thit/ic-21.html"
VNN_ARTICLE_RE = re.compile(r'href="(/[^"]*gia-heo-hoi-hom-nay[^"]*\.html)"')
VNN_DATE_RE = re.compile(r'property="article:published_time"\s+content="(\d{4}-\d{2}-\d{2})T')


def vnn_list_articles(max_pages: int = 3) -> list[str]:
    """Trả về danh sách URL bài viết (chưa biết ngày) từ trang danh mục,
    duyệt qua vài trang để có đủ bài cho backfill."""
    paths = set()
    for page in range(1, max_pages + 1):
        url = VNN_CATEGORY_URL if page == 1 else f"{VNN_CATEGORY_URL}?page={page}"
        html = fetch(url)
        found = set(VNN_ARTICLE_RE.findall(html))
        new_paths = found - paths
        if not new_paths and page > 1:
            break
        paths |= found
    return ["https://vinanet.vn" + p for p in paths]


def vnn_parse(html: str, url: str) -> tuple[str | None, list[dict]]:
    m = VNN_DATE_RE.search(html)
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
                    "source": VNN_SOURCE,
                    "region": current_region,
                    "province": province,
                    "price_vnd_per_kg": price,
                    "change_vnd_per_kg": None,
                    "benchmark_price_vnd_per_kg": None,
                    "source_url": url,
                }
            )
    return date_str, records


def vnn_fetch_latest() -> list[dict]:
    best_date = None
    best_records = None
    for url in vnn_list_articles(max_pages=1):
        try:
            html = fetch(url)
            date_str, rows = vnn_parse(html, url)
        except requests.RequestException as e:
            print(f"[{VNN_SOURCE}] Lỗi khi tải {url}: {e}", file=sys.stderr)
            continue
        if date_str and (best_date is None or date_str_to_sortkey(date_str) > date_str_to_sortkey(best_date)):
            best_date, best_records = date_str, rows
    return best_records or []


def vnn_fetch_by_date(target_date: str) -> list[dict]:
    for url in vnn_list_articles():
        try:
            html = fetch(url)
            date_str, rows = vnn_parse(html, url)
        except requests.RequestException as e:
            print(f"[{VNN_SOURCE}] Lỗi khi tải {url}: {e}", file=sys.stderr)
            continue
        if date_str == target_date:
            return rows
    return []


def vnn_fetch_backfill(limit: int) -> list[dict]:
    records = []
    for url in vnn_list_articles()[:limit]:
        try:
            html = fetch(url)
            _, rows = vnn_parse(html, url)
            records.extend(rows)
        except requests.RequestException as e:
            print(f"[{VNN_SOURCE}] Lỗi khi tải {url}: {e}", file=sys.stderr)
    return records


def vnn_fetch_url(url: str) -> list[dict]:
    html = fetch(url)
    _, rows = vnn_parse(html, url)
    return rows


VNN_SITEMAP_ENTRY_RE = re.compile(
    r"<loc>(https://vinanet\.vn/[^<]*gia-heo-hoi-hom-nay[^<]*)</loc>"
    r"<lastmod>(\d{4}-\d{2}-\d{2})T"
)


def vnn_list_articles_from_sitemap(months_back: int = 6) -> list[tuple[str, str]]:
    """Dò bài viết cũ qua sitemap theo tháng (sitemaps/news-YYYY-M.xml, tháng
    không có số 0 đứng đầu). Sitemap có sẵn ngày đăng nên không cần tải từng
    bài chỉ để biết ngày như vnn_list_articles()."""
    from datetime import date

    today = date.today()
    seen = {}
    for i in range(months_back):
        month_index = today.month - i
        year = today.year + (month_index - 1) // 12
        month = (month_index - 1) % 12 + 1
        sitemap_url = f"https://vinanet.vn/sitemaps/news-{year:04d}-{month}.xml"
        try:
            xml = fetch(sitemap_url)
        except requests.RequestException as e:
            print(f"[{VNN_SOURCE}] Lỗi khi tải sitemap {sitemap_url}: {e}", file=sys.stderr)
            continue
        for m in VNN_SITEMAP_ENTRY_RE.finditer(xml):
            url, iso_date = m.group(1), m.group(2)
            y, mo, d = iso_date.split("-")
            seen[url] = f"{d}/{mo}/{y}"
    items = sorted(seen.items(), key=lambda kv: date_str_to_sortkey(kv[1]), reverse=True)
    return items


def vnn_fetch_sitemap_backfill(months_back: int = 6) -> list[dict]:
    records = []
    articles = vnn_list_articles_from_sitemap(months_back)
    print(f"[{VNN_SOURCE}] Tìm thấy {len(articles)} bài qua sitemap ({months_back} tháng gần đây).")
    for url, _expected_date in articles:
        try:
            html = fetch(url)
            _, rows = vnn_parse(html, url)
            records.extend(rows)
        except requests.RequestException as e:
            print(f"[{VNN_SOURCE}] Lỗi khi tải {url}: {e}", file=sys.stderr)
    return records


# ---------------------------------------------------------------------------
# Điều phối theo nguồn (dùng key ngắn: nongnghiepmoitruong/vietnambiz/greenfeed/vinanet)
# ---------------------------------------------------------------------------
def fetch_latest_all(sources: list[str] | None = None) -> list[dict]:
    """Lấy dữ liệu mới nhất hiện có của từng nguồn (không nhất thiết cùng ngày
    do các nguồn có độ trễ xuất bản khác nhau)."""
    sources = sources or SOURCES
    records = []
    for src in sources:
        try:
            if src == "nongnghiepmoitruong":
                rows = nnmt_fetch_latest()
            elif src == "vietnambiz":
                rows = vnb_fetch_latest()
            elif src == "greenfeed":
                rows = gf_fetch_latest()
            elif src == "vinanet":
                rows = vnn_fetch_latest()
            else:
                continue
            print(f"[{SOURCE_LABELS[src]}] lấy được {len(rows)} dòng")
            records.extend(rows)
        except requests.RequestException as e:
            print(f"[{SOURCE_LABELS[src]}] Lỗi khi tải dữ liệu: {e}", file=sys.stderr)
    return records


def fetch_by_date_all(target_date: str, sources: list[str] | None = None) -> list[dict]:
    """Lấy dữ liệu đúng ngày target_date (dd/mm/yyyy) từ từng nguồn nếu có."""
    sources = sources or SOURCES
    records = []
    for src in sources:
        try:
            if src == "nongnghiepmoitruong":
                rows = nnmt_fetch_by_date(target_date)
            elif src == "vietnambiz":
                rows = vnb_fetch_by_date(target_date)
            elif src == "greenfeed":
                rows = gf_fetch_by_date(target_date)
            elif src == "vinanet":
                rows = vnn_fetch_by_date(target_date)
            else:
                continue
            if rows:
                print(f"[{SOURCE_LABELS[src]}] {target_date}: lấy được {len(rows)} dòng")
            else:
                print(f"[{SOURCE_LABELS[src]}] Không có dữ liệu cho ngày {target_date}.")
            records.extend(rows)
        except requests.RequestException as e:
            print(f"[{SOURCE_LABELS[src]}] Lỗi khi tải dữ liệu: {e}", file=sys.stderr)
    return records


DB_COLUMNS = [
    "date",
    "source",
    "region",
    "province",
    "price_vnd_per_kg",
    "change_vnd_per_kg",
    "benchmark_price_vnd_per_kg",
    "source_url",
]

_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    date TEXT NOT NULL,
    source TEXT NOT NULL,
    region TEXT,
    province TEXT NOT NULL,
    price_vnd_per_kg INTEGER,
    change_vnd_per_kg INTEGER,
    benchmark_price_vnd_per_kg INTEGER,
    source_url TEXT,
    PRIMARY KEY (date, source, province)
);
CREATE INDEX IF NOT EXISTS idx_prices_date ON prices(date);
CREATE INDEX IF NOT EXISTS idx_prices_source ON prices(source);
CREATE INDEX IF NOT EXISTS idx_prices_province ON prices(province);
"""


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Mở kết nối SQLite, tạo bảng/index nếu chưa có. WAL giúp đọc và ghi
    không chặn lẫn nhau khi nhiều tiến trình (server + script CLI) cùng
    dùng chung 1 file .db."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript(_DB_SCHEMA)
    return conn


def save_records(records: list[dict], db_path: Path) -> None:
    if not records:
        print("Không có dữ liệu mới để lưu.")
        return

    rows = [
        (
            r["date"],
            r["source"],
            r.get("region"),
            r["province"],
            r.get("price_vnd_per_kg"),
            r.get("change_vnd_per_kg"),
            r.get("benchmark_price_vnd_per_kg"),
            r.get("source_url"),
        )
        for r in records
    ]

    conn = get_connection(db_path)
    try:
        conn.executemany(
            """
            INSERT INTO prices (date, source, region, province, price_vnd_per_kg,
                                 change_vnd_per_kg, benchmark_price_vnd_per_kg, source_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, source, province) DO UPDATE SET
                region=excluded.region,
                price_vnd_per_kg=excluded.price_vnd_per_kg,
                change_vnd_per_kg=excluded.change_vnd_per_kg,
                benchmark_price_vnd_per_kg=excluded.benchmark_price_vnd_per_kg,
                source_url=excluded.source_url
            """,
            rows,
        )
        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    finally:
        conn.close()

    print(f"Đã lưu {len(records)} dòng mới, tổng {total} dòng vào {db_path}")


def load_records_df(db_path: Path) -> pd.DataFrame:
    if not db_path.exists():
        return pd.DataFrame(columns=DB_COLUMNS)
    conn = get_connection(db_path)
    try:
        return pd.read_sql_query(f"SELECT {', '.join(DB_COLUMNS)} FROM prices", conn)
    finally:
        conn.close()


EXPORT_COLUMNS = {
    "date": "Ngày",
    "source": "Nguồn",
    "region": "Miền",
    "province": "Địa phương",
    "price_vnd_per_kg": "Giá (đ/kg)",
    "change_vnd_per_kg": "Biến động (đ/kg)",
    "benchmark_price_vnd_per_kg": "Giá heo cám GreenFeed (đ/kg)",
    "source_url": "Nguồn URL",
}


def export_to_excel(db_path: Path, dest) -> int:
    """Xuất toàn bộ dữ liệu ra Excel. `dest` có thể là đường dẫn file hoặc
    buffer (BytesIO, dùng khi trả file trực tiếp qua web). Trả về số dòng
    đã xuất."""
    df = load_records_df(db_path)
    if df.empty:
        raise ValueError("Chưa có dữ liệu để xuất.")

    export_df = df.copy()
    export_df["_date_sort"] = pd.to_datetime(export_df["date"], format="%d/%m/%Y")
    export_df = export_df.sort_values(["_date_sort", "source", "province"]).drop(columns="_date_sort")
    export_df = export_df.rename(columns=EXPORT_COLUMNS)

    with pd.ExcelWriter(dest, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Gia heo hoi")
        ws = writer.sheets["Gia heo hoi"]
        for col_idx, col_name in enumerate(export_df.columns, start=1):
            max_len = max(
                len(str(col_name)),
                int(export_df.iloc[:, col_idx - 1].fillna("").astype(str).str.len().max())
                if len(export_df)
                else 0,
            )
            ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = min(max_len + 2, 45)
        ws.freeze_panes = "A2"

    return len(export_df)


def build_comparison_table(records: list[dict]) -> pd.DataFrame:
    """Pivot records hiện tại thành bảng: hàng=tỉnh, cột=nguồn, giá trị=giá."""
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    df["_key"] = df["province"].map(normalize_province)
    # giữ tên tỉnh gốc đầu tiên gặp cho mỗi khoá, để hiển thị đẹp
    display_names = df.drop_duplicates("_key").set_index("_key")["province"]
    pivot = df.pivot_table(
        index="_key", columns="source", values="price_vnd_per_kg", aggfunc="first"
    )
    pivot.index = pivot.index.map(display_names)
    pivot.index.name = "Địa phương"
    cols = [c for c in SOURCE_ORDER if c in pivot.columns]
    return pivot[cols]


def dates_by_source(records: list[dict]) -> dict[str, str]:
    """Ngày thực tế mà mỗi nguồn trả về trong lần fetch này."""
    result = {}
    for r in records:
        result.setdefault(r["source"], r["date"])
    return result
