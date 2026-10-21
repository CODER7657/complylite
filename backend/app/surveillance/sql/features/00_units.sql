-- Units of review: one row per client, symbol and trading day with at least one order.
-- Every feature family, the rules and the models score these same units.
CREATE OR REPLACE TABLE units AS
SELECT client_id, symbol, CAST(timestamp AS DATE) AS trade_date
FROM orders
GROUP BY ALL;
