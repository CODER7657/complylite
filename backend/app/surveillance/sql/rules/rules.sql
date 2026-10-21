-- The three original ComplyLite detectors, re-expressed per review unit (client, symbol, day)
-- with the obvious bugs fixed. Thresholds come from default_rules.yaml.
--
-- Fixes compared with app/services/detection_rules.py as it was:
--   * The windows were anchored to CURRENT_TIMESTAMP, so historical uploads never fired the wash
--     or high-frequency rules. Here each rule is evaluated on the trading day of the unit.
--   * The self-trade rule self-joined every pair of trades, double-counting pairs (and growing
--     quadratically). It also never looked at the counterparty, so it was really a round-trip
--     rule. It now counts trades whose counterparty is the client itself or a linked account.
--   * Risk scores follow the original formulas (0 to 100); rule_score is the largest one fired.
CREATE OR REPLACE TABLE rule_hits AS
WITH t AS (
    SELECT client_id, symbol, CAST(timestamp AS DATE) AS trade_date, side, quantity, counterparty_id, timestamp
    FROM trades
),
self_t AS (
    SELECT t.client_id, t.symbol, t.trade_date, COUNT(*) AS n,
           COUNT(*) FILTER (WHERE t.counterparty_id = t.client_id OR l.linked_id IS NOT NULL) AS matched
    FROM t LEFT JOIN link_pairs l ON l.client_id = t.client_id AND l.linked_id = t.counterparty_id
    GROUP BY ALL
),
wash AS (
    SELECT client_id, symbol, trade_date, COUNT(*) AS trade_count,
           ABS(SUM(CASE WHEN side = 'BUY' THEN quantity ELSE -quantity END)) AS abs_net,
           AVG(quantity) AS avg_qty
    FROM t GROUP BY ALL
),
hourly AS (
    SELECT client_id, symbol, trade_date, MAX(k) AS max_hourly_trades FROM (
        SELECT client_id, symbol, trade_date, DATE_TRUNC('hour', timestamp) AS hr, COUNT(*) AS k
        FROM t GROUP BY ALL
    ) GROUP BY ALL
),
hits AS (
    SELECT u.client_id, u.symbol, u.trade_date,
           COALESCE(s.matched, 0) >= {self_min_matched} AS self_trade_hit,
           CASE WHEN s.n > 0 THEN LEAST(100.0, s.matched * 100.0 / s.n) ELSE 0 END AS self_trade_risk,
           COALESCE(w.trade_count >= {wash_min_trades} AND w.abs_net <= w.avg_qty * {wash_net_ratio}, FALSE)
               AS wash_trade_hit,
           LEAST(100.0, COALESCE(w.trade_count, 0) * 10.0) AS wash_trade_risk,
           COALESCE(h.max_hourly_trades > {hf_min_per_hour}, FALSE) AS high_frequency_hit,
           LEAST(100.0, COALESCE(h.max_hourly_trades, 0) * 1.0) AS high_frequency_risk
    FROM units u
    LEFT JOIN self_t s USING (client_id, symbol, trade_date)
    LEFT JOIN wash w USING (client_id, symbol, trade_date)
    LEFT JOIN hourly h USING (client_id, symbol, trade_date)
)
SELECT client_id, symbol, trade_date, self_trade_hit, wash_trade_hit, high_frequency_hit,
       GREATEST(
           CASE WHEN self_trade_hit THEN self_trade_risk ELSE 0 END,
           CASE WHEN wash_trade_hit THEN wash_trade_risk ELSE 0 END,
           CASE WHEN high_frequency_hit THEN high_frequency_risk ELSE 0 END
       ) AS rule_score,
       concat_ws(',',
           CASE WHEN self_trade_hit THEN 'SELF_TRADE' END,
           CASE WHEN wash_trade_hit THEN 'WASH_TRADE' END,
           CASE WHEN high_frequency_hit THEN 'HIGH_FREQUENCY' END
       ) AS rules_fired
FROM hits;
