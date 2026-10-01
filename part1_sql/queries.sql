-- ============================================================
-- Part 1 - SQL Business Query Engine
-- Database: data/meesho_reseller.db (SQLite)
-- Tables:   resellers(reseller_id, reseller_name, city, region, join_date)
--           orders(order_id, reseller_id, category, product_name, quantity,
--                  unit_price, order_date, month, status)
-- Revenue everywhere = SUM(quantity * unit_price)
-- ============================================================


-- ------------------------------------------------------------
-- Q1. Monthly revenue by category
-- Output feeds Part 2 and Part 4: part1_sql/output/monthly_category_revenue.csv
-- Columns must be exactly: month, category, revenue, n_orders
-- Expected: 15 rows (3 months x 5 categories)
-- ------------------------------------------------------------
SELECT
    month,
    category,
    ROUND(SUM(quantity * unit_price), 2) AS revenue,
    COUNT(*)                             AS n_orders
FROM orders
GROUP BY month, category
ORDER BY
    CASE month
        WHEN 'April' THEN 1
        WHEN 'May'   THEN 2
        WHEN 'June'  THEN 3
    END,
    CASE category
        WHEN 'Ethnic Wear'            THEN 1
        WHEN 'Western Wear'           THEN 2
        WHEN 'Kids Wear'              THEN 3
        WHEN 'Home & Kitchen'         THEN 4
        WHEN 'Beauty & Personal Care' THEN 5
    END;


-- ------------------------------------------------------------
-- Q2. Region-wise total revenue and order count
-- JOIN orders to resellers on reseller_id, GROUP BY region.
-- Sorted by revenue descending (North, West, South, East).
-- The four region totals sum to the grand total 1262066.92 (900 orders).
-- ------------------------------------------------------------
SELECT
    r.region,
    ROUND(SUM(o.quantity * o.unit_price), 2) AS total_revenue,
    COUNT(*)                                 AS n_orders
FROM orders o
JOIN resellers r ON o.reseller_id = r.reseller_id
GROUP BY r.region
ORDER BY total_revenue DESC;


-- ------------------------------------------------------------
-- Q3. Top resellers by total spend
-- HAVING filters after GROUP BY, because the aggregated total
-- does not exist until grouping has happened (WHERE cannot do this).
-- ------------------------------------------------------------
SELECT
    r.reseller_id,
    r.reseller_name,
    ROUND(SUM(o.quantity * o.unit_price), 2) AS total_spend
FROM orders o
JOIN resellers r ON o.reseller_id = r.reseller_id
GROUP BY r.reseller_id, r.reseller_name
HAVING SUM(o.quantity * o.unit_price) > 50000
ORDER BY total_spend DESC
LIMIT 5;


-- ------------------------------------------------------------
-- Q4a. Resellers who have never placed an order
-- LEFT JOIN keeps every reseller, then COUNT(o.order_id) = 0
-- keeps only those with no matching order rows.
-- Expected: exactly one row - RS024, Ahmedabad Reseller 6, West
-- ------------------------------------------------------------
SELECT
    r.reseller_id,
    r.reseller_name,
    r.region
FROM resellers r
LEFT JOIN orders o ON r.reseller_id = o.reseller_id
GROUP BY r.reseller_id, r.reseller_name, r.region
HAVING COUNT(o.order_id) = 0;


-- ------------------------------------------------------------
-- Q4b. Diagnostic: COUNT(*) vs COUNT(order_id) for RS024
--
-- A LEFT JOIN keeps the reseller row even when there is no matching order.
-- For RS024 the join therefore produces ONE row whose order columns are all NULL.
--
-- COUNT(*) counts the resulting row, including that NULL-padded row, so it returns 1.
-- COUNT(order_id) counts only non-NULL order IDs, so it returns 0.
--
-- Therefore COUNT(*) is the WRONG way to test for a zero-match LEFT JOIN row
-- (it would report RS024 as having 1 order), and COUNT(order_id) is the
-- correct way to identify zero orders.
--
-- Expected: RS024 | count_star = 1 | count_order_id = 0
-- ------------------------------------------------------------
SELECT
    r.reseller_id,
    COUNT(*)          AS count_star,
    COUNT(o.order_id) AS count_order_id
FROM resellers r
LEFT JOIN orders o ON r.reseller_id = o.reseller_id
WHERE r.reseller_id = 'RS024'
GROUP BY r.reseller_id;


-- ------------------------------------------------------------
-- Q5. Average Order Value (AOV) - June, Delivered orders only
-- Both filters apply together. SUM / COUNT over the filtered set.
-- Expected: 1267.69 (from 218 delivered June orders)
-- ------------------------------------------------------------
SELECT
    ROUND(SUM(quantity * unit_price) / COUNT(*), 2) AS aov
FROM orders
WHERE month = 'June'
  AND status = 'Delivered';
