"""Xuất dữ liệu ra Excel: giá heo hơi và kế hoạch xuất bán."""
from pathlib import Path

import pandas as pd

from core.repositories.prices_repo import load_records_df
from core.repositories.sale_allocations_repo import list_allocations_for_export
from core.repositories.sale_plans_repo import list_sale_plans_for_export

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


SALE_PLAN_EXPORT_COLUMNS = {
    "plan_code": "Mã kế hoạch",
    "id": "ID nội bộ",
    "planned_date": "Ngày dự kiến",
    "farm": "Trang trại",
    "province": "Tỉnh",
    "zone": "Khu",
    "shed": "Chuồng",
    "lot": "Lô",
    "pig_type_name": "Loại heo",
    "quantity": "Số lượng dự kiến (con)",
    "received_quantity": "Số lượng thực nhận (con)",
    "received_at": "Ngày nhận",
    "received_by": "Người nhận",
    "allocated_quantity": "Số lượng đã phân bổ (con)",
    "remaining_quantity": "Số lượng còn lại (con)",
    "note": "Ghi chú",
    "status": "Trạng thái",
    "created_by": "Người tạo",
    "approved_by": "Duyệt bởi",
    "approved_at": "Duyệt lúc",
    "rejected_by": "Từ chối bởi",
    "rejected_at": "Từ chối lúc",
    "rejected_reason": "Lý do từ chối",
    "created_at": "Tạo lúc",
    "created_ip": "IP tạo",
    "updated_by": "Người sửa gần nhất",
    "updated_at": "Sửa lúc",
    "updated_ip": "IP sửa",
}

SALE_ALLOCATION_EXPORT_COLUMNS = {
    "plan_code": "Mã kế hoạch bán",
    "id": "ID nội bộ",
    "sale_plan_code": "Mã kế hoạch trại",
    "planned_date": "Ngày dự kiến",
    "farm": "Trang trại",
    "province": "Tỉnh",
    "zone": "Khu",
    "shed": "Chuồng",
    "lot": "Lô",
    "pig_type_name": "Loại heo",
    "quantity": "Số lượng (con)",
    "selling_price": "Giá chào bán (đ/kg)",
    "note": "Ghi chú",
    "customer_name": "Khách hàng",
    "customer_phone": "SĐT khách hàng",
    "customer_email": "Email khách hàng",
    "customer_contact_person": "Người liên hệ khách hàng",
    "contact_note": "Ghi chú liên hệ",
    "contacted_by": "Người liên hệ",
    "contacted_at": "Liên hệ lúc",
    "confirmed_sale_at": "Ngày chốt bán",
    "delivery_time": "Khung giờ giao",
    "payment_method": "Hình thức thanh toán",
    "actual_price": "Giá bán thực tế (đ/kg)",
    "actual_quantity": "Số lượng bán thực tế (con)",
    "paid_amount": "Số tiền đã thu (đ)",
    "paid_at": "Ngày thu tiền",
    "weighing_ref": "Số chứng từ cân",
    "invoice_number": "Số hoá đơn",
    "invoiced_by": "Người lập hoá đơn",
    "invoiced_at": "Lập hoá đơn lúc",
    "revenue_recorded_by": "Người ghi nhận doanh thu",
    "revenue_recorded_at": "Ghi nhận doanh thu lúc",
    "status": "Trạng thái",
    "created_by": "Người tạo",
    "created_at": "Tạo lúc",
    "created_ip": "IP tạo",
    "updated_by": "Người sửa gần nhất",
    "updated_at": "Sửa lúc",
    "updated_ip": "IP sửa",
}

QUOTATION_COLUMNS = {
    "plan_code": "Mã kế hoạch bán",
    "planned_date": "Ngày dự kiến",
    "farm": "Trang trại",
    "province": "Tỉnh",
    "zone": "Khu",
    "pig_type_name": "Loại heo",
    "quantity": "Số lượng (con)",
    "selling_price": "Giá chào bán (đ/kg)",
    "delivery_time": "Khung giờ giao",
    "payment_method": "Hình thức thanh toán",
    "note": "Ghi chú",
}

PAYMENT_METHOD_LABEL = {
    "bank_transfer_immediate": "Chuyển khoản ngay",
    "bank_transfer_24h": "Chuyển khoản trước 24h",
    "cash": "Tiền mặt",
    "credit": "Công nợ",
    "other": "Khác",
}

SALE_PLAN_STATUS_LABEL = {
    "active": "Đang chờ",  # fallback cho dữ liệu cũ, không còn ghi mới giá trị này
    "pending_approval": "Chờ duyệt",
    "approved": "Đã duyệt",
    "rejected": "Từ chối",
    "cancelled": "Đã hủy",
    "disabled": "Đã vô hiệu hoá",
}

ALLOCATION_STATUS_LABEL = {
    "active": "Đang xử lý",
    "done": "Đã bán",
    "cancelled": "Đã hủy",
    "disabled": "Đã vô hiệu hoá",
}


def _autosize_and_freeze(df: pd.DataFrame, ws) -> None:
    for col_idx, col_name in enumerate(df.columns, start=1):
        max_len = max(
            len(str(col_name)),
            int(df.iloc[:, col_idx - 1].fillna("").astype(str).str.len().max()) if len(df) else 0,
        )
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = min(max_len + 2, 45)
    ws.freeze_panes = "A2"


def export_sale_plans_to_excel(db_path: Path, dest) -> int:
    """Xuất toàn bộ kế hoạch trại (nguồn cung, BM01) ra Excel, gồm cả trường
    ẩn để đối soát. `dest` có thể là đường dẫn file hoặc buffer (BytesIO)."""
    rows = list_sale_plans_for_export(db_path)
    if not rows:
        raise ValueError("Chưa có kế hoạch nào để xuất.")

    df = pd.DataFrame(rows).drop(columns=["pig_type", "farm_id"])
    df["status"] = df["status"].map(lambda s: SALE_PLAN_STATUS_LABEL.get(s, s))
    df = df.rename(columns=SALE_PLAN_EXPORT_COLUMNS)

    with pd.ExcelWriter(dest, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Ke hoach trai")
        _autosize_and_freeze(df, writer.sheets["Ke hoach trai"])

    return len(df)


def export_sale_allocations_to_excel(db_path: Path, dest) -> int:
    """Xuất toàn bộ kế hoạch bán (Phòng bán hàng, BM02) ra Excel, gồm cả
    trường ẩn để đối soát."""
    rows = list_allocations_for_export(db_path)
    if not rows:
        raise ValueError("Chưa có kế hoạch bán nào để xuất.")

    df = pd.DataFrame(rows).drop(columns=["pig_type", "sale_plan_id", "customer_id"])
    df["status"] = df["status"].map(lambda s: ALLOCATION_STATUS_LABEL.get(s, s))
    df["payment_method"] = df["payment_method"].map(lambda s: PAYMENT_METHOD_LABEL.get(s, s))
    df = df.rename(columns=SALE_ALLOCATION_EXPORT_COLUMNS)

    with pd.ExcelWriter(dest, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Ke hoach ban")
        _autosize_and_freeze(df, writer.sheets["Ke hoach ban"])

    return len(df)


def export_allocation_quotation_to_excel(db_path: Path, dest, allocation_ids: list[int]) -> int:
    """Xuất file 'chào hàng' gọn (không cột nội bộ/audit) từ 1 hoặc nhiều kế
    hoạch bán được chọn — dùng để gửi khách hàng."""
    rows = [r for r in list_allocations_for_export(db_path) if r["id"] in set(allocation_ids)]
    if not rows:
        raise ValueError("Không tìm thấy kế hoạch bán để xuất.")

    df = pd.DataFrame(rows)[list(QUOTATION_COLUMNS.keys())]
    df = df.rename(columns=QUOTATION_COLUMNS)

    with pd.ExcelWriter(dest, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Chao hang")
        _autosize_and_freeze(df, writer.sheets["Chao hang"])

    return len(df)
