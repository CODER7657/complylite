import json

import duckdb
import pandas as pd
import pytest

from app.surveillance.modeling import split_by_day
from app.surveillance.pipeline import run_evaluation
from app.surveillance.simulator import PATTERNS, make_config, simulate


@pytest.fixture(scope="module")
def tiny_dataset(tmp_path_factory):
    out = tmp_path_factory.mktemp("sim")
    res = simulate(make_config("tiny", seed=3))
    res.write(out)
    return out, res


def test_simulator_is_deterministic():
    a = simulate(make_config("tiny", seed=11, n_days=3))
    b = simulate(make_config("tiny", seed=11, n_days=3))
    pd.testing.assert_frame_equal(a.orders, b.orders)
    pd.testing.assert_frame_equal(a.trades, b.trades)
    c = simulate(make_config("tiny", seed=12, n_days=3))
    assert len(c.orders) != len(a.orders) or not c.orders["price"].equals(a.orders["price"])


def test_dataset_has_labels_seed_and_no_leakage(tiny_dataset):
    out, res = tiny_dataset
    meta = json.loads((out / "config.json").read_text())
    assert meta["seed"] == 3 and meta["config"]["n_days"] == 8
    con = duckdb.connect(str(out / "market.duckdb"), read_only=True)
    try:
        cols = {r[0] for t in ("orders", "trades", "clients") for r in con.execute(f"DESCRIBE {t}").fetchall()}
    finally:
        con.close()
    assert not cols & {"event_id", "label", "pattern", "is_manipulation", "role"}
    assert set(res.event_units["pattern"]) <= set(PATTERNS)
    assert len(res.event_units) > 0 and len(res.scenario_units) > 0
    # every labeled order exists
    assert set(res.event_orders["order_id"]) <= set(res.orders["order_id"])
    # trades never happen before their order was placed
    m = res.trades.merge(res.orders[["order_id", "timestamp"]], on="order_id", suffixes=("", "_o"))
    assert (m["timestamp"] >= m["timestamp_o"]).all()


def test_split_is_by_day_and_ordered():
    days = pd.Series(pd.date_range("2026-01-01", periods=20).date)
    split = split_by_day(days)
    assert list(split[:12]) == ["train"] * 12
    assert days[split == "train"].max() < days[split == "val"].min() < days[split == "test"].min()


def test_evaluation_smoke(tiny_dataset):
    out, _ = tiny_dataset
    rep = run_evaluation(out, k=50, holdout=True, lopo=False)
    h = rep["holdout"]
    for m in ("rules", "isolation_forest", "gbm", "rules_plus_gbm"):
        assert 0.0 <= h["methods"][m]["pr_auc"] <= 1.0
        assert "same_workload_as_rules" in h["methods"][m]
    con = duckdb.connect(str(out / "market.duckdb"), read_only=True)
    try:
        q = con.execute("SELECT COUNT(*), SUM(in_queue::INT) FROM alert_scores").fetchone()
        pc_days = con.execute("SELECT MAX(trade_date) FROM past_cases").fetchone()[0]
        test_start = min(rep["split"]["test"])
    finally:
        con.close()
    assert q[0] > 0 and q[1] > 0
    assert str(pc_days) < test_start  # past cases come from training days only
