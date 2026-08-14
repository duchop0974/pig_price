"""Hàm dùng chung cho các scraper: tải trang, chuẩn hoá tên tỉnh/số, parse bảng 3 cột."""
import re
import unicodedata

import requests

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
REGION_BUCKETS = [label for _, label in REGION_KEYWORDS]

# Các nguồn gắn nhãn miền không đồng nhất (vd. TÂY NAM BỘ/ĐÔNG NAM BỘ đều
# thuộc miền Nam) nên quy hết về 3 miền chuẩn ở REGION_BUCKETS.
REGION_ALIAS = {
    "MIỀN BẮC": "Miền Bắc",
    "Miền Bắc": "Miền Bắc",
    "MIỀN TRUNG": "Miền Trung - Tây Nguyên",
    "Miền Trung - Tây Nguyên": "Miền Trung - Tây Nguyên",
    "TÂY NAM BỘ": "Miền Nam",
    "ĐÔNG NAM BỘ": "Miền Nam",
    "Miền Nam": "Miền Nam",
}


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


def date_str_to_sortkey(date_str: str) -> tuple[int, int, int]:
    d, m, y = date_str.split("/")
    return (int(y), int(m), int(d))
