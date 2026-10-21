-- Order-to-trade and cancel-to-fill behaviour per unit.
-- fast_cancel_share: share of cancelled orders that lived under 2 seconds.
-- cancel_fill_size_ratio: average size of cancelled orders over average size of filled orders
-- (0 when either side is missing). Spoofers cancel big orders and fill small ones.
CREATE OR REPLACE TABLE feat_order_cancel AS
WITH o AS (
    SELECT client_id, symbol, CAST(timestamp AS DATE) AS trade_date, status, quantity, filled_quantity,
           date_diff('millisecond', timestamp, end_time) / 1000.0 AS life_s
    FROM orders
)
SELECT client_id, symbol, trade_date,
       COUNT(*) FILTER (WHERE status = 'CANCELLED') AS n_cancelled,
       COUNT(*) FILTER (WHERE status = 'CANCELLED') / (COUNT(*) FILTER (WHERE filled_quantity > 0) + 1.0)
           AS cancel_to_fill_ratio,
       COUNT(*) / GREATEST(COUNT(*) FILTER (WHERE filled_quantity > 0), 1) AS order_to_trade_ratio,
       COALESCE(COUNT(*) FILTER (WHERE status = 'CANCELLED' AND life_s < 2.0)
                / NULLIF(COUNT(*) FILTER (WHERE status = 'CANCELLED'), 0), 0) AS fast_cancel_share,
       COALESCE(AVG(quantity) FILTER (WHERE status = 'CANCELLED')
                / AVG(quantity) FILTER (WHERE filled_quantity > 0), 0) AS cancel_fill_size_ratio,
       COALESCE(SUM(quantity) FILTER (WHERE status = 'CANCELLED') / SUM(quantity), 0) AS cancelled_qty_share,
       MEDIAN(life_s) FILTER (WHERE status = 'CANCELLED') AS median_cancel_life_s
FROM o
GROUP BY ALL;
