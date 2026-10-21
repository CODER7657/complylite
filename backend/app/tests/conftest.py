"""Shared helpers: tiny hand-made market databases for SQL feature tests."""
from __future__ import annotations

from datetime import datetime, timedelta

import duckdb
import pandas as pd
import pytest

from app.surveillance.features import feature_sql_files, run_sql_file

DAY = datetime(2026, 3, 2, 9, 15)


def ts(minutes: float = 0.0, day: int = 0) -> datetime:
    return DAY + timedelta(days=day, minutes=minutes)


CLIENT_COLS = ["client_id", "client_name", "client_type", "risk_rating", "account_status", "created_date",
               "dealer_id", "mobile_hash", "email_hash", "address_hash"]
ORDER_COLS = ["order_id", "client_id", "trader_id", "symbol", "side", "quantity", "price", "timestamp",
              "order_type", "status", "filled_quantity", "end_time"]
TRADE_COLS = ["trade_id", "order_id", "client_id", "counterparty_id", "symbol", "side", "quantity", "price",
              "timestamp"]


def client(cid, ctype="RETAIL", mobile=None, email=None, address=None, dealer="ONLINE"):
    return dict(client_id=cid, client_name=cid, client_type=ctype, risk_rating="LOW", account_status="ACTIVE",
                created_date=DAY.date(), dealer_id=dealer, mobile_hash=mobile or f"m{cid}",
                email_hash=email or f"e{cid}", address_hash=address or f"a{cid}")


def order(oid, cid, side, qty, price, t, status="FILLED", end=None, symbol="AAA", trader="ONLINE", filled=None):
    return dict(order_id=oid, client_id=cid, trader_id=trader, symbol=symbol, side=side, quantity=qty, price=price,
                timestamp=t, order_type="LIMIT", status=status,
                filled_quantity=(qty if status == "FILLED" else 0) if filled is None else filled,
                end_time=end or (t + timedelta(seconds=1)))


def trade(tid, oid, cid, side, qty, price, t, cp="EXT", symbol="AAA"):
    return dict(trade_id=tid, order_id=oid, client_id=cid, counterparty_id=cp, symbol=symbol, side=side,
                quantity=qty, price=price, timestamp=t)


def flat_bars(symbol="AAA", price=100.0, days=1, jump_at=None, jump_to=None):
    rows = []
    for d in range(days):
        for m in range(376):
            p = jump_to if (jump_at is not None and d == 0 and m >= jump_at) else price
            rows.append(dict(symbol=symbol, ts=ts(m, d), mid=p, volume=1000))
    return rows


def build_db(clients, orders, trades, bars=None) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    frames = {
        "clients": pd.DataFrame(clients, columns=CLIENT_COLS),
        "orders": pd.DataFrame(orders, columns=ORDER_COLS),
        "trades": pd.DataFrame(trades, columns=TRADE_COLS),
        "market_bars": pd.DataFrame(bars if bars is not None else flat_bars(),
                                    columns=["symbol", "ts", "mid", "volume"]),
    }
    casts = {"quantity": "BIGINT", "filled_quantity": "BIGINT", "price": "DOUBLE", "mid": "DOUBLE",
             "timestamp": "TIMESTAMP", "end_time": "TIMESTAMP", "ts": "TIMESTAMP", "volume": "BIGINT"}
    for name, df in frames.items():
        con.register("_df", df)
        cols = ", ".join(f"CAST({c} AS {casts[c]}) AS {c}" if c in casts else f"CAST({c} AS VARCHAR) AS {c}"
                         if c not in ("created_date",) else c for c in df.columns)
        con.execute(f"CREATE TABLE {name} AS SELECT {cols} FROM _df")
        con.unregister("_df")
    return con


def run_family(con, *prefixes: str) -> None:
    """Run 00_units.sql plus the named feature files (by filename prefix)."""
    for path in feature_sql_files():
        if path.name.startswith("00_") or any(path.name.startswith(p) for p in prefixes):
            run_sql_file(con, path)


def row(con, table: str, client_id: str, symbol: str = "AAA") -> dict:
    df = con.execute(f"SELECT * FROM {table} WHERE client_id = ? AND symbol = ? ORDER BY trade_date",
                     [client_id, symbol]).df()
    assert len(df) >= 1, f"no row for {client_id} in {table}"
    return df.iloc[-1].to_dict()


@pytest.fixture
def T():
    return ts
