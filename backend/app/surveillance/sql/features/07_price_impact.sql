-- Price impact around a client's orders and trades, using exchange minute mids (linearly
-- interpolated inside the minute). Signs follow the client's side, so a positive post-trade
-- drift means the price moved in the client's favour after the trade.
--   pre/post_trade_drift_2m/15m_bps : signed mid move in the 2 or 15 minutes before/after trades
--   cancel_order_drift_bps         : signed mid move while the client's cancelled orders rested
--   ret_prior_3d_bps, day_return_bps, net_buy_share_3d : pump-and-dump context
--   trades_ahead_of_dealer_flow    : trades followed within 20 minutes by same-side orders from
--                                    other clients of the same dealer, at least 3x the size
CREATE OR REPLACE TABLE bars_interp AS
SELECT symbol, ts, mid,
       COALESCE(LEAD(mid) OVER (PARTITION BY symbol, CAST(ts AS DATE) ORDER BY ts), mid) AS mid_next
FROM market_bars;

CREATE OR REPLACE TABLE feat_price_impact AS
WITH t AS (
    SELECT trade_id, order_id, client_id, symbol, CAST(timestamp AS DATE) AS trade_date, side, quantity,
           timestamp,
           CASE WHEN side = 'BUY' THEN 1 ELSE -1 END AS sgn,
           timestamp - INTERVAL 15 MINUTE AS ts_b15,
           timestamp - INTERVAL 2 MINUTE AS ts_b2,
           timestamp + INTERVAL 2 MINUTE AS ts_f2,
           timestamp + INTERVAL 15 MINUTE AS ts_f15
    FROM trades
),
m_now AS (
    SELECT t.trade_id,
           b.mid + (b.mid_next - b.mid) * LEAST(date_diff('millisecond', b.ts, t.timestamp) / 60000.0, 1) AS v
    FROM t ASOF JOIN bars_interp b ON t.symbol = b.symbol AND t.timestamp >= b.ts
),
m_b15 AS (
    SELECT t.trade_id,
           b.mid + (b.mid_next - b.mid) * LEAST(date_diff('millisecond', b.ts, t.ts_b15) / 60000.0, 1) AS v
    FROM t ASOF JOIN bars_interp b ON t.symbol = b.symbol AND t.ts_b15 >= b.ts
),
m_b2 AS (
    SELECT t.trade_id,
           b.mid + (b.mid_next - b.mid) * LEAST(date_diff('millisecond', b.ts, t.ts_b2) / 60000.0, 1) AS v
    FROM t ASOF JOIN bars_interp b ON t.symbol = b.symbol AND t.ts_b2 >= b.ts
),
m_f2 AS (
    SELECT t.trade_id,
           b.mid + (b.mid_next - b.mid) * LEAST(date_diff('millisecond', b.ts, t.ts_f2) / 60000.0, 1) AS v
    FROM t ASOF JOIN bars_interp b ON t.symbol = b.symbol AND t.ts_f2 >= b.ts
),
m_f15 AS (
    SELECT t.trade_id,
           b.mid + (b.mid_next - b.mid) * LEAST(date_diff('millisecond', b.ts, t.ts_f15) / 60000.0, 1) AS v
    FROM t ASOF JOIN bars_interp b ON t.symbol = b.symbol AND t.ts_f15 >= b.ts
),
per_trade AS (
    SELECT t.client_id, t.symbol, t.trade_date, t.quantity,
           t.sgn * (n.v / b15.v - 1) * 1e4 AS pre15,
           t.sgn * (n.v / b2.v - 1) * 1e4 AS pre2,
           t.sgn * (f2.v / n.v - 1) * 1e4 AS post2,
           t.sgn * (f15.v / n.v - 1) * 1e4 AS post15
    FROM t
    JOIN m_now n USING (trade_id)
    JOIN m_b15 b15 USING (trade_id)
    JOIN m_b2 b2 USING (trade_id)
    JOIN m_f2 f2 USING (trade_id)
    JOIN m_f15 f15 USING (trade_id)
),
trade_agg AS (
    SELECT client_id, symbol, trade_date,
           SUM(pre15 * quantity) / SUM(quantity) AS pre_trade_drift_15m_bps,
           SUM(pre2 * quantity) / SUM(quantity) AS pre_trade_drift_2m_bps,
           SUM(post2 * quantity) / SUM(quantity) AS post_trade_drift_2m_bps,
           SUM(post15 * quantity) / SUM(quantity) AS post_trade_drift_15m_bps
    FROM per_trade GROUP BY ALL
),
c AS (
    SELECT order_id, client_id, symbol, CAST(timestamp AS DATE) AS trade_date, quantity, timestamp, end_time,
           CASE WHEN side = 'BUY' THEN 1 ELSE -1 END AS sgn
    FROM orders WHERE status = 'CANCELLED'
),
c_start AS (
    SELECT c.order_id,
           b.mid + (b.mid_next - b.mid) * LEAST(date_diff('millisecond', b.ts, c.timestamp) / 60000.0, 1) AS v
    FROM c ASOF JOIN bars_interp b ON c.symbol = b.symbol AND c.timestamp >= b.ts
),
c_end AS (
    SELECT c.order_id,
           b.mid + (b.mid_next - b.mid) * LEAST(date_diff('millisecond', b.ts, c.end_time) / 60000.0, 1) AS v
    FROM c ASOF JOIN bars_interp b ON c.symbol = b.symbol AND c.end_time >= b.ts
),
cancel_agg AS (
    SELECT c.client_id, c.symbol, c.trade_date,
           SUM(c.sgn * (e.v / s.v - 1) * 1e4 * c.quantity) / SUM(c.quantity) AS cancel_order_drift_bps
    FROM c JOIN c_start s USING (order_id) JOIN c_end e USING (order_id)
    GROUP BY ALL
),
sym_daily AS (
    SELECT symbol, CAST(ts AS DATE) AS trade_date, arg_min(mid, ts) AS open_mid, arg_max(mid, ts) AS close_mid
    FROM market_bars GROUP BY ALL
),
sym_ctx AS (
    SELECT symbol, trade_date,
           (close_mid / open_mid - 1) * 1e4 AS day_return_bps,
           (open_mid / LAG(close_mid, 3) OVER (PARTITION BY symbol ORDER BY trade_date) - 1) * 1e4
               AS ret_prior_3d_bps,
           DENSE_RANK() OVER (ORDER BY trade_date) AS day_idx
    FROM sym_daily
),
flow AS (
    SELECT client_id, symbol, CAST(timestamp AS DATE) AS trade_date,
           SUM(CASE WHEN side = 'BUY' THEN quantity * price ELSE -quantity * price END) AS net_notional,
           SUM(quantity * price) AS gross_notional
    FROM trades GROUP BY ALL
),
flow3 AS (
    SELECT f.client_id, f.symbol, f.trade_date,
           SUM(f.net_notional) OVER w / SUM(f.gross_notional) OVER w AS net_buy_share_3d
    FROM flow f
    JOIN (SELECT DISTINCT trade_date, day_idx FROM sym_ctx) d USING (trade_date)
    WINDOW w AS (PARTITION BY f.client_id, f.symbol ORDER BY d.day_idx RANGE BETWEEN 2 PRECEDING AND CURRENT ROW)
),
dealer_orders AS (
    SELECT client_id, trader_id, symbol, side, quantity, timestamp
    FROM orders WHERE trader_id NOT IN ('ONLINE', 'DMA')
),
ahead AS (
    SELECT t.trade_id, t.client_id, t.symbol, t.trade_date, t.quantity, SUM(d.quantity) AS flow_after
    FROM t
    JOIN orders ot ON ot.order_id = t.order_id
    JOIN dealer_orders d
      ON d.trader_id = ot.trader_id AND d.symbol = t.symbol AND d.side = t.side
     AND d.client_id <> t.client_id
     AND d.timestamp > t.timestamp AND d.timestamp <= t.timestamp + INTERVAL 20 MINUTE
    WHERE ot.trader_id NOT IN ('ONLINE', 'DMA')
    GROUP BY ALL
),
ahead_agg AS (
    SELECT client_id, symbol, trade_date,
           COUNT(*) FILTER (WHERE flow_after >= 3 * quantity) AS trades_ahead_of_dealer_flow,
           LN(1 + MAX(flow_after / quantity)) AS log_dealer_flow_ratio
    FROM ahead GROUP BY ALL
)
SELECT u.client_id, u.symbol, u.trade_date,
       ta.pre_trade_drift_15m_bps, ta.pre_trade_drift_2m_bps,
       ta.post_trade_drift_2m_bps, ta.post_trade_drift_15m_bps,
       ca.cancel_order_drift_bps,
       sc.day_return_bps, sc.ret_prior_3d_bps,
       f3.net_buy_share_3d,
       COALESCE(aa.trades_ahead_of_dealer_flow, 0) AS trades_ahead_of_dealer_flow,
       COALESCE(aa.log_dealer_flow_ratio, 0) AS log_dealer_flow_ratio
FROM units u
LEFT JOIN trade_agg ta USING (client_id, symbol, trade_date)
LEFT JOIN cancel_agg ca USING (client_id, symbol, trade_date)
LEFT JOIN sym_ctx sc USING (symbol, trade_date)
LEFT JOIN flow3 f3 USING (client_id, symbol, trade_date)
LEFT JOIN ahead_agg aa USING (client_id, symbol, trade_date);
