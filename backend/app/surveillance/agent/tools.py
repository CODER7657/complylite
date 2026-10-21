"""Read-only, row-limited tools the case-note planner may call.

Every tool runs on a DuckDB connection opened with ``read_only=True`` and external access
disabled, and every result is capped in rows. Each call also records the numbers it returned in
a ledger, which the checker uses to confirm that numbers in the note came from the data.
"""
from __future__ import annotations

import json
import math
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from app.surveillance.agent.sql_guard import SqlGuardError, limited
from app.surveillance.features import FEATURE_COLUMNS, FEATURES
from app.surveillance.paths import MARKET_DB

SQL_ROW_LIMIT = 200
SHOW_ROWS = 40
QUERY_TIMEOUT_S = 10.0

SCHEMA_HINT = (
    "Tables: trades(trade_id, order_id, client_id, counterparty_id, symbol, side, quantity, price, timestamp) "
    "where counterparty_id is another client of this broker or 'EXT' for the rest of the market; "
    "orders(order_id, client_id, trader_id, symbol, side, quantity, price, timestamp, order_type, status, "
    "filled_quantity, end_time) where status is FILLED, PARTIAL or CANCELLED and end_time is the fill or cancel "
    "time; clients(client_id, client_type, risk_rating, account_status, created_date, dealer_id); "
    "link_pairs(client_id, linked_id) for accounts sharing a mobile, email or address; "
    "market_bars(symbol, ts, mid, volume) one row per minute; "
    "features(client_id, symbol, trade_date, ...) the model inputs; "
    "alert_scores(alert_id, client_id, symbol, trade_date, daily_rank, final_score, rules_fired, ...)."
)


def open_readonly(db_path: str | Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(db_path), read_only=True, config={"enable_external_access": False})
    return con


def _jsonable(v: Any) -> Any:
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if math.isnan(f) else round(f, 4)
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if v is pd.NaT:
        return None
    return v


def _records(df: pd.DataFrame) -> list[dict]:
    return [{k: _jsonable(v) for k, v in r.items()} for r in df.to_dict("records")]


def _numbers(obj: Any, out: list[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)) and not (isinstance(obj, float) and math.isnan(obj)):
        out.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _numbers(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _numbers(v, out)


class ReadOnlyTools:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        if self.db_path.is_dir():
            self.db_path = self.db_path / MARKET_DB
        self.con = open_readonly(self.db_path)
        self.ledger: list[float] = []
        self.calls: list[dict] = []
        self._past: pd.DataFrame | None = None

    def close(self) -> None:
        self.con.close()

    def reset(self) -> None:
        self.ledger, self.calls = [], []

    # ----------------------------------------------------------------- internals
    def _query(self, sql: str, params: list | None = None) -> pd.DataFrame:
        timer = threading.Timer(QUERY_TIMEOUT_S, self.con.interrupt)
        timer.start()
        try:
            return self.con.execute(sql, params or []).df()
        finally:
            timer.cancel()

    def _record(self, name: str, args: dict, result: dict) -> str:
        _numbers(result, self.ledger)
        self.calls.append({"tool": name, "args": args})
        return json.dumps(result, default=str, separators=(",", ":"))

    # --------------------------------------------------------------------- tools
    def sql_query(self, query: str) -> str:
        try:
            df = self._query(limited(query, SQL_ROW_LIMIT))
        except SqlGuardError as e:
            return self._record("sql_query", {"query": query}, {"error": f"rejected: {e}"})
        except duckdb.Error as e:
            return self._record("sql_query", {"query": query}, {"error": str(e).splitlines()[0][:300]})
        rows = _records(df.head(SHOW_ROWS))
        res = {"columns": list(df.columns), "rows": [list(r.values()) for r in rows], "row_count": len(df),
               "truncated": len(df) > SHOW_ROWS}
        return self._record("sql_query", {"query": query}, res)

    def client_profile(self, client_id: str, as_of: str | None = None) -> str:
        c = self._query("SELECT client_id, client_type, risk_rating, account_status, created_date, dealer_id "
                        "FROM clients WHERE client_id = ?", [client_id])
        if c.empty:
            return self._record("client_profile", {"client_id": client_id}, {"error": "unknown client"})
        as_of = as_of or "9999-12-31"
        linked = self._query("SELECT linked_id FROM link_pairs WHERE client_id = ? ORDER BY 1", [client_id])
        act = self._query(
            "SELECT COUNT(DISTINCT CAST(timestamp AS DATE)) AS active_days, COUNT(DISTINCT symbol) AS symbols, "
            "COUNT(*) AS trades, ROUND(SUM(quantity * price), 2) AS traded_value "
            "FROM trades WHERE client_id = ? AND CAST(timestamp AS DATE) < CAST(? AS DATE) "
            "AND CAST(timestamp AS DATE) >= CAST(? AS DATE) - INTERVAL 14 DAY", [client_id, as_of, as_of])
        prior = self._query(
            "SELECT COUNT(*) AS n FROM alert_scores WHERE client_id = ? AND in_queue AND trade_date < CAST(? AS DATE)",
            [client_id, as_of])
        past = self._query(
            "SELECT outcome, COUNT(*) AS n FROM past_cases WHERE client_id = ? AND trade_date < CAST(? AS DATE) "
            "GROUP BY 1", [client_id, as_of])
        res = {
            "client": _records(c)[0],
            "linked_accounts": linked["linked_id"].tolist(),
            "last_14_days_before_alert": _records(act)[0],
            "earlier_queued_alerts": int(prior["n"].iloc[0]),
            "past_case_outcomes": {r["outcome"]: int(r["n"]) for r in _records(past)},
        }
        return self._record("client_profile", {"client_id": client_id, "as_of": as_of}, res)

    def price_window(self, symbol: str, start: str, end: str) -> str:
        try:
            df = self._query("SELECT ts, mid, volume FROM market_bars WHERE symbol = ? AND ts BETWEEN "
                             "CAST(? AS TIMESTAMP) AND CAST(? AS TIMESTAMP) ORDER BY ts", [symbol, start, end])
        except duckdb.Error as e:
            return self._record("price_window", {"symbol": symbol}, {"error": str(e).splitlines()[0][:200]})
        if df.empty:
            return self._record("price_window", {"symbol": symbol, "start": start, "end": end}, {"error": "no bars"})
        step = max(1, math.ceil(len(df) / 60))
        shown = df.iloc[::step]
        first, last = float(df["mid"].iloc[0]), float(df["mid"].iloc[-1])
        res = {
            "summary": {"first_mid": round(first, 2), "last_mid": round(last, 2),
                        "high_mid": round(float(df["mid"].max()), 2), "low_mid": round(float(df["mid"].min()), 2),
                        "change_bps": round((last / first - 1) * 1e4, 1), "minutes": len(df),
                        "total_volume": int(df["volume"].sum())},
            "every_n_minutes": step,
            "bars": [[_jsonable(t), round(float(m), 2), int(v)] for t, m, v in
                     zip(shown["ts"], shown["mid"], shown["volume"])],
        }
        return self._record("price_window", {"symbol": symbol, "start": start, "end": end}, res)

    def similar_past_cases(self, alert_id: str, k: int = 5) -> str:
        cur = self._query("SELECT f.* FROM alert_scores a JOIN features f USING (client_id, symbol, trade_date) "
                          "WHERE a.alert_id = ?", [alert_id])
        if cur.empty:
            return self._record("similar_past_cases", {"alert_id": alert_id}, {"error": "unknown alert"})
        if self._past is None:
            self._past = self._query("SELECT * FROM past_cases")
        past = self._past
        if past.empty:
            return self._record("similar_past_cases", {"alert_id": alert_id}, {"cases": []})
        X = past[FEATURE_COLUMNS].astype(float)
        mu, sd = X.mean(), X.std().replace(0, 1).fillna(1)
        Z = ((X - mu) / sd).fillna(0)
        z = ((cur[FEATURE_COLUMNS].astype(float).iloc[0] - mu) / sd).fillna(0)
        dist = np.sqrt(((Z - z) ** 2).sum(axis=1))
        idx = np.argsort(dist.to_numpy())[: max(1, min(int(k), 10))]
        cases = []
        for i in idx:
            r = past.iloc[i]
            close = (Z.iloc[i] - z).abs().sort_values().index[:3]
            cases.append({"alert_id": r["alert_id"], "outcome": r["outcome"], "pattern": r["pattern"],
                          "distance": round(float(dist.iloc[i]), 2),
                          "most_similar_on": [FEATURES[c] for c in close]})
        res = {"note": "past cases are alerts already closed on earlier days", "cases": cases}
        return self._record("similar_past_cases", {"alert_id": alert_id, "k": k}, res)

    # ------------------------------------------------------------ dispatch/schema
    def call(self, name: str, args: dict) -> str:
        fn = {"sql_query": self.sql_query, "client_profile": self.client_profile,
              "price_window": self.price_window, "similar_past_cases": self.similar_past_cases}.get(name)
        if fn is None:
            return json.dumps({"error": f"unknown tool {name}"})
        try:
            return fn(**args)
        except TypeError as e:
            return json.dumps({"error": f"bad arguments: {e}"})


TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "sql_query",
        "description": "Run one read-only SELECT on the broker's DuckDB data. At most 200 rows are computed and "
                       f"{SHOW_ROWS} returned. " + SCHEMA_HINT,
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "client_profile",
        "description": "Client master record, linked accounts, activity in the 14 days before as_of, and how "
                       "earlier alerts on this client were closed.",
        "parameters": {"type": "object", "properties": {
            "client_id": {"type": "string"}, "as_of": {"type": "string", "description": "YYYY-MM-DD"}},
            "required": ["client_id"]}}},
    {"type": "function", "function": {
        "name": "price_window",
        "description": "Exchange minute mids and volume for a symbol between two timestamps "
                       "('YYYY-MM-DD HH:MM:SS'), with a summary. Long windows are thinned to about 60 bars.",
        "parameters": {"type": "object", "properties": {
            "symbol": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"}},
            "required": ["symbol", "start", "end"]}}},
    {"type": "function", "function": {
        "name": "similar_past_cases",
        "description": "The closest already-closed alerts from earlier days by feature profile, with how each was "
                       "closed (ESCALATED or DISMISSED).",
        "parameters": {"type": "object", "properties": {
            "alert_id": {"type": "string"}, "k": {"type": "integer"}}, "required": ["alert_id"]}}},
]
