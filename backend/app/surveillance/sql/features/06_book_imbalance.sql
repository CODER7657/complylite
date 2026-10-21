-- Order-book imbalance proxies from the client's own orders.
-- A spoof sequence is a fill that had at least two of the client's own opposite-side orders
-- placed in the 60 seconds before it and cancelled within 30 seconds after it.
-- placed_vs_filled_imbalance_gap: |buy-sell imbalance of placed quantity minus that of filled
-- quantity|. Someone who shows size on one side and trades on the other scores high.
CREATE OR REPLACE TABLE feat_book_imbalance AS
WITH o AS (
    SELECT client_id, symbol, CAST(timestamp AS DATE) AS trade_date, side, quantity, price,
           timestamp, end_time, status, filled_quantity
    FROM orders
),
f AS (
    SELECT trade_id, client_id, symbol, CAST(timestamp AS DATE) AS trade_date, side, timestamp
    FROM trades
),
seq AS (
    SELECT f.trade_id, f.client_id, f.symbol, f.trade_date,
           COUNT(*) AS n_opp, COUNT(DISTINCT o.price) AS n_levels
    FROM f JOIN o
      ON o.client_id = f.client_id AND o.symbol = f.symbol AND o.trade_date = f.trade_date
     AND o.side <> f.side AND o.status = 'CANCELLED'
     AND o.timestamp BETWEEN f.timestamp - INTERVAL 60 SECOND AND f.timestamp
     AND o.end_time BETWEEN f.timestamp AND f.timestamp + INTERVAL 30 SECOND
    GROUP BY ALL
),
seq_agg AS (
    SELECT client_id, symbol, trade_date,
           COUNT(*) FILTER (WHERE n_opp >= 2) AS spoof_sequences,
           MAX(n_levels) AS max_layer_levels
    FROM seq GROUP BY ALL
),
imb AS (
    SELECT client_id, symbol, trade_date,
           SUM(CASE WHEN side = 'BUY' THEN quantity ELSE -quantity END) / SUM(quantity) AS placed_imbalance,
           SUM(CASE WHEN side = 'BUY' THEN filled_quantity ELSE -filled_quantity END)
               / NULLIF(SUM(filled_quantity), 0) AS filled_imbalance
    FROM o GROUP BY ALL
)
SELECT u.client_id, u.symbol, u.trade_date,
       COALESCE(s.spoof_sequences, 0) AS spoof_sequences,
       COALESCE(s.max_layer_levels, 0) AS max_layer_levels,
       COALESCE(ABS(i.placed_imbalance - i.filled_imbalance), 0) AS placed_vs_filled_imbalance_gap
FROM units u
LEFT JOIN seq_agg s USING (client_id, symbol, trade_date)
LEFT JOIN imb i USING (client_id, symbol, trade_date);
