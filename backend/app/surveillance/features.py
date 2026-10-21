"""Build the per-unit feature table and the rule hits from the SQL files in ``sql/``.

A review unit is one client trading one symbol on one day. Each feature family lives in its own
SQL file under ``sql/features`` and writes one ``feat_*`` table keyed by
(client_id, symbol, trade_date). ``build_features`` runs them in file order and joins the
results into a single ``features`` table.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from app.core.rules import load_rules
from app.surveillance.paths import SQL_DIR

KEYS = ["client_id", "symbol", "trade_date"]

# name -> plain-language description, used in explanations and case notes.
FEATURES: dict[str, str] = {
    "n_orders": "orders placed",
    "n_trades": "trades executed",
    "log_notional": "log of traded value",
    "notional_vs_prior": "traded value versus the client's own 10-day average in this symbol",
    "prior_active_days": "days the client traded this symbol in the previous 10 days",
    "share_of_broker_flow": "share of the broker's traded value in this symbol today",
    "symbols_today": "symbols the client traded today",
    "is_market_maker": "client is a registered market maker",
    "is_institutional": "client is an institution",
    "is_day_trader": "client is an intraday trader",
    "n_cancelled": "orders cancelled",
    "cancel_to_fill_ratio": "cancelled orders per filled order",
    "order_to_trade_ratio": "orders per filled order",
    "fast_cancel_share": "share of cancels within 2 seconds",
    "cancel_fill_size_ratio": "size of cancelled orders versus filled orders",
    "cancelled_qty_share": "share of placed quantity that was cancelled",
    "median_cancel_life_s": "median life of cancelled orders (seconds)",
    "n_round_trips": "buy/sell round trips",
    "median_rt_seconds": "median round-trip time (seconds)",
    "share_rt_under_5m": "share of round trips under 5 minutes",
    "median_rt_price_diff_bps": "median price difference between round-trip legs (bps)",
    "median_rt_qty_match": "how closely round-trip quantities match (1 = identical)",
    "net_qty_ratio": "net position as a share of gross quantity",
    "internal_cp_share": "share of trades against another client of this broker",
    "top_cp_share": "share of trades against the single most frequent internal counterparty",
    "max_trades_same_cp": "trades against the single most frequent internal counterparty",
    "n_distinct_internal_cp": "distinct internal counterparties",
    "internal_cp_hhi": "concentration of internal counterparties (HHI)",
    "cp_pair_days_10d": "days in the last 10 the client traded with its main internal counterparty",
    "n_linked_accounts": "accounts linked by shared mobile, email or address",
    "self_cp_trades": "trades against itself",
    "linked_cp_trades": "trades against itself or a linked account",
    "linked_cp_share": "share of trades against itself or a linked account",
    "linked_same_symbol_today": "linked accounts trading the same symbol today",
    "linked_opposite_side_today": "linked accounts on the opposite net side today",
    "spoof_sequences": "fills bracketed by quickly cancelled opposite-side orders",
    "max_layer_levels": "distinct price levels in a cancelled opposite-side cluster",
    "placed_vs_filled_imbalance_gap": "gap between the side the client showed and the side it traded",
    "pre_trade_drift_15m_bps": "signed price move in the 15 minutes before trades (bps)",
    "pre_trade_drift_2m_bps": "signed price move in the 2 minutes before trades (bps)",
    "post_trade_drift_2m_bps": "signed price move in the 2 minutes after trades (bps)",
    "post_trade_drift_15m_bps": "signed price move in the 15 minutes after trades (bps)",
    "cancel_order_drift_bps": "signed price move while cancelled orders were resting (bps)",
    "day_return_bps": "symbol's open-to-close return today (bps)",
    "ret_prior_3d_bps": "symbol's return over the previous 3 trading days (bps)",
    "net_buy_share_3d": "client's net buying as a share of gross over 3 trading days",
    "trades_ahead_of_dealer_flow": "trades placed just before larger same-side orders via the same dealer",
    "log_dealer_flow_ratio": "size of that later dealer flow relative to the client's trade (log)",
}
FEATURE_COLUMNS = list(FEATURES)


def feature_sql_files() -> list[Path]:
    return sorted((SQL_DIR / "features").glob("*.sql"))


def run_sql_file(con: duckdb.DuckDBPyConnection, path: Path) -> None:
    con.execute(path.read_text(encoding="utf-8"))


def build_features(con: duckdb.DuckDBPyConnection) -> None:
    """Run every feature SQL file, then join the families into ``features``."""
    for path in feature_sql_files():
        run_sql_file(con, path)
    fam = [r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables WHERE starts_with(table_name, 'feat_') ORDER BY table_name"
    ).fetchall()]
    joins = "\n".join(f"LEFT JOIN {t} USING (client_id, symbol, trade_date)" for t in fam)
    con.execute(f"CREATE OR REPLACE TABLE features AS SELECT * FROM units {joins}")
    cols = {r[0] for r in con.execute("DESCRIBE features").fetchall()}
    missing = [c for c in FEATURE_COLUMNS if c not in cols]
    if missing:
        raise RuntimeError(f"feature columns missing after build: {missing}")


def rule_params(rules: dict | None = None) -> dict:
    rules = rules if rules is not None else load_rules()
    st = rules.get("self_trade_detection", {})
    wt = rules.get("wash_trade_detection", {})
    hf = rules.get("high_frequency_pattern", {})
    return {
        "self_min_matched": int(st.get("min_offsetting_trades", 2)),
        "wash_min_trades": int(wt.get("min_trades", 6)),
        "wash_net_ratio": float(wt.get("net_position_threshold_ratio", 0.1)),
        "hf_min_per_hour": int(hf.get("min_max_trades_per_hour", 10)),
    }


def build_rules(con: duckdb.DuckDBPyConnection, rules: dict | None = None) -> None:
    """Evaluate the fixed rule pack per unit into ``rule_hits`` (needs ``units`` and ``link_pairs``)."""
    sql = (SQL_DIR / "rules" / "rules.sql").read_text(encoding="utf-8")
    con.execute(sql.format(**rule_params(rules)))


def load_matrix(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    df = con.execute(
        "SELECT f.*, r.rule_score, r.rules_fired, r.self_trade_hit, r.wash_trade_hit, r.high_frequency_hit "
        "FROM features f JOIN rule_hits r USING (client_id, symbol, trade_date) "
        "ORDER BY trade_date, client_id, symbol"
    ).df()
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    return df
