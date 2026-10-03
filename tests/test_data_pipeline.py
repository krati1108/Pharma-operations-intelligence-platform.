import sqlite3

from src.data_pipeline import generate_synthetic_data, run_pipeline
from src.database import query_dataframe


def test_synthetic_data_has_expected_grain_and_integrity(tmp_path) -> None:
    frames = generate_synthetic_data(tmp_path / "raw", write_csv=True)
    assert len(frames["products"]) == 24
    assert len(frames["warehouses"]) == 4
    assert len(frames["weekly_sales"]) == 24 * 4 * 104
    assert len(frames["inventory_batches"]) == 24 * 4 * 2
    assert frames["weekly_sales"]["lost_sales_units"].sum() > 0
    assert (tmp_path / "raw" / "purchase_orders.csv").exists()


def test_etl_builds_relational_database_and_analytical_views(tmp_path) -> None:
    database_path = tmp_path / "pharma_test.db"
    counts = run_pipeline(
        tmp_path / "raw",
        database_path,
        as_of_date="2027-01-15",
    )
    assert counts["weekly_sales"] == 24 * 4 * 104
    assert counts["purchase_orders"] > 300

    kpis = query_dataframe("SELECT * FROM v_executive_kpis", database_path=database_path)
    inventory = query_dataframe("SELECT * FROM v_inventory_health", database_path=database_path)
    suppliers = query_dataframe("SELECT * FROM v_supplier_performance", database_path=database_path)
    assert len(kpis) == 1
    assert kpis.loc[0, "total_revenue"] > 0
    assert len(inventory) == 24 * 4
    assert inventory["replenishment_flag"].sum() > 0
    assert inventory["on_order_quantity"].sum() > 0
    assert len(suppliers) == 8

    config = query_dataframe("SELECT as_of_date FROM simulation_config", database_path=database_path)
    stock_reconciliation = query_dataframe(
        """
        SELECT
            (SELECT SUM(inventory_quantity) FROM inventory_batches) AS batch_units,
            (SELECT SUM(inventory_quantity + expired_inventory_quantity)
                FROM v_inventory_health) AS reconciled_units,
            (SELECT SUM(ordered_quantity - received_quantity)
                FROM purchase_orders WHERE status = 'Open') AS open_po_units,
            (SELECT SUM(on_order_quantity) FROM v_inventory_health) AS view_on_order_units
        """,
        database_path=database_path,
    ).iloc[0]
    assert config.loc[0, "as_of_date"] == "2027-01-15"
    assert stock_reconciliation.batch_units == stock_reconciliation.reconciled_units
    assert stock_reconciliation.open_po_units == stock_reconciliation.view_on_order_units

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

