"""Prepare the bakery sales dataset for PostgreSQL CSV import."""

from __future__ import annotations

import csv
import argparse
from pathlib import Path


OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "bakery_sales.csv"

HEADER_MAP = {
    "Order_ID": "order_id",
    "Customer_ID": "customer_id",
    "Customer_Age": "customer_age",
    "Customer_Gender": "customer_gender",
    "Customer_Segment": "customer_segment",
    "Loyalty_Member": "loyalty_member",
    "Date": "sale_date",
    "Year": "sale_year",
    "Month": "sale_month",
    "Day": "sale_day",
    "Day_of_Week": "day_of_week",
    "Weekend": "weekend",
    "Hour": "sale_hour",
    "Time": "sale_time",
    "Season": "season",
    "Festival": "festival",
    "Weather": "weather",
    "Temperature": "temperature_c",
    "Product": "product",
    "Category": "category",
    "Quantity": "quantity",
    "Unit_Price": "unit_price",
    "Cost_Price": "cost_price",
    "Discount_Percentage": "discount_percentage",
    "Selling_Price": "selling_price",
    "Total_Bill": "total_bill",
    "Payment_Method": "payment_method",
    "Promotion_Applied": "promotion_applied",
    "Promotion_Type": "promotion_type",
    "Shelf_Life_Days": "shelf_life_days",
    "Storage_Type": "storage_type",
    "Perishability": "perishability",
    "Store_ID": "store_id",
    "Units_Produced": "units_produced",
    "Units_Sold": "units_sold",
    "Unsold_Units": "unsold_units",
    "Stock_Available": "stock_available",
    "Waste_Pct": "waste_percentage",
    "Profit": "profit",
    "Customer_Rating": "customer_rating",
}

BOOLEAN_COLUMNS = {"Loyalty_Member", "Weekend", "Promotion_Applied"}


def normalize_boolean(value: str) -> str:
    """Convert Yes/No values to PostgreSQL-compatible true/false text."""
    normalized = value.strip().lower()
    if normalized == "yes":
        return "true"
    if normalized == "no":
        return "false"
    raise ValueError(f"Unexpected boolean value: {value!r}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare the bakery sales dataset for PostgreSQL CSV import."
    )
    parser.add_argument("source", type=Path, help="Path to the original CSV file")
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        help="Destination for the prepared CSV file",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    with args.source.open(newline="", encoding="utf-8-sig") as source_file:
        reader = csv.DictReader(source_file)
        if reader.fieldnames != list(HEADER_MAP):
            raise ValueError("The source CSV columns do not match the expected schema.")

        with args.output.open("w", newline="", encoding="utf-8") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=list(HEADER_MAP.values()))
            writer.writeheader()

            row_count = 0
            for source_row in reader:
                prepared_row = {}
                for source_name, output_name in HEADER_MAP.items():
                    value = source_row[source_name].strip()
                    if source_name in BOOLEAN_COLUMNS:
                        value = normalize_boolean(value)
                    prepared_row[output_name] = value

                writer.writerow(prepared_row)
                row_count += 1

    print(f"Prepared {row_count:,} rows at {args.output.resolve()}")


if __name__ == "__main__":
    main()
