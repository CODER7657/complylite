-- Same-day round trips per unit. Every sell is paired with the latest earlier buy (and every
-- buy with the latest earlier sell) by the same client in the same symbol on the same day.
-- Wash trades show short round trips at almost the same price and the same quantity.
CREATE OR REPLACE TABLE feat_round_trip AS
WITH t AS (
    SELECT client_id, symbol, CAST(timestamp AS DATE) AS trade_date, side, quantity, price, timestamp
    FROM trades
),
b AS (SELECT * FROM t WHERE side = 'BUY'),
s AS (SELECT * FROM t WHERE side = 'SELL'),
legs AS (
    SELECT s.client_id, s.symbol, s.trade_date,
           date_diff('millisecond', b.timestamp, s.timestamp) / 1000.0 AS rt_s,
           ABS(s.price - b.price) / b.price * 1e4 AS rt_bps,
           LEAST(s.quantity, b.quantity) / GREATEST(s.quantity, b.quantity) AS qty_match
    FROM s ASOF JOIN b
      ON s.client_id = b.client_id AND s.symbol = b.symbol AND s.trade_date = b.trade_date
     AND s.timestamp >= b.timestamp
    UNION ALL
    SELECT b.client_id, b.symbol, b.trade_date,
           date_diff('millisecond', s.timestamp, b.timestamp) / 1000.0 AS rt_s,
           ABS(b.price - s.price) / s.price * 1e4 AS rt_bps,
           LEAST(s.quantity, b.quantity) / GREATEST(s.quantity, b.quantity) AS qty_match
    FROM b ASOF JOIN s
      ON b.client_id = s.client_id AND b.symbol = s.symbol AND b.trade_date = s.trade_date
     AND b.timestamp >= s.timestamp
),
agg AS (
    SELECT client_id, symbol, trade_date,
           COUNT(*) AS n_round_trips,
           MEDIAN(rt_s) AS median_rt_seconds,
           AVG(CASE WHEN rt_s <= 300 THEN 1.0 ELSE 0.0 END) AS share_rt_under_5m,
           MEDIAN(rt_bps) AS median_rt_price_diff_bps,
           MEDIAN(qty_match) AS median_rt_qty_match
    FROM legs
    GROUP BY ALL
),
net AS (
    SELECT client_id, symbol, trade_date,
           ABS(SUM(CASE WHEN side = 'BUY' THEN quantity ELSE -quantity END)) / SUM(quantity) AS net_qty_ratio
    FROM t
    GROUP BY ALL
)
SELECT n.client_id, n.symbol, n.trade_date,
       COALESCE(a.n_round_trips, 0) AS n_round_trips,
       a.median_rt_seconds,
       COALESCE(a.share_rt_under_5m, 0) AS share_rt_under_5m,
       a.median_rt_price_diff_bps,
       COALESCE(a.median_rt_qty_match, 0) AS median_rt_qty_match,
       n.net_qty_ratio
FROM net n
LEFT JOIN agg a USING (client_id, symbol, trade_date);
