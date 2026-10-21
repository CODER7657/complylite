-- Activity and rolling windows per client and instrument.
-- notional_vs_prior compares today's traded value with the same client's average in the same
-- symbol over the previous 10 calendar days (NULL when there is no history).
CREATE OR REPLACE TABLE feat_activity AS
WITH t AS (
    SELECT client_id, symbol, CAST(timestamp AS DATE) AS trade_date,
           COUNT(*) AS n_trades, SUM(quantity * price) AS notional
    FROM trades
    GROUP BY ALL
),
o AS (
    SELECT client_id, symbol, CAST(timestamp AS DATE) AS trade_date, COUNT(*) AS n_orders
    FROM orders
    GROUP BY ALL
),
d AS (
    SELECT u.client_id, u.symbol, u.trade_date, o.n_orders,
           COALESCE(t.n_trades, 0) AS n_trades,
           COALESCE(t.notional, 0) AS notional
    FROM units u
    JOIN o USING (client_id, symbol, trade_date)
    LEFT JOIN t USING (client_id, symbol, trade_date)
),
sym_day AS (
    SELECT symbol, trade_date, SUM(notional) AS broker_notional FROM t GROUP BY ALL
),
client_day AS (
    SELECT client_id, trade_date, COUNT(*) AS symbols_today FROM units GROUP BY ALL
),
roll AS (
    SELECT d.*,
           AVG(notional) OVER w AS prior_avg_notional,
           COUNT(*) OVER w AS prior_active_days
    FROM d
    WINDOW w AS (
        PARTITION BY client_id, symbol ORDER BY trade_date
        RANGE BETWEEN INTERVAL 10 DAY PRECEDING AND INTERVAL 1 DAY PRECEDING
    )
)
SELECT r.client_id, r.symbol, r.trade_date,
       r.n_orders,
       r.n_trades,
       LN(1 + r.notional) AS log_notional,
       CASE WHEN r.prior_avg_notional > 0 THEN r.notional / r.prior_avg_notional END AS notional_vs_prior,
       r.prior_active_days,
       CASE WHEN s.broker_notional > 0 THEN r.notional / s.broker_notional ELSE 0 END AS share_of_broker_flow,
       cd.symbols_today,
       CASE WHEN c.client_type = 'MARKET_MAKER' THEN 1 ELSE 0 END AS is_market_maker,
       CASE WHEN c.client_type = 'INSTITUTIONAL' THEN 1 ELSE 0 END AS is_institutional,
       CASE WHEN c.client_type = 'DAY_TRADER' THEN 1 ELSE 0 END AS is_day_trader
FROM roll r
LEFT JOIN sym_day s USING (symbol, trade_date)
LEFT JOIN client_day cd USING (client_id, trade_date)
LEFT JOIN clients c USING (client_id);
