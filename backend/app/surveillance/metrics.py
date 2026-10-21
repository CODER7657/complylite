"""Queue-based metrics. The analyst reviews about 50 alerts a day, so most metrics are measured
on a daily queue: each day, the top-k units by score (only units with a positive score count
for the rules, since a rule that did not fire produces no alert)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from app.surveillance.simulator import PATTERNS


def daily_queue_mask(df: pd.DataFrame, score: np.ndarray, k: int | None, require_positive: bool = False,
                     caps: dict | None = None) -> np.ndarray:
    """Boolean mask of units that make the daily queue. k=None means every unit with score > 0.
    caps optionally gives a per-day queue length that overrides k."""
    s = pd.Series(np.asarray(score, dtype=float), index=df.index)
    eligible = s > 0 if (require_positive or k is None) else pd.Series(True, index=df.index)
    mask = pd.Series(False, index=df.index)
    for day, idx in df.groupby("trade_date").groups.items():
        cand = s.loc[idx][eligible.loc[idx]]
        cap = caps.get(day, 0) if caps is not None else k
        if cap is not None:
            cand = cand.sort_values(ascending=False, kind="stable").head(cap)
        mask.loc[cand.index] = True
    return mask.to_numpy()


def daily_queue_precision(df: pd.DataFrame, score: np.ndarray, k: int, require_positive: bool = False) -> float:
    """Mean over days of (true alerts in the day's queue) / k. Empty slots count as misses."""
    mask = daily_queue_mask(df, score, k, require_positive)
    hits = pd.Series(mask & (df["y"].to_numpy() == 1), index=df.index).groupby(df["trade_date"]).sum()
    return float((hits / k).mean())


def queue_report(df: pd.DataFrame, score: np.ndarray, k: int | None, n_trades: int,
                 require_positive: bool = False, caps: dict | None = None) -> dict:
    y = df["y"].to_numpy()
    mask = daily_queue_mask(df, score, k, require_positive, caps)
    n_days = df["trade_date"].nunique()
    queued = int(mask.sum())
    tp = int((mask & (y == 1)).sum())
    fp = queued - tp
    rep = {
        "alerts_per_day": round(queued / n_days, 1),
        "precision": round(tp / queued, 4) if queued else 0.0,
        "recall": round(tp / max(1, int(y.sum())), 4),
        "false_alarms_per_10k_trades": round(fp / max(1, n_trades) * 1e4, 1),
        "recall_by_pattern": {},
        "false_alarm_share_by_scenario": {},
    }
    if k is not None and caps is None:
        rep["precision_at_k_daily"] = round(daily_queue_precision(df, score, k, require_positive), 4)
    for p in PATTERNS:
        sel = df["pattern"].to_numpy() == p
        if sel.sum():
            rep["recall_by_pattern"][p] = round(float((mask & sel).sum() / sel.sum()), 4)
    if fp:
        neg_q = df.loc[mask & (y == 0), "scenario"].value_counts()
        rep["false_alarm_share_by_scenario"] = {str(k_): round(int(v) / fp, 4) for k_, v in neg_q.items()}
    return rep


def rules_workload(df: pd.DataFrame, rules_score: np.ndarray, k: int) -> dict:
    """Per-day alert count the fixed rules raise, capped at the analyst's capacity k."""
    fired = pd.Series(np.asarray(rules_score) > 0, index=df.index).groupby(df["trade_date"]).sum()
    return {d: int(min(k, n)) for d, n in fired.items()}


def method_report(df: pd.DataFrame, score: np.ndarray, n_trades: int, k: int = 50,
                  rules_only: bool = False, caps: dict | None = None) -> dict:
    """PR-AUC; the full daily top-k queue; and, if caps is given, the same-workload queue where every
    method raises exactly as many alerts per day as the rules did (capped at k)."""
    out = {
        "pr_auc": round(float(average_precision_score(df["y"], score)), 4),
        "queue": queue_report(df, score, k, n_trades, require_positive=rules_only),
    }
    if caps is not None:
        out["same_workload_as_rules"] = queue_report(df, score, k, n_trades, require_positive=rules_only, caps=caps)
    return out


def oracle_precision(df: pd.DataFrame, k: int) -> float:
    """Best possible daily precision@k given how many true units each day has."""
    pos = df.groupby("trade_date")["y"].sum()
    return float((pos.clip(upper=k) / k).mean())
