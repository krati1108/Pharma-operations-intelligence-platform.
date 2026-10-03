"""Generate realistic synthetic pharma operations data and load SQLite.

The generator is deterministic by default. It models two years of weekly demand,
multi-batch warehouse inventory, and purchase-order outcomes with supplier-specific
reliability and quality profiles.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import DATABASE_PATH, RANDOM_SEED, RAW_DATA_DIR, SIMULATION_DATE
from .database import create_schema, load_frames, table_counts

SUPPLIER_SPECS = [
    ("SUP-001", "Apex Active Ingredients", "United States", 28, 0.94, 0.985),
    ("SUP-002", "Helix Pharma Materials", "Germany", 35, 0.91, 0.978),
    ("SUP-003", "NovaMed Generics", "India", 42, 0.84, 0.964),
    ("SUP-004", "Sterling Biologics", "Switzerland", 49, 0.89, 0.991),
    ("SUP-005", "VitaCore Laboratories", "Ireland", 32, 0.87, 0.973),
    ("SUP-006", "Pacific Therapeutics", "Singapore", 45, 0.81, 0.957),
    ("SUP-007", "NorthStar Injectables", "Canada", 30, 0.93, 0.987),
    ("SUP-008", "Orion Healthcare Supply", "United Kingdom", 38, 0.86, 0.969),
]

PRODUCT_SPECS = [
    ("P001", "Cardiostat 10 mg", "Cardiology", "Tablet", "10 mg", "SUP-001", 3.10, 12.50, 28, 115),
    ("P002", "Cardiostat 20 mg", "Cardiology", "Tablet", "20 mg", "SUP-001", 4.00, 15.75, 28, 90),
    ("P003", "ThromboClear 75 mg", "Cardiology", "Tablet", "75 mg", "SUP-002", 6.80, 24.00, 35, 70),
    ("P004", "GlucoBalance 500 mg", "Endocrinology", "Tablet", "500 mg", "SUP-003", 1.85, 8.50, 42, 145),
    ("P005", "GlucoBalance XR", "Endocrinology", "Tablet", "750 mg", "SUP-003", 2.70, 11.25, 42, 105),
    ("P006", "InsuSure Basal", "Endocrinology", "Injection", "100 U/mL", "SUP-004", 31.50, 68.00, 49, 58),
    ("P007", "RespiraFlow", "Respiratory", "Inhaler", "90 mcg", "SUP-005", 12.40, 38.00, 32, 80),
    ("P008", "AirGuard Duo", "Respiratory", "Inhaler", "250/50 mcg", "SUP-005", 18.90, 56.00, 32, 62),
    ("P009", "Cefraxin 500 mg", "Anti-infective", "Capsule", "500 mg", "SUP-006", 4.60, 17.50, 45, 86),
    ("P010", "Azimune 250 mg", "Anti-infective", "Tablet", "250 mg", "SUP-006", 3.90, 15.00, 45, 74),
    ("P011", "VancoSafe IV", "Anti-infective", "Injection", "1 g", "SUP-007", 17.50, 49.00, 30, 44),
    ("P012", "NeuroCalm 50 mg", "Neurology", "Capsule", "50 mg", "SUP-002", 5.20, 21.00, 35, 76),
    ("P013", "MigraLess ODT", "Neurology", "ODT", "10 mg", "SUP-008", 7.10, 27.50, 38, 55),
    ("P014", "OncoRelief", "Oncology", "Tablet", "100 mg", "SUP-004", 82.00, 185.00, 49, 22),
    ("P015", "Immunexa", "Oncology", "Injection", "40 mg/0.8 mL", "SUP-004", 128.00, 295.00, 49, 14),
    ("P016", "ArthriEase 200 mg", "Pain Management", "Tablet", "200 mg", "SUP-003", 2.30, 10.50, 42, 128),
    ("P017", "PainFree ER", "Pain Management", "Tablet", "650 mg", "SUP-008", 3.15, 13.00, 38, 110),
    ("P018", "Dermaclear Cream", "Dermatology", "Cream", "1%", "SUP-005", 5.80, 19.50, 32, 64),
    ("P019", "RenalPro 800 mg", "Nephrology", "Tablet", "800 mg", "SUP-001", 8.70, 29.00, 28, 47),
    ("P020", "GastroShield 40 mg", "Gastroenterology", "Capsule", "40 mg", "SUP-003", 2.10, 9.75, 42, 132),
    ("P021", "HematoPlus", "Hematology", "Injection", "200 mg/mL", "SUP-007", 24.00, 61.00, 30, 35),
    ("P022", "Allerban 10 mg", "Allergy", "Tablet", "10 mg", "SUP-008", 1.20, 7.25, 38, 118),
    ("P023", "PediaLyte Rx", "Pediatrics", "Solution", "250 mL", "SUP-006", 3.60, 14.00, 45, 69),
    ("P024", "OsteoBuild D3", "Bone Health", "Capsule", "2000 IU", "SUP-002", 2.80, 12.00, 35, 95),
]

WAREHOUSE_SPECS = [
    ("WH-NE", "Northeast Distribution Center", "Allentown", "Northeast", 1.12),
    ("WH-SE", "Southeast Distribution Center", "Atlanta", "Southeast", 0.98),
    ("WH-MW", "Midwest Distribution Center", "Indianapolis", "Midwest", 1.00),
    ("WH-W", "West Distribution Center", "Reno", "West", 0.90),
]


def _as_iso(series: pd.Series) -> pd.Series:
    """Convert datetimes to SQLite-friendly ISO dates."""
    return pd.to_datetime(series).dt.strftime("%Y-%m-%d")


def _build_dimension_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    suppliers = pd.DataFrame(
        [row[:4] for row in SUPPLIER_SPECS],
        columns=[
            "supplier_id",
            "supplier_name",
            "country",
            "contracted_lead_time_days",
        ],
    )
    products = pd.DataFrame(
        [row[:9] for row in PRODUCT_SPECS],
        columns=[
            "product_id",
            "product_name",
            "therapeutic_area",
            "dosage_form",
            "strength",
            "primary_supplier_id",
            "unit_cost",
            "unit_price",
            "lead_time_days",
        ],
    )
    warehouses = pd.DataFrame(
        [row[:4] for row in WAREHOUSE_SPECS],
        columns=["warehouse_id", "warehouse_name", "city", "region"],
    )
    return suppliers, products, warehouses


def _generate_weekly_sales(
    products: pd.DataFrame,
    warehouses: pd.DataFrame,
    rng: np.random.Generator,
    as_of_date: pd.Timestamp,
) -> pd.DataFrame:
    """Simulate two years of weekly demand, fulfilled sales, and lost sales."""
    weeks = pd.date_range(end=as_of_date - pd.Timedelta(days=6), periods=104, freq="W-MON")
    warehouse_factors = {row[0]: row[4] for row in WAREHOUSE_SPECS}
    base_demand = {row[0]: row[9] for row in PRODUCT_SPECS}
    records: list[dict[str, Any]] = []
    sales_id = 1

    for product_index, product in products.iterrows():
        phase = float(rng.uniform(0, 2 * np.pi))
        annual_strength = 0.10 if product["therapeutic_area"] != "Respiratory" else 0.24
        for warehouse in warehouses.itertuples(index=False):
            local_factor = warehouse_factors[warehouse.warehouse_id] * rng.uniform(0.94, 1.06)
            for week_index, week in enumerate(weeks):
                annual = 1 + annual_strength * np.sin(2 * np.pi * week_index / 52 + phase)
                respiratory_winter = 1.0
                if product["therapeutic_area"] in {"Respiratory", "Anti-infective", "Allergy"}:
                    respiratory_winter += 0.15 * np.cos(2 * np.pi * week_index / 52)
                trend = 1 + (0.0011 + product_index * 0.000015) * week_index
                promotion = 1.13 if week_index in {34, 35, 81, 82} else 1.0
                expected = base_demand[product["product_id"]] * local_factor * annual * respiratory_winter * trend * promotion
                demand = max(0, round(rng.normal(expected, max(2.5, expected * 0.09))))

                # A small, controlled set of service failures creates observable lost demand.
                fill_rate = rng.uniform(0.83, 0.96) if rng.random() < 0.065 else rng.uniform(0.975, 1.0)
                units_sold = min(demand, round(demand * fill_rate))
                records.append(
                    {
                        "sales_id": sales_id,
                        "week_start": week.strftime("%Y-%m-%d"),
                        "product_id": product["product_id"],
                        "warehouse_id": warehouse.warehouse_id,
                        "demand_units": demand,
                        "units_sold": units_sold,
                        "lost_sales_units": demand - units_sold,
                        "revenue": round(units_sold * float(product["unit_price"]), 2),
                    }
                )
                sales_id += 1
    return pd.DataFrame(records)


def _generate_inventory(
    products: pd.DataFrame,
    warehouses: pd.DataFrame,
    weekly_sales: pd.DataFrame,
    rng: np.random.Generator,
    as_of_date: pd.Timestamp,
) -> pd.DataFrame:
    """Create two FEFO-managed batches for each product/warehouse position."""
    recent = (
        weekly_sales.sort_values("week_start")
        .groupby(["product_id", "warehouse_id"], as_index=False)
        .tail(12)
        .groupby(["product_id", "warehouse_id"], as_index=False)["demand_units"]
        .mean()
        .rename(columns={"demand_units": "avg_weekly_demand"})
    )
    demand_lookup = recent.set_index(["product_id", "warehouse_id"])["avg_weekly_demand"]
    records: list[dict[str, Any]] = []
    position_index = 0

    for product in products.itertuples(index=False):
        for warehouse in warehouses.itertuples(index=False):
            avg_demand = float(demand_lookup.loc[(product.product_id, warehouse.warehouse_id)])
            lead_weeks = product.lead_time_days / 7
            safety_stock = max(5, round(avg_demand * (0.65 + rng.uniform(0.05, 0.45))))
            reorder_point = round(avg_demand * lead_weeks + safety_stock)

            # Cycle through deliberate coverage states to make the risk dashboard useful.
            coverage_factors = [0.12, 0.55, 1.00, 1.65, 2.50]
            factor = coverage_factors[position_index % len(coverage_factors)]
            total_inventory = max(0, round(reorder_point * factor * rng.uniform(0.92, 1.08)))
            first_batch_qty = round(total_inventory * rng.uniform(0.35, 0.65))
            quantities = [first_batch_qty, total_inventory - first_batch_qty]

            for batch_sequence, quantity in enumerate(quantities, start=1):
                manufactured_months_ago = int(rng.integers(4, 19))
                manufacture_date = as_of_date - pd.DateOffset(months=manufactured_months_ago)
                expiry_options = [-25, 40, 75, 125, 170, 260, 420, 610]
                # Roughly one quarter of positions have inventory inside the 180-day window.
                if (position_index + batch_sequence) % 7 == 0:
                    days_to_expiry = expiry_options[(position_index + batch_sequence) % 5]
                else:
                    days_to_expiry = int(rng.choice(expiry_options[3:]))
                expiry_date = as_of_date + pd.Timedelta(days=days_to_expiry)
                if expiry_date <= manufacture_date:
                    expiry_date = manufacture_date + pd.DateOffset(months=12)
                batch_number = (
                    f"{product.product_id}-{warehouse.warehouse_id.replace('WH-', '')}-"
                    f"{as_of_date.year - manufactured_months_ago // 12}{batch_sequence:02d}"
                )
                records.append(
                    {
                        "batch_id": f"BAT-{position_index + 1:03d}-{batch_sequence}",
                        "batch_number": batch_number,
                        "product_id": product.product_id,
                        "warehouse_id": warehouse.warehouse_id,
                        "manufacture_date": manufacture_date.strftime("%Y-%m-%d"),
                        "expiry_date": pd.Timestamp(expiry_date).strftime("%Y-%m-%d"),
                        "inventory_quantity": quantity,
                        "reorder_point": reorder_point,
                        "safety_stock": safety_stock,
                        "last_count_date": as_of_date.strftime("%Y-%m-%d"),
                    }
                )
            position_index += 1
    return pd.DataFrame(records)


def _generate_purchase_orders(
    products: pd.DataFrame,
    warehouses: pd.DataFrame,
    rng: np.random.Generator,
    as_of_date: pd.Timestamp,
) -> pd.DataFrame:
    """Simulate supplier delivery, fill-rate, and batch-acceptance outcomes."""
    supplier_profiles = {
        row[0]: {"lead_days": row[3], "on_time": row[4], "quality": row[5]}
        for row in SUPPLIER_SPECS
    }
    records: list[dict[str, Any]] = []
    products_by_supplier = {
        supplier_id: group for supplier_id, group in products.groupby("primary_supplier_id")
    }
    po_number = 1

    for supplier_id, supplier_products in products_by_supplier.items():
        profile = supplier_profiles[supplier_id]
        for _ in range(48):
            product = supplier_products.iloc[int(rng.integers(0, len(supplier_products)))]
            warehouse = warehouses.iloc[int(rng.integers(0, len(warehouses)))]
            days_ago = int(rng.integers(12, 500))
            order_date = as_of_date - pd.Timedelta(days=days_ago)
            promised = order_date + pd.Timedelta(days=int(profile["lead_days"]))
            is_open = order_date > as_of_date - pd.Timedelta(days=int(profile["lead_days"] * 0.65))
            is_cancelled = (not is_open) and rng.random() < 0.025
            ordered = int(rng.integers(150, 1200))

            if is_open:
                actual = pd.NaT
                received = 0
                accepted = 0
                status = "Open"
            elif is_cancelled:
                actual = pd.NaT
                received = 0
                accepted = 0
                status = "Cancelled"
            else:
                on_time = rng.random() < profile["on_time"]
                delivery_variance = int(rng.integers(-5, 1)) if on_time else int(rng.integers(1, 15))
                actual = promised + pd.Timedelta(days=delivery_variance)
                received = round(ordered * rng.uniform(0.94, 1.0))
                rejection_rate = float(np.clip(rng.normal(1 - profile["quality"], 0.009), 0, 0.09))
                accepted = round(received * (1 - rejection_rate))
                status = "Delivered"

            records.append(
                {
                    "purchase_order_id": f"PO-{po_number:05d}",
                    "supplier_id": supplier_id,
                    "product_id": product["product_id"],
                    "warehouse_id": warehouse["warehouse_id"],
                    "order_date": order_date.strftime("%Y-%m-%d"),
                    "promised_delivery_date": promised.strftime("%Y-%m-%d"),
                    "actual_delivery_date": None if pd.isna(actual) else actual.strftime("%Y-%m-%d"),
                    "ordered_quantity": ordered,
                    "received_quantity": received,
                    "accepted_quantity": accepted,
                    "unit_cost": round(float(product["unit_cost"]) * rng.uniform(0.97, 1.04), 2),
                    "status": status,
                }
            )
            po_number += 1
    return pd.DataFrame(records)


def validate_frames(frames: dict[str, pd.DataFrame]) -> None:
    """Fail fast on primary-key, referential, date, and quantity defects."""
    key_columns = {
        "suppliers": "supplier_id",
        "products": "product_id",
        "warehouses": "warehouse_id",
        "weekly_sales": "sales_id",
        "inventory_batches": "batch_id",
        "purchase_orders": "purchase_order_id",
    }
    for table, key in key_columns.items():
        frame = frames[table]
        if frame.empty:
            raise ValueError(f"{table} is empty")
        if frame[key].isna().any() or frame[key].duplicated().any():
            raise ValueError(f"Invalid primary key in {table}.{key}")

    if not set(frames["products"]["primary_supplier_id"]).issubset(
        set(frames["suppliers"]["supplier_id"])
    ):
        raise ValueError("Products contain unknown suppliers")
    if (frames["weekly_sales"]["units_sold"] > frames["weekly_sales"]["demand_units"]).any():
        raise ValueError("Units sold cannot exceed demand")
    if not (
        frames["weekly_sales"]["lost_sales_units"]
        == frames["weekly_sales"]["demand_units"] - frames["weekly_sales"]["units_sold"]
    ).all():
        raise ValueError("Lost sales must equal demand minus fulfilled units")
    if (frames["purchase_orders"]["accepted_quantity"] > frames["purchase_orders"]["received_quantity"]).any():
        raise ValueError("Accepted quantity cannot exceed received quantity")
    delivered = frames["purchase_orders"]["status"].eq("Delivered")
    has_actual_date = frames["purchase_orders"]["actual_delivery_date"].notna()
    if not delivered.equals(has_actual_date):
        raise ValueError("Only delivered purchase orders may have an actual delivery date")
    if (
        pd.to_datetime(frames["inventory_batches"]["expiry_date"])
        <= pd.to_datetime(frames["inventory_batches"]["manufacture_date"])
    ).any():
        raise ValueError("Expiry date must follow manufacture date")


def generate_synthetic_data(
    output_dir: Path | str = RAW_DATA_DIR,
    seed: int = RANDOM_SEED,
    as_of_date: str | pd.Timestamp = SIMULATION_DATE,
    write_csv: bool = True,
) -> dict[str, pd.DataFrame]:
    """Build normalized, reproducible data frames and optionally persist CSVs."""
    as_of = pd.Timestamp(as_of_date).normalize()
    rng = np.random.default_rng(seed)
    suppliers, products, warehouses = _build_dimension_frames()
    weekly_sales = _generate_weekly_sales(products, warehouses, rng, as_of)
    inventory_batches = _generate_inventory(products, warehouses, weekly_sales, rng, as_of)
    purchase_orders = _generate_purchase_orders(products, warehouses, rng, as_of)

    frames = {
        "suppliers": suppliers,
        "products": products,
        "warehouses": warehouses,
        "weekly_sales": weekly_sales,
        "inventory_batches": inventory_batches,
        "purchase_orders": purchase_orders,
    }
    validate_frames(frames)

    if write_csv:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        for name, frame in frames.items():
            frame.to_csv(output_path / f"{name}.csv", index=False)
    return frames


def run_pipeline(
    output_dir: Path | str = RAW_DATA_DIR,
    database_path: Path | str = DATABASE_PATH,
    seed: int = RANDOM_SEED,
    as_of_date: str | pd.Timestamp = SIMULATION_DATE,
) -> dict[str, int]:
    """Run generation, validation, schema creation, and transactional loading."""
    frames = generate_synthetic_data(output_dir, seed, as_of_date, write_csv=True)
    create_schema(database_path, as_of_date=as_of_date)
    load_frames(frames, database_path)
    return table_counts(database_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the pharmaceutical analytics database")
    parser.add_argument("--database", type=Path, default=DATABASE_PATH)
    parser.add_argument("--output-dir", type=Path, default=RAW_DATA_DIR)
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    args = parser.parse_args()
    counts = run_pipeline(args.output_dir, args.database, args.seed)
    print(f"ETL complete: {args.database}")
    for table, count in counts.items():
        print(f"  {table}: {count:,} rows")


if __name__ == "__main__":
    main()
