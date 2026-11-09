# Data story: from the simulator to a real order book

Everything ComplyLite has been measured on is simulated. This page says what the pipeline
expects, what would change on a real broker's data, how to plug a real book in, and what
the repository does not claim.

## What the pipeline reads

The ranked queue is built from one DuckDB file, `market.duckdb`, in the directory named by
`COMPLYLITE_SURVEILLANCE_DIR` (default `data/sim/default`). The feature SQL in
`backend/app/surveillance/sql/` reads five tables. Columns as the simulator writes them
(checked with `DESCRIBE` on a `scripts/simulate.py --preset tiny` run):

| Table | Columns |
|---|---|
| `clients` | client_id, client_name, client_type, risk_rating, account_status, created_date, dealer_id, mobile_hash, email_hash, address_hash |
| `symbols` | symbol, segment, tick_size, half_spread_bps |
| `orders` | order_id, client_id, trader_id, symbol, side, quantity, price, timestamp, order_type, **status, filled_quantity, end_time** |
| `trades` | trade_id, **order_id**, client_id, **counterparty_id**, symbol, side, quantity, price, timestamp |
| `market_bars` | symbol, ts, mid, volume |

Several features depend on columns a small broker may not have in one place:

| Column | Used by | Without it |
|---|---|---|
| `trades.counterparty_id` | `04_counterparty`, `05_linked_accounts`, the wash-trade rule | wash trades between linked accounts cannot be seen |
| `orders.status`, `filled_quantity`, `end_time` | `02_order_cancel`, `06_book_imbalance`, `07_price_impact` | spoofing (place, cancel, trade the other side) cannot be seen |
| `clients.mobile_hash`, `email_hash`, `address_hash` | `05_linked_accounts` | accounts run by one person look unrelated |
| `market_bars` | `07_price_impact` | pump and dump and front running lose their price signal |
| `trades.order_id` | `07_price_impact` | a fill cannot be tied to the order that caused it |

## Not the CSV upload

The API's CSV upload (`POST /api/v1/data/upload/csv`) writes to a separate legacy database
(`compliance.db`) with a narrower schema: orders without status, fill or end time; trades
without order or counterparty; clients without the contact hashes. **Nothing uploaded there
reaches the ranked queue.** Use the route below to evaluate real data.

## How to plug in a real order book

1. Export the five tables above for a period with known outcomes (alerts your analysts
   already closed as real or not). Hash phone, email and address with one salted hash
   before export; the pipeline only compares hashes, it never needs the values.
2. Load them into a new `market.duckdb` with exactly these table and column names
   (DuckDB reads CSV or Parquet directly, for example
   `CREATE TABLE trades AS SELECT * FROM read_parquet('trades.parquet')`).
3. Put your closed-alert labels in `labels.duckdb`: a table `event_units` (client_id,
   symbol, trade_date, pattern) for alerts confirmed as real, and `scenario_units` (same
   keys, scenario) for alerts closed as false, which training uses as hard negatives.
4. Point `COMPLYLITE_SURVEILLANCE_DIR` at that directory and run `scripts/run_eval.py`.
   It trains on the earliest days, tunes on the next block and scores the holdout once,
   and writes `reports/metrics.json` and the ranked `alert_scores` table the API serves.

## What changes on real data

- **The numbers will drop.** The features were written with the simulator's four planted
  patterns in mind. When one pattern is held out of training, the daily queue's recall for
  it falls to 0.69 (wash trade), 0.08 (spoofing), 0.04 (pump and dump) and 0.00 (front
  running) ([reports/EVAL.md](../reports/EVAL.md)). Real manipulation will not match the
  simulator's shapes this neatly.
- **Labels are scarce and biased.** Closed alerts reflect what past rules surfaced; patterns
  the old rules missed have no positive labels at all.
- **Base rates differ.** The simulated holdout has about 26 true alerts a day for 50 review
  slots. A real broker's rate may be far lower, which lowers precision at 50 for every method.
- **Thresholds need retuning.** The rule packs in `backend/app/data/rule_packs` are set for
  the simulator's volumes and price scales.

## What is not claimed

- No result in this repository is on real trading data.
- No claim that the model would catch manipulation patterns it was not built for.
- No regulatory approval or fitness for a filing; the case note is a draft an analyst
  checks, and the language model never decides an alert.
