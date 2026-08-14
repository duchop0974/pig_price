"""CLI lấy giá heo hơi từ nhiều nguồn để so sánh, lưu vào SQLite."""
import argparse
import math
import sys
from datetime import datetime
from pathlib import Path

from core.repositories.prices_repo import save_records
from core.scrapers.registry import SCRAPERS, SOURCE_LABELS, SOURCES, fetch_by_date_all, fetch_latest_all
from core.services.export_service import export_to_excel
from core.services.price_service import build_comparison_table, dates_by_source

if sys.stdout.encoding is None or sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def print_comparison_table(records: list[dict]) -> None:
    if not records:
        print("Không có dữ liệu để so sánh.")
        return

    dates = dates_by_source(records)
    print("\nNgày cập nhật theo từng nguồn:")
    for source_key in SOURCES:
        source_label = SOURCE_LABELS[source_key]
        if source_label in dates:
            print(f"  - {source_label}: {dates[source_label]}")
        else:
            print(f"  - {source_label}: (không có dữ liệu)")

    table = build_comparison_table(records)
    print("\nSo sánh giá heo hơi (đ/kg):")
    if table.empty:
        print("(không có dữ liệu)")
    else:
        print(table.to_string(na_rep="-"))
    print()


def run_today(source: str, output: Path) -> None:
    sources = SOURCES if source == "all" else [source]
    records = fetch_latest_all(sources)
    save_records(records, output)
    print_comparison_table(records)


def run_date(source: str, target_date: str, output: Path) -> None:
    sources = SOURCES if source == "all" else [source]
    records = fetch_by_date_all(target_date, sources)
    save_records(records, output)
    print_comparison_table(records)


def run_legacy(source: str, mode: str, url: str | None, output: Path, limit: int) -> None:
    sources = SOURCES if source == "all" else [source]

    if url and (mode != "url" or len(sources) != 1):
        sys.exit("--url chỉ dùng được với --mode url và một --source cụ thể.")

    all_records = []
    for s in sources:
        scraper = SCRAPERS[s]
        if mode == "url":
            if hasattr(scraper, "fetch_url"):
                all_records.extend(scraper.fetch_url(url))
            else:
                print(f"[{SOURCE_LABELS[s]}] Nguồn này không hỗ trợ --mode url, bỏ qua.")
        elif mode == "latest":
            all_records.extend(fetch_latest_all([s]))
        elif mode == "backfill":
            if hasattr(scraper, "fetch_backfill"):
                all_records.extend(scraper.fetch_backfill(limit))
            else:
                print(f"[{SOURCE_LABELS[s]}] Nguồn này chỉ có dữ liệu mới nhất, không backfill được.")
                all_records.extend(fetch_latest_all([s]))

    save_records(all_records, output)


def run_deep_backfill(source: str, days: int, output: Path) -> None:
    """Lấy dữ liệu cũ sâu hơn nhiều so với --mode backfill thường, bằng cách
    dò qua sitemap của từng trang (nnmt/vinanet/baovanhoa) hoặc nhiều trang
    danh mục hơn (vietnambiz), thay vì chỉ đọc đúng trang danh sách/danh mục
    hiện tại (vốn chỉ hiện vài bài gần nhất)."""
    sources = SOURCES if source == "all" else [source]
    months = max(1, math.ceil(days / 30))
    pages = max(1, min(10, math.ceil(days / 8)))

    all_records = []
    for s in sources:
        scraper = SCRAPERS[s]
        if s == "nongnghiepmoitruong":
            rows = scraper.fetch_sitemap_backfill(months_back=months)
        elif s == "vinanet":
            rows = scraper.fetch_sitemap_backfill(months_back=months)
        elif s == "baovanhoa":
            rows = scraper.fetch_sitemap_backfill(days_back=days)
        elif s == "vietnambiz":
            rows = scraper.fetch_deep_backfill(pages=pages)
        else:
            print(f"[{SOURCE_LABELS[s]}] Nguồn này không hỗ trợ lấy sâu, bỏ qua.")
            rows = []
        all_records.extend(rows)

    save_records(all_records, output)


def run_export(db_path: Path, xlsx_path: Path) -> None:
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        n = export_to_excel(db_path, xlsx_path)
    except ValueError as e:
        sys.exit(str(e))
    print(f"Đã xuất {n} dòng ra {xlsx_path}")


def main():
    parser = argparse.ArgumentParser(description="Lấy dữ liệu giá heo hơi.")
    parser.add_argument(
        "--source",
        choices=SOURCES + ["all"],
        default="all",
        help="Nguồn dữ liệu, mặc định lấy tất cả để so sánh",
    )
    parser.add_argument(
        "--mode",
        choices=["today", "date", "latest", "backfill", "deep-backfill", "url", "export"],
        default="today",
        help=(
            "today: giá mới nhất + bảng so sánh (mặc định); "
            "date: giá đúng ngày --date + bảng so sánh; "
            "deep-backfill: lấy sâu nhiều ngày/tháng qua sitemap (nnmt/vinanet/baovanhoa) "
            "hoặc nhiều trang danh mục hơn (vietnambiz); "
            "export: xuất toàn bộ dữ liệu ra file Excel; "
            "latest/backfill/url: chế độ nâng cao, không in bảng so sánh"
        ),
    )
    parser.add_argument("--date", help="Ngày cần lấy, định dạng dd/mm/yyyy (dùng với --mode date)")
    parser.add_argument("--url", help="URL bài viết cụ thể (dùng với --mode url)")
    parser.add_argument(
        "--output", default="data/gia_heo_hoi.db", help="Đường dẫn file dữ liệu SQLite"
    )
    parser.add_argument(
        "--export-file",
        default=None,
        help="Đường dẫn file Excel xuất ra (dùng với --mode export, mặc định data/gia_heo_hoi_YYYYMMDD.xlsx)",
    )
    parser.add_argument(
        "--limit", type=int, default=20, help="Số bài tối đa khi --mode backfill"
    )
    parser.add_argument(
        "--days", type=int, default=30, help="Số ngày muốn lấy sâu về trước khi --mode deep-backfill"
    )
    args = parser.parse_args()

    output = Path(args.output)

    if args.mode == "today":
        run_today(args.source, output)
    elif args.mode == "date":
        if not args.date:
            sys.exit("--date là bắt buộc khi --mode date (định dạng dd/mm/yyyy)")
        try:
            datetime.strptime(args.date, "%d/%m/%Y")
        except ValueError:
            sys.exit(f"Ngày không hợp lệ: {args.date}. Dùng định dạng dd/mm/yyyy, vd 30/07/2026")
        run_date(args.source, args.date, output)
    elif args.mode == "deep-backfill":
        run_deep_backfill(args.source, args.days, output)
    elif args.mode == "export":
        xlsx_path = Path(args.export_file) if args.export_file else Path(f"data/gia_heo_hoi_{datetime.now():%Y%m%d}.xlsx")
        run_export(output, xlsx_path)
    else:
        run_legacy(args.source, args.mode, args.url, output, args.limit)


if __name__ == "__main__":
    main()
