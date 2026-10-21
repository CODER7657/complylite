"""One test per feature family, each on a tiny hand-made fixture with values worked out by hand."""
from datetime import timedelta

import pytest

from app.surveillance.features import FEATURE_COLUMNS, build_features, build_rules
from app.tests.conftest import build_db, client, flat_bars, order, row, run_family, trade, ts


def test_units_one_row_per_client_symbol_day():
    con = build_db(
        [client("C1")],
        [order("o1", "C1", "BUY", 10, 100, ts(5)), order("o2", "C1", "SELL", 10, 100, ts(6)),
         order("o3", "C1", "BUY", 10, 100, ts(5, day=1))],
        [],
    )
    run_family(con)
    assert con.execute("SELECT COUNT(*) FROM units").fetchone()[0] == 2


def test_activity_rolling_window_and_share():
    con = build_db(
        [client("C1", ctype="DAY_TRADER"), client("C2")],
        [order("o1", "C1", "BUY", 10, 100, ts(5)), order("o2", "C1", "BUY", 30, 100, ts(5, day=1)),
         order("o3", "C2", "BUY", 10, 100, ts(6, day=1))],
        [trade("t1", "o1", "C1", "BUY", 10, 100, ts(5)), trade("t2", "o2", "C1", "BUY", 30, 100, ts(5, day=1)),
         trade("t3", "o3", "C2", "BUY", 10, 100, ts(6, day=1))],
        flat_bars(days=2),
    )
    run_family(con, "01_")
    r = row(con, "feat_activity", "C1")
    assert r["notional_vs_prior"] == pytest.approx(3000 / 1000)
    assert r["prior_active_days"] == 1
    assert r["share_of_broker_flow"] == pytest.approx(3000 / 4000)
    assert r["is_day_trader"] == 1 and r["is_market_maker"] == 0


def test_order_cancel_ratios():
    t0 = ts(10)
    con = build_db(
        [client("C1")],
        [order("o1", "C1", "BUY", 100, 100, t0, status="CANCELLED", end=t0 + timedelta(seconds=1)),
         order("o2", "C1", "BUY", 300, 100, t0, status="CANCELLED", end=t0 + timedelta(seconds=10)),
         order("o3", "C1", "SELL", 50, 100, t0)],
        [trade("t1", "o3", "C1", "SELL", 50, 100, t0 + timedelta(seconds=1))],
    )
    run_family(con, "02_")
    r = row(con, "feat_order_cancel", "C1")
    assert r["n_cancelled"] == 2
    assert r["cancel_to_fill_ratio"] == pytest.approx(2 / 2)  # 2 cancels / (1 fill + 1)
    assert r["order_to_trade_ratio"] == 3
    assert r["fast_cancel_share"] == pytest.approx(0.5)
    assert r["cancel_fill_size_ratio"] == pytest.approx(200 / 50)
    assert r["cancelled_qty_share"] == pytest.approx(400 / 450)


def test_round_trip_time_price_and_quantity():
    con = build_db(
        [client("C1")],
        [order("o1", "C1", "BUY", 100, 100.0, ts(10)), order("o2", "C1", "SELL", 100, 100.05, ts(12))],
        [trade("t1", "o1", "C1", "BUY", 100, 100.0, ts(10)), trade("t2", "o2", "C1", "SELL", 100, 100.05, ts(12))],
    )
    run_family(con, "03_")
    r = row(con, "feat_round_trip", "C1")
    assert r["n_round_trips"] == 1
    assert r["median_rt_seconds"] == pytest.approx(120)
    assert r["share_rt_under_5m"] == 1
    assert r["median_rt_price_diff_bps"] == pytest.approx(5.0)
    assert r["median_rt_qty_match"] == 1
    assert r["net_qty_ratio"] == 0


def test_counterparty_concentration():
    con = build_db(
        [client("C1"), client("C2")],
        [order(f"o{i}", "C1", "BUY", 10, 100, ts(i)) for i in range(3)],
        [trade("t0", "o0", "C1", "BUY", 10, 100, ts(0), cp="C2"),
         trade("t1", "o1", "C1", "BUY", 10, 100, ts(1), cp="C2"),
         trade("t2", "o2", "C1", "BUY", 10, 100, ts(2), cp="EXT")],
    )
    run_family(con, "04_")
    r = row(con, "feat_counterparty", "C1")
    assert r["internal_cp_share"] == pytest.approx(2 / 3)
    assert r["top_cp_share"] == pytest.approx(2 / 3)
    assert r["max_trades_same_cp"] == 2
    assert r["n_distinct_internal_cp"] == 1
    assert r["internal_cp_hhi"] == pytest.approx(1.0)
    assert r["cp_pair_days_10d"] == 1


def test_linked_accounts_matching():
    con = build_db(
        [client("C1", mobile="same"), client("C2", mobile="same"), client("C3")],
        [order("o1", "C1", "BUY", 10, 100, ts(1)), order("o2", "C2", "SELL", 10, 100, ts(1)),
         order("o3", "C1", "SELL", 10, 100, ts(3)), order("o4", "C2", "BUY", 10, 100, ts(3)),
         order("o5", "C3", "BUY", 10, 100, ts(4))],
        [trade("t1", "o1", "C1", "BUY", 10, 100, ts(1), cp="C2"),
         trade("t2", "o2", "C2", "SELL", 10, 100, ts(1), cp="C1"),
         trade("t3", "o3", "C1", "SELL", 10, 100, ts(3), cp="C2"),
         trade("t4", "o4", "C2", "BUY", 10, 100, ts(3), cp="C1"),
         trade("t5", "o5", "C3", "BUY", 10, 100, ts(4), cp="EXT")],
    )
    run_family(con, "05_")
    r1 = row(con, "feat_linked_accounts", "C1")
    assert r1["n_linked_accounts"] == 1
    assert r1["linked_cp_trades"] == 2
    assert r1["linked_cp_share"] == pytest.approx(1.0)
    assert r1["self_cp_trades"] == 0
    assert r1["linked_same_symbol_today"] == 1
    r3 = row(con, "feat_linked_accounts", "C3")
    assert r3["linked_cp_trades"] == 0 and r3["n_linked_accounts"] == 0


def test_book_imbalance_spoof_sequence():
    t0 = ts(30)
    s = timedelta(seconds=1)
    con = build_db(
        [client("C1")],
        [order("o1", "C1", "BUY", 1000, 99.9, t0, status="CANCELLED", end=t0 + 25 * s),
         order("o2", "C1", "BUY", 1000, 99.8, t0 + s, status="CANCELLED", end=t0 + 26 * s),
         order("o3", "C1", "SELL", 100, 100.1, t0 + 19 * s)],
        [trade("t1", "o3", "C1", "SELL", 100, 100.1, t0 + 20 * s)],
    )
    run_family(con, "06_")
    r = row(con, "feat_book_imbalance", "C1")
    assert r["spoof_sequences"] == 1
    assert r["max_layer_levels"] == 2
    # placed: (2000 - 100) / 2100 ; filled: -1  -> gap = 1900/2100 + 1
    assert r["placed_vs_filled_imbalance_gap"] == pytest.approx(1900 / 2100 + 1)


def test_price_impact_and_dealer_flow():
    bars = flat_bars(price=100.0, jump_at=31, jump_to=101.0)  # mid steps up at 09:46
    con = build_db(
        [client("C1", dealer="D01"), client("INST", ctype="INSTITUTIONAL", dealer="D01")],
        [order("o1", "C1", "BUY", 10, 100.0, ts(30), trader="D01"),
         order("o2", "INST", "BUY", 1000, 100.5, ts(35), trader="D01")],
        [trade("t1", "o1", "C1", "BUY", 10, 100.0, ts(30)),
         trade("t2", "o2", "INST", "BUY", 1000, 100.5, ts(35))],
        bars,
    )
    run_family(con, "07_")
    r = row(con, "feat_price_impact", "C1")
    assert r["post_trade_drift_2m_bps"] == pytest.approx(100.0)  # 100 -> 101
    assert r["pre_trade_drift_2m_bps"] == pytest.approx(0.0)
    assert r["trades_ahead_of_dealer_flow"] == 1
    inst = row(con, "feat_price_impact", "INST")
    assert inst["trades_ahead_of_dealer_flow"] == 0


def test_full_build_and_fixed_rules():
    t = [ts(i) for i in range(10)]
    clients = [client("C1", email="x"), client("C2", email="x")]
    orders, trades = [], []
    # Six balanced trades by C1 against linked C2 -> wash rule and linked self-trade rule.
    for i in range(6):
        side = "BUY" if i % 2 == 0 else "SELL"
        orders.append(order(f"o{i}", "C1", side, 10, 100, t[i]))
        trades.append(trade(f"t{i}", f"o{i}", "C1", side, 10, 100, t[i], cp="C2"))
    con = build_db(clients, orders, trades)
    build_features(con)
    build_rules(con)
    cols = {r[0] for r in con.execute("DESCRIBE features").fetchall()}
    assert set(FEATURE_COLUMNS) <= cols
    r = con.execute("SELECT * FROM rule_hits WHERE client_id = 'C1'").df().iloc[0]
    assert bool(r["self_trade_hit"]) and bool(r["wash_trade_hit"]) and not bool(r["high_frequency_hit"])
    assert r["rule_score"] == pytest.approx(100.0)
    assert "SELF_TRADE" in r["rules_fired"] and "WASH_TRADE" in r["rules_fired"]
