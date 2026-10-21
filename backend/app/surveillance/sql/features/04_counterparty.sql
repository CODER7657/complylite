-- Counterparty concentration per unit. 'EXT' means the other side sat at another broker, so
-- only internal counterparties (clients of this broker) can be identified and concentrated.
-- cp_pair_days_10d: for the unit's most persistent internal counterparty, on how many of the
-- last 10 calendar days (today included) the two clients traded with each other in any symbol.
CREATE OR REPLACE TABLE feat_counterparty AS
WITH t AS (
    SELECT client_id, symbol, CAST(timestamp AS DATE) AS trade_date, counterparty_id
    FROM trades
),
tot AS (
    SELECT client_id, symbol, trade_date, COUNT(*) AS n FROM t GROUP BY ALL
),
cp AS (
    SELECT client_id, symbol, trade_date, counterparty_id, COUNT(*) AS k
    FROM t WHERE counterparty_id <> 'EXT'
    GROUP BY ALL
),
cpa AS (
    SELECT client_id, symbol, trade_date,
           SUM(k) AS n_internal, MAX(k) AS max_k, COUNT(*) AS n_cp, SUM(k * k) AS sumsq
    FROM cp GROUP BY ALL
),
pair_days AS (
    SELECT DISTINCT client_id, counterparty_id, trade_date FROM cp
),
pair_hist AS (
    SELECT client_id, counterparty_id, trade_date,
           COUNT(*) OVER (
               PARTITION BY client_id, counterparty_id ORDER BY trade_date
               RANGE BETWEEN INTERVAL 9 DAY PRECEDING AND CURRENT ROW
           ) AS days_together
    FROM pair_days
),
persist AS (
    SELECT cp.client_id, cp.symbol, cp.trade_date, MAX(ph.days_together) AS cp_pair_days_10d
    FROM cp JOIN pair_hist ph USING (client_id, counterparty_id, trade_date)
    GROUP BY ALL
)
SELECT tot.client_id, tot.symbol, tot.trade_date,
       COALESCE(cpa.n_internal, 0) / tot.n AS internal_cp_share,
       COALESCE(cpa.max_k, 0) / tot.n AS top_cp_share,
       COALESCE(cpa.max_k, 0) AS max_trades_same_cp,
       COALESCE(cpa.n_cp, 0) AS n_distinct_internal_cp,
       CASE WHEN cpa.n_internal > 0 THEN cpa.sumsq / (cpa.n_internal * cpa.n_internal) ELSE 0 END
           AS internal_cp_hhi,
       COALESCE(p.cp_pair_days_10d, 0) AS cp_pair_days_10d
FROM tot
LEFT JOIN cpa USING (client_id, symbol, trade_date)
LEFT JOIN persist p USING (client_id, symbol, trade_date);
