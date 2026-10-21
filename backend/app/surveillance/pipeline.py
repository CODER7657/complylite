"""End-to-end evaluation: features, rules, models, metrics, and the scored alert queue.

``run_evaluation`` is what ``scripts/run_eval.py`` and the CI smoke test call. It trains on the
earliest days, tunes early stopping and the blend weight on the next block, and scores the
holdout block once. It writes the ranked queue (``alert_scores``) and a small history of past
decisions (``past_cases``, training days only) back into ``market.duckdb`` for the API and the
case-note agent. Labels never go into ``market.duckdb`` except for those training-day past
cases, which stand in for alerts an analyst already closed.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from app.surveillance.evidence import evidence_level, red_flags
from app.surveillance.features import FEATURE_COLUMNS, build_features, build_rules, load_matrix
from app.surveillance.metrics import method_report, oracle_precision, queue_report, rules_workload
from app.surveillance.modeling import (
    attach_labels, rules_score, split_by_day, top_contributions, train_models,
)
from app.surveillance.paths import LABELS_DB, MARKET_DB
from app.surveillance.simulator import PATTERNS

METHODS = ("rules", "isolation_forest", "gbm", "rules_plus_gbm")


def alert_id(row) -> str:
    return f"{row['trade_date'].strftime('%Y%m%d')}-{row['client_id']}-{row['symbol']}"


def _scores(models, df: pd.DataFrame) -> dict[str, np.ndarray]:
    g = models.score_gbm(df)
    return {
        "rules": rules_score(df),
        "isolation_forest": models.score_if(df),
        "gbm": g,
        "rules_plus_gbm": models.score_blend(df, g),
    }


def _oracle_fa(part: pd.DataFrame, caps: dict, n_trades: int) -> float:
    pos = part.groupby("trade_date")["y"].sum()
    fp = sum(max(0, c - int(pos.get(d, 0))) for d, c in caps.items())
    return fp / max(1, n_trades) * 1e4


def _leave_one_pattern_out(train, val, test, n_trades_test, k) -> dict:
    """Retrain the GBM with one pattern removed from training and validation entirely, then see
    whether the holdout queue still catches it. This is the 'new kind of manipulation' case."""
    out = {}
    for p in PATTERNS:
        if (test["pattern"] == p).sum() == 0:
            continue
        tr = train[train["pattern"] != p]
        va = val[val["pattern"] != p]
        m = train_models(tr, va, k)
        g = m.score_gbm(test)
        rep = queue_report(test, g, k, n_trades_test)
        sel = (test["pattern"] == p) | (test["y"] == 0)
        out[p] = {
            "recall_in_queue": rep["recall_by_pattern"].get(p, 0.0),
            "pr_auc_this_pattern": round(float(average_precision_score(test.loc[sel, "y"], g[sel.to_numpy()])), 4),
        }
    return out


def run_evaluation(dataset_dir: str | Path, k: int = 50, holdout: bool = True, rebuild: bool = True,
                   lopo: bool = True, write_queue: bool = True) -> dict:
    t_start = time.perf_counter()
    ds = Path(dataset_dir)
    con = duckdb.connect(str(ds / MARKET_DB))
    try:
        if rebuild or not con.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'features'").fetchone()[0]:
            build_features(con)
            build_rules(con)
        df = load_matrix(con)
        n_trades_by_day = con.execute(
            "SELECT CAST(timestamp AS DATE) AS d, COUNT(*) AS n FROM trades GROUP BY ALL").df()
        meta = json.loads(con.execute("SELECT value FROM dataset_meta WHERE key = 'meta'").fetchone()[0])
    finally:
        con.close()
    t_features = time.perf_counter() - t_start

    df = attach_labels(df, ds / LABELS_DB)
    df["split"] = split_by_day(df["trade_date"])
    n_trades_by_day["d"] = pd.to_datetime(n_trades_by_day["d"]).dt.date
    split_of_day = df.drop_duplicates("trade_date").set_index("trade_date")["split"]
    n_trades_by_day["split"] = n_trades_by_day["d"].map(split_of_day)
    trades_in = n_trades_by_day.groupby("split")["n"].sum().to_dict()

    train, val, test = (df[df["split"] == s] for s in ("train", "val", "test"))
    t0 = time.perf_counter()
    models = train_models(train, val, k)
    t_train = time.perf_counter() - t0

    def evaluate(part: pd.DataFrame, name: str) -> dict:
        sc = _scores(models, part)
        n_tr = int(trades_in.get(name, 0))
        caps = rules_workload(part, sc["rules"], k)
        res = {
            "days": int(part["trade_date"].nunique()),
            "units": int(len(part)),
            "positive_units": int(part["y"].sum()),
            "positives_by_pattern": {p: int((part["pattern"] == p).sum()) for p in PATTERNS},
            "trades": n_tr,
            "oracle_precision_at_k": round(oracle_precision(part, k), 4),
            "rules_workload_per_day": round(sum(caps.values()) / max(1, len(caps)), 1),
            "methods": {m: method_report(part, sc[m], n_tr, k, rules_only=(m == "rules"), caps=caps)
                        for m in METHODS},
            "rules_as_fired": queue_report(part, sc["rules"], None, n_tr),
            "oracle_same_workload_fa_10k": round(_oracle_fa(part, caps, n_tr), 1),
        }
        return res

    report = {
        "dataset": {"dir": str(ds), "seed": meta["seed"], "generator_version": meta["generator_version"],
                    "summary": meta["summary"], "config": meta["config"]},
        "split": {s: sorted({d.isoformat() for d in df.loc[df["split"] == s, "trade_date"]}) for s in
                  ("train", "val", "test")},
        "k_per_day": k,
        "model": {"gbm_best_iteration": models.best_iteration, "blend_weight_on_rules": models.blend_w,
                  "n_features": len(FEATURE_COLUMNS)},
        "validation": evaluate(val, "val"),
    }
    if holdout:
        report["holdout"] = evaluate(test, "test")
        if lopo:
            report["holdout"]["leave_one_pattern_out"] = _leave_one_pattern_out(
                train, val, test, int(trades_in.get("test", 0)), k)

    imp = pd.Series(models.gbm.booster_.feature_importance("gain"), index=FEATURE_COLUMNS)
    contrib = np.abs(models.contributions(df[df["split"] != "train"])[:, :-1]).mean(axis=0)
    report["feature_importance"] = {
        "mean_abs_shap": dict(sorted(((f, round(float(v), 4)) for f, v in zip(FEATURE_COLUMNS, contrib)),
                                     key=lambda x: -x[1])),
        "gain_share": {f: round(float(v), 4) for f, v in (imp / imp.sum()).sort_values(ascending=False).items()},
    }

    if write_queue:
        _write_queue(ds, df, models, k)
        models.save(ds / "models")
    report["timing_seconds"] = {"features_and_rules": round(t_features, 1), "training": round(t_train, 1),
                                "total": round(time.perf_counter() - t_start, 1)}
    report["_frame"] = df  # for charts; dropped before JSON
    report["_scores"] = {s: _scores(models, part) for s, part in (("val", val), ("test", test))}
    return report


def _write_queue(ds: Path, df: pd.DataFrame, models, k: int) -> None:
    sc = _scores(models, df)
    out = df[["client_id", "symbol", "trade_date", "split", "rule_score", "rules_fired"]].copy()
    out["rules_score"] = sc["rules"]
    out["if_score"] = sc["isolation_forest"]
    out["gbm_score"] = sc["gbm"]
    out["final_score"] = sc["rules_plus_gbm"]
    out["alert_id"] = out.apply(alert_id, axis=1)
    out["daily_rank"] = out.groupby("trade_date")["final_score"].rank(ascending=False, method="first").astype(int)
    out["in_queue"] = out["daily_rank"] <= k
    reasons = top_contributions(models, df)
    out["top_reasons"] = [json.dumps(r) for r in reasons]
    rows = df[FEATURE_COLUMNS].to_dict("records")
    flags = [red_flags(r) for r in rows]
    out["red_flags"] = [json.dumps(f) for f in flags]
    out["evidence_level"] = [evidence_level(len(f), float(g)) for f, g in zip(flags, sc["gbm"])]

    hist = df[(df["split"] == "train")].copy()
    hist["gbm_score"] = sc["gbm"][(df["split"] == "train").to_numpy()]
    hist["daily_rank"] = hist.groupby("trade_date")["gbm_score"].rank(ascending=False, method="first")
    past = hist[hist["daily_rank"] <= k].copy()
    past["outcome"] = np.where(past["y"] == 1, "ESCALATED", "DISMISSED")
    past["pattern"] = np.where(past["y"] == 1, past["pattern"], None)
    past["alert_id"] = past.apply(alert_id, axis=1)
    past = past[["alert_id", "client_id", "symbol", "trade_date", "outcome", "pattern"] + FEATURE_COLUMNS]

    con = duckdb.connect(str(ds / MARKET_DB))
    try:
        cols = ["alert_id", "client_id", "symbol", "trade_date", "split", "daily_rank", "in_queue", "final_score",
                "gbm_score", "if_score", "rules_score", "rule_score", "rules_fired", "evidence_level", "red_flags",
                "top_reasons"]
        con.register("_q", out[cols])
        con.execute("CREATE OR REPLACE TABLE alert_scores AS SELECT * FROM _q")
        con.unregister("_q")
        con.register("_p", past)
        con.execute("CREATE OR REPLACE TABLE past_cases AS SELECT * FROM _p")
        con.unregister("_p")
    finally:
        con.close()
