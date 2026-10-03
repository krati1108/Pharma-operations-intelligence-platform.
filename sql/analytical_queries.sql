-- Portfolio query library for ad hoc analysis.
-- The dashboard uses the versioned views in schema.sql; these queries demonstrate
-- deeper CTE, join, aggregation, CASE, and window-function patterns.

-- 1) Rank product/warehouse positions by stockout urgency.
WITH risk_rank AS (
    SELECT
        product_name,
        therapeutic_area,
        warehouse_name,
        inventory_quantity,
        weeks_of_supply,
        stockout_risk,
        recommended_order_quantity,
        ROW_NUMBER() OVER (
            PARTITION BY warehouse_id
            ORDER BY
                CASE stockout_risk
                    WHEN 'Critical' THEN 1
                    WHEN 'High' THEN 2
                    WHEN 'Watch' THEN 3
                    ELSE 4
                END,
                weeks_of_supply
        ) AS warehouse_risk_rank
    FROM v_inventory_health
)
SELECT *
FROM risk_rank
WHERE warehouse_risk_rank <= 10
ORDER BY warehouse_name, warehouse_risk_rank;

-- 2) Compute weekly demand trend and four-week moving average by therapeutic area.
WITH therapy_week AS (
    SELECT
        ws.week_start,
        p.therapeutic_area,
        SUM(ws.demand_units) AS weekly_demand
    FROM weekly_sales ws
    JOIN products p ON p.product_id = ws.product_id
    GROUP BY ws.week_start, p.therapeutic_area
)
SELECT
    week_start,
    therapeutic_area,
    weekly_demand,
    ROUND(AVG(weekly_demand) OVER (
        PARTITION BY therapeutic_area
        ORDER BY week_start
        ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
    ), 1) AS moving_average_4_week,
    ROUND(100.0 * (weekly_demand - LAG(weekly_demand, 52) OVER (
        PARTITION BY therapeutic_area ORDER BY week_start
    )) / NULLIF(LAG(weekly_demand, 52) OVER (
        PARTITION BY therapeutic_area ORDER BY week_start
    ), 0), 1) AS year_over_year_pct
FROM therapy_week
ORDER BY week_start, therapeutic_area;

-- 3) FEFO batch action list with cumulative warehouse/product inventory.
SELECT
    e.warehouse_name,
    e.product_name,
    e.batch_number,
    e.expiry_date,
    e.days_to_expiry,
    e.inventory_quantity,
    e.inventory_value_at_risk,
    SUM(e.inventory_quantity) OVER (
        PARTITION BY e.warehouse_id, e.product_id
        ORDER BY e.expiry_date
    ) AS cumulative_units_by_fefo,
    CASE
        WHEN e.days_to_expiry < 0 THEN 'Quarantine and disposition'
        WHEN e.days_to_expiry <= 90 THEN 'Transfer, return, or prioritize allocation'
        WHEN e.days_to_expiry <= 180 THEN 'Monitor weekly'
        ELSE 'No immediate action'
    END AS recommended_action
FROM v_expiry_risk e
ORDER BY e.days_to_expiry, e.inventory_value_at_risk DESC;

-- 4) Supplier scorecard with quartile ranking.
WITH scored AS (
    SELECT
        supplier_id,
        supplier_name,
        delivered_orders,
        on_time_delivery_pct,
        acceptance_quality_pct,
        fill_rate_pct,
        ROUND(
            0.45 * on_time_delivery_pct
            + 0.30 * acceptance_quality_pct
            + 0.25 * fill_rate_pct,
            1
        ) AS composite_score
    FROM v_supplier_performance
)
SELECT
    *,
    DENSE_RANK() OVER (ORDER BY composite_score DESC) AS supplier_rank,
    NTILE(4) OVER (ORDER BY composite_score DESC) AS performance_quartile
FROM scored
ORDER BY supplier_rank;

-- 5) Service level and lost revenue opportunity by product.
SELECT
    p.product_id,
    p.product_name,
    p.therapeutic_area,
    SUM(ws.demand_units) AS demand_units,
    SUM(ws.units_sold) AS units_sold,
    SUM(ws.lost_sales_units) AS lost_sales_units,
    ROUND(100.0 * SUM(ws.units_sold) / NULLIF(SUM(ws.demand_units), 0), 2) AS service_level_pct,
    ROUND(SUM(ws.lost_sales_units * p.unit_price), 2) AS simulated_lost_revenue_opportunity
FROM weekly_sales ws
JOIN products p ON p.product_id = ws.product_id
GROUP BY p.product_id, p.product_name, p.therapeutic_area
ORDER BY simulated_lost_revenue_opportunity DESC;

-- 6) Open purchase-order exposure by warehouse and supplier.
SELECT
    w.warehouse_name,
    s.supplier_name,
    COUNT(*) AS open_po_count,
    SUM(po.ordered_quantity) AS open_units,
    ROUND(SUM(po.ordered_quantity * po.unit_cost), 2) AS open_po_value,
    SUM(CASE WHEN po.promised_delivery_date < c.as_of_date THEN 1 ELSE 0 END)
        AS past_due_orders
FROM purchase_orders po
JOIN warehouses w ON w.warehouse_id = po.warehouse_id
JOIN suppliers s ON s.supplier_id = po.supplier_id
CROSS JOIN simulation_config c
WHERE po.status = 'Open'
GROUP BY w.warehouse_name, s.supplier_name
ORDER BY open_po_value DESC;
