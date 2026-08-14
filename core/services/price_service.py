"""Xử lý/tổng hợp dữ liệu giá: pivot bảng so sánh, suy luận miền theo tỉnh."""
import pandas as pd

from core.scrapers.registry import SOURCE_ORDER
from core.scrapers.utils import REGION_ALIAS, normalize_province


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


def build_province_region_map(df: pd.DataFrame) -> dict[str, str]:
    """Suy ra miền (Bắc/Trung/Nam) cho từng tỉnh từ nhãn 'region' đã cào
    được, lấy miền xuất hiện nhiều nhất cho mỗi tỉnh vì các nguồn gắn nhãn
    không đồng nhất với nhau (vd. một nguồn tách riêng Tây Nam Bộ/Đông Nam
    Bộ, nguồn khác gộp chung Miền Nam)."""
    if df.empty or "region" not in df.columns:
        return {}
    tmp = df.dropna(subset=["region"]).copy()
    if tmp.empty:
        return {}
    tmp["_key"] = tmp["province"].map(normalize_province)
    tmp["_bucket"] = tmp["region"].map(REGION_ALIAS)
    tmp = tmp.dropna(subset=["_bucket"])
    if tmp.empty:
        return {}
    counts = tmp.groupby(["_key", "_bucket"]).size().reset_index(name="n")
    winners = counts.loc[counts.groupby("_key")["n"].idxmax()]
    return dict(zip(winners["_key"], winners["_bucket"]))


def dates_by_source(records: list[dict]) -> dict[str, str]:
    """Ngày thực tế mà mỗi nguồn trả về trong lần fetch này."""
    result = {}
    for r in records:
        result.setdefault(r["source"], r["date"])
    return result
