PRAGMA foreign_keys = ON;

DROP VIEW IF EXISTS v_executive_kpis;
DROP VIEW IF EXISTS v_supplier_performance;
DROP VIEW IF EXISTS v_expiry_risk;
DROP VIEW IF EXISTS v_inventory_health;
DROP TABLE IF EXISTS purchase_orders;
DROP TABLE IF EXISTS inventory_batches;
DROP TABLE IF EXISTS weekly_sales;
DROP TABLE IF EXISTS warehouses;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS suppliers;
DROP TABLE IF EXISTS simulation_config;

CREATE TABLE simulation_config (
    config_id INTEGER PRIMARY KEY CHECK (config_id = 1),
    as_of_date TEXT NOT NULL
);

INSERT INTO simulation_config (config_id, as_of_date) VALUES (1, '2026-09-27');

CREATE TABLE suppliers (
    supplier_id TEXT PRIMARY KEY,
    supplier_name TEXT NOT NULL UNIQUE,
    country TEXT NOT NULL,
    contracted_lead_time_days INTEGER NOT NULL CHECK (contracted_lead_time_days > 0)
);

CREATE TABLE products (
    product_id TEXT PRIMARY KEY,
    product_name TEXT NOT NULL UNIQUE,
    therapeutic_area TEXT NOT NULL,
    dosage_form TEXT NOT NULL,
    strength TEXT NOT NULL,
    primary_supplier_id TEXT NOT NULL,
    unit_cost REAL NOT NULL CHECK (unit_cost > 0),
    unit_price REAL NOT NULL CHECK (unit_price >= unit_cost),
    lead_time_days INTEGER NOT NULL CHECK (lead_time_days > 0),
    FOREIGN KEY (primary_supplier_id) REFERENCES suppliers(supplier_id)
);

CREATE TABLE warehouses (
    warehouse_id TEXT PRIMARY KEY,
    warehouse_name TEXT NOT NULL UNIQUE,
    city TEXT NOT NULL,
    region TEXT NOT NULL
);

CREATE TABLE weekly_sales (
    sales_id INTEGER PRIMARY KEY,
    week_start TEXT NOT NULL,
    product_id TEXT NOT NULL,
    warehouse_id TEXT NOT NULL,
    demand_units INTEGER NOT NULL CHECK (demand_units >= 0),
    units_sold INTEGER NOT NULL CHECK (units_sold >= 0 AND units_sold <= demand_units),
    lost_sales_units INTEGER NOT NULL CHECK (lost_sales_units >= 0),
    revenue REAL NOT NULL CHECK (revenue >= 0),
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id),
    CHECK (lost_sales_units = demand_units - units_sold),
    UNIQUE (week_start, product_id, warehouse_id)
);

CREATE TABLE inventory_batches (
    batch_id TEXT PRIMARY KEY,
    batch_number TEXT NOT NULL,
    product_id TEXT NOT NULL,
    warehouse_id TEXT NOT NULL,
    manufacture_date TEXT NOT NULL,
    expiry_date TEXT NOT NULL,
    inventory_quantity INTEGER NOT NULL CHECK (inventory_quantity >= 0),
    reorder_point INTEGER NOT NULL CHECK (reorder_point >= 0),
    safety_stock INTEGER NOT NULL CHECK (safety_stock >= 0),
    last_count_date TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id),
    CHECK (expiry_date > manufacture_date),
    UNIQUE (batch_number, warehouse_id)
);

CREATE TABLE purchase_orders (
    purchase_order_id TEXT PRIMARY KEY,
    supplier_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    warehouse_id TEXT NOT NULL,
    order_date TEXT NOT NULL,
    promised_delivery_date TEXT NOT NULL,
    actual_delivery_date TEXT,
    ordered_quantity INTEGER NOT NULL CHECK (ordered_quantity > 0),
    received_quantity INTEGER NOT NULL CHECK (received_quantity >= 0),
    accepted_quantity INTEGER NOT NULL CHECK (accepted_quantity >= 0),
    unit_cost REAL NOT NULL CHECK (unit_cost > 0),
    status TEXT NOT NULL CHECK (status IN ('Delivered', 'Open', 'Cancelled')),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id),
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id),
    CHECK (promised_delivery_date >= order_date),
    CHECK (actual_delivery_date IS NULL OR actual_delivery_date >= order_date),
    CHECK (
        (status = 'Delivered' AND actual_delivery_date IS NOT NULL)
        OR (status IN ('Open', 'Cancelled') AND actual_delivery_date IS NULL)
    ),
    CHECK (received_quantity <= ordered_quantity),
    CHECK (accepted_quantity <= received_quantity)
);

CREATE INDEX idx_sales_product_week ON weekly_sales(product_id, week_start);
CREATE INDEX idx_sales_warehouse_week ON weekly_sales(warehouse_id, week_start);
CREATE INDEX idx_batches_expiry ON inventory_batches(expiry_date);
CREATE INDEX idx_batches_product_warehouse ON inventory_batches(product_id, warehouse_id);
CREATE INDEX idx_po_supplier_status ON purchase_orders(supplier_id, status);

CREATE VIEW v_inventory_health AS
WITH latest_week AS (
    SELECT MAX(week_start) AS max_week FROM weekly_sales
),
recent_demand AS (
    SELECT
        product_id,
        warehouse_id,
        AVG(demand_units) AS avg_weekly_demand,
        SUM(demand_units) AS demand_last_12_weeks
    FROM weekly_sales, latest_week
    WHERE week_start > date(max_week, '-84 days')
    GROUP BY product_id, warehouse_id
),
stock AS (
    SELECT
        b.product_id,
        b.warehouse_id,
        SUM(CASE WHEN b.expiry_date >= c.as_of_date THEN b.inventory_quantity ELSE 0 END)
            AS inventory_quantity,
        SUM(CASE WHEN b.expiry_date < c.as_of_date THEN b.inventory_quantity ELSE 0 END)
            AS expired_inventory_quantity,
        MAX(b.reorder_point) AS reorder_point,
        MAX(b.safety_stock) AS safety_stock
    FROM inventory_batches b
    CROSS JOIN simulation_config c
    GROUP BY b.product_id, b.warehouse_id
),
open_orders AS (
    SELECT
        product_id,
        warehouse_id,
        SUM(ordered_quantity - received_quantity) AS on_order_quantity
    FROM purchase_orders
    WHERE status = 'Open'
    GROUP BY product_id, warehouse_id
)
SELECT
    p.product_id,
    p.product_name,
    p.therapeutic_area,
    w.warehouse_id,
    w.warehouse_name,
    w.region,
    s.inventory_quantity,
    s.expired_inventory_quantity,
    COALESCE(o.on_order_quantity, 0) AS on_order_quantity,
    s.inventory_quantity + COALESCE(o.on_order_quantity, 0) AS inventory_position,
    s.reorder_point,
    s.safety_stock,
    ROUND(COALESCE(d.avg_weekly_demand, 0), 2) AS avg_weekly_demand,
    CASE
        WHEN COALESCE(d.avg_weekly_demand, 0) = 0 THEN NULL
        ELSE ROUND(s.inventory_quantity / d.avg_weekly_demand, 2)
    END AS weeks_of_supply,
    CASE
        WHEN s.inventory_quantity <= s.safety_stock THEN 'Critical'
        WHEN s.inventory_quantity <= s.reorder_point THEN 'High'
        WHEN COALESCE(d.avg_weekly_demand, 0) > 0
             AND s.inventory_quantity / d.avg_weekly_demand < 6 THEN 'Watch'
        ELSE 'Healthy'
    END AS stockout_risk,
    CASE
        WHEN s.inventory_quantity + COALESCE(o.on_order_quantity, 0) <= s.reorder_point THEN 1
        ELSE 0
    END AS replenishment_flag,
    MAX(
        0,
        CAST(ROUND(
            (COALESCE(d.avg_weekly_demand, 0) * (p.lead_time_days / 7.0 + 4))
            + s.safety_stock - s.inventory_quantity - COALESCE(o.on_order_quantity, 0)
        ) AS INTEGER)
    ) AS recommended_order_quantity,
    ROUND(s.inventory_quantity * p.unit_cost, 2) AS inventory_value,
    p.unit_cost,
    p.unit_price,
    p.lead_time_days
FROM stock s
JOIN products p ON p.product_id = s.product_id
JOIN warehouses w ON w.warehouse_id = s.warehouse_id
LEFT JOIN recent_demand d
    ON d.product_id = s.product_id AND d.warehouse_id = s.warehouse_id
LEFT JOIN open_orders o
    ON o.product_id = s.product_id AND o.warehouse_id = s.warehouse_id;

CREATE VIEW v_expiry_risk AS
SELECT
    b.batch_id,
    b.batch_number,
    b.product_id,
    p.product_name,
    p.therapeutic_area,
    b.warehouse_id,
    w.warehouse_name,
    b.manufacture_date,
    b.expiry_date,
    CAST(julianday(c.as_of_date) - julianday(b.manufacture_date) AS INTEGER) AS age_days,
    CAST(julianday(b.expiry_date) - julianday(c.as_of_date) AS INTEGER) AS days_to_expiry,
    b.inventory_quantity,
    p.unit_cost,
    ROUND(b.inventory_quantity * p.unit_cost, 2) AS inventory_value_at_risk,
    CASE
        WHEN b.expiry_date < c.as_of_date THEN 'Expired'
        WHEN b.expiry_date <= date(c.as_of_date, '+90 days') THEN '0-90 days'
        WHEN b.expiry_date <= date(c.as_of_date, '+180 days') THEN '91-180 days'
        WHEN b.expiry_date <= date(c.as_of_date, '+365 days') THEN '181-365 days'
        ELSE 'Over 365 days'
    END AS expiry_bucket
FROM inventory_batches b
JOIN products p ON p.product_id = b.product_id
JOIN warehouses w ON w.warehouse_id = b.warehouse_id
CROSS JOIN simulation_config c;

CREATE VIEW v_supplier_performance AS
SELECT
    s.supplier_id,
    s.supplier_name,
    s.country,
    s.contracted_lead_time_days,
    COUNT(CASE WHEN po.status = 'Delivered' THEN 1 END) AS delivered_orders,
    ROUND(100.0 * AVG(
        CASE WHEN po.status = 'Delivered'
             THEN CASE WHEN po.actual_delivery_date <= po.promised_delivery_date THEN 1.0 ELSE 0.0 END
        END
    ), 1) AS on_time_delivery_pct,
    ROUND(100.0 * SUM(CASE WHEN po.status = 'Delivered' THEN po.accepted_quantity ELSE 0 END)
        / NULLIF(SUM(CASE WHEN po.status = 'Delivered' THEN po.received_quantity ELSE 0 END), 0), 1
    ) AS acceptance_quality_pct,
    ROUND(100.0 * SUM(CASE WHEN po.status = 'Delivered' THEN po.received_quantity ELSE 0 END)
        / NULLIF(SUM(CASE WHEN po.status = 'Delivered' THEN po.ordered_quantity ELSE 0 END), 0), 1
    ) AS fill_rate_pct,
    ROUND(AVG(
        CASE WHEN po.status = 'Delivered'
             THEN julianday(po.actual_delivery_date) - julianday(po.order_date)
        END
    ), 1) AS actual_lead_time_days,
    ROUND(SUM(po.ordered_quantity * po.unit_cost), 2) AS total_po_value
FROM suppliers s
LEFT JOIN purchase_orders po ON po.supplier_id = s.supplier_id
GROUP BY s.supplier_id, s.supplier_name, s.country, s.contracted_lead_time_days;

CREATE VIEW v_executive_kpis AS
SELECT
    (SELECT ROUND(SUM(revenue), 2) FROM weekly_sales) AS total_revenue,
    (SELECT SUM(units_sold) FROM weekly_sales) AS units_sold,
    (SELECT ROUND(SUM(inventory_value), 2) FROM v_inventory_health) AS inventory_value,
    (SELECT COUNT(*) FROM v_inventory_health WHERE stockout_risk = 'Critical') AS critical_stockout_skus,
    (SELECT ROUND(SUM(inventory_quantity) / NULLIF(SUM(avg_weekly_demand), 0), 2)
        FROM v_inventory_health) AS network_weeks_of_supply,
    (SELECT COUNT(*) FROM v_inventory_health WHERE replenishment_flag = 1) AS replenishment_flags,
    (SELECT SUM(inventory_quantity) FROM v_expiry_risk WHERE expiry_bucket IN ('Expired', '0-90 days'))
        AS units_expiring_90_days,
    (SELECT SUM(inventory_quantity) FROM v_expiry_risk
        WHERE expiry_bucket IN ('Expired', '0-90 days', '91-180 days')) AS units_expiring_180_days,
    (SELECT ROUND(SUM(inventory_value_at_risk), 2) FROM v_expiry_risk
        WHERE expiry_bucket IN ('Expired', '0-90 days', '91-180 days')) AS expiry_value_at_risk_180_days,
    (SELECT ROUND(AVG(on_time_delivery_pct), 1) FROM v_supplier_performance) AS supplier_on_time_delivery_pct,
    (SELECT ROUND(AVG(acceptance_quality_pct), 1) FROM v_supplier_performance) AS supplier_acceptance_quality_pct;
