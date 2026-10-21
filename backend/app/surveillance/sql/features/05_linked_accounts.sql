-- Self and linked-account matching. Two clients are linked when they share a mobile number,
-- email or address (hashed in the client master). Family accounts are linked too, which is
-- why linked trading on its own is not proof of anything.
CREATE OR REPLACE TABLE link_pairs AS
SELECT DISTINCT client_id, linked_id FROM (
    SELECT a.client_id, b.client_id AS linked_id FROM clients a JOIN clients b
      ON a.mobile_hash = b.mobile_hash AND a.client_id <> b.client_id
    UNION ALL
    SELECT a.client_id, b.client_id FROM clients a JOIN clients b
      ON a.email_hash = b.email_hash AND a.client_id <> b.client_id
    UNION ALL
    SELECT a.client_id, b.client_id FROM clients a JOIN clients b
      ON a.address_hash = b.address_hash AND a.client_id <> b.client_id
);

CREATE OR REPLACE TABLE feat_linked_accounts AS
WITH t AS (
    SELECT t.client_id, t.symbol, CAST(t.timestamp AS DATE) AS trade_date, t.side, t.quantity,
           t.counterparty_id = t.client_id AS is_self,
           l.linked_id IS NOT NULL AS is_linked
    FROM trades t
    LEFT JOIN link_pairs l ON l.client_id = t.client_id AND l.linked_id = t.counterparty_id
),
agg AS (
    SELECT client_id, symbol, trade_date, COUNT(*) AS n,
           COUNT(*) FILTER (WHERE is_self) AS self_cp_trades,
           COUNT(*) FILTER (WHERE is_self OR is_linked) AS linked_cp_trades,
           SUM(CASE WHEN side = 'BUY' THEN quantity ELSE -quantity END) AS net_qty
    FROM t GROUP BY ALL
),
nlinks AS (
    SELECT client_id, COUNT(*) AS n_linked_accounts FROM link_pairs GROUP BY ALL
),
mirror AS (
    SELECT u.client_id, u.symbol, u.trade_date,
           COUNT(DISTINCT l.linked_id) AS linked_same_symbol_today,
           COUNT(DISTINCT l.linked_id) FILTER (WHERE a1.net_qty * a2.net_qty < 0) AS linked_opposite_side_today
    FROM units u
    JOIN link_pairs l ON l.client_id = u.client_id
    JOIN units u2 ON u2.client_id = l.linked_id AND u2.symbol = u.symbol AND u2.trade_date = u.trade_date
    LEFT JOIN agg a1 ON a1.client_id = u.client_id AND a1.symbol = u.symbol AND a1.trade_date = u.trade_date
    LEFT JOIN agg a2 ON a2.client_id = u2.client_id AND a2.symbol = u2.symbol AND a2.trade_date = u2.trade_date
    GROUP BY ALL
)
SELECT u.client_id, u.symbol, u.trade_date,
       COALESCE(nl.n_linked_accounts, 0) AS n_linked_accounts,
       COALESCE(a.self_cp_trades, 0) AS self_cp_trades,
       COALESCE(a.linked_cp_trades, 0) AS linked_cp_trades,
       CASE WHEN a.n > 0 THEN a.linked_cp_trades / a.n ELSE 0 END AS linked_cp_share,
       COALESCE(m.linked_same_symbol_today, 0) AS linked_same_symbol_today,
       COALESCE(m.linked_opposite_side_today, 0) AS linked_opposite_side_today
FROM units u
LEFT JOIN agg a USING (client_id, symbol, trade_date)
LEFT JOIN nlinks nl USING (client_id)
LEFT JOIN mirror m USING (client_id, symbol, trade_date);
