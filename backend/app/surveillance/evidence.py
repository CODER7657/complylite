"""Deterministic red flags and evidence levels for a review unit.

These are plain thresholds written down before any model was trained. They are not the model;
they exist so that the case-note checker has a fixed, inspectable rule for how strong a
conclusion the evidence allows.
"""
from __future__ import annotations

import math
from typing import Any

CONCLUSIONS = ("ESCALATE", "REVIEW_FURTHER", "DISMISS")


def _v(row: dict, key: str) -> float:
    x = row.get(key)
    if x is None:
        return 0.0
    try:
        f = float(x)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(f) else f


def red_flags(row: dict[str, Any]) -> list[dict]:
    flags = []
    if _v(row, "linked_cp_trades") >= 2:
        flags.append({"flag": "linked_counterparty",
                      "text": f"{int(_v(row, 'linked_cp_trades'))} trades against itself or a linked account"})
    if _v(row, "max_trades_same_cp") >= 4 and _v(row, "top_cp_share") >= 0.5:
        flags.append({"flag": "repeated_internal_counterparty",
                      "text": f"{int(_v(row, 'max_trades_same_cp'))} trades against one internal counterparty"})
    if (_v(row, "n_round_trips") >= 2 and _v(row, "median_rt_qty_match") >= 0.95
            and row.get("median_rt_price_diff_bps") is not None and _v(row, "median_rt_price_diff_bps") <= 5):
        flags.append({"flag": "matched_round_trips",
                      "text": "repeated round trips of the same size at almost the same price"})
    if _v(row, "spoof_sequences") >= 1 and _v(row, "cancel_fill_size_ratio") >= 2:
        flags.append({"flag": "cancel_after_opposite_fill",
                      "text": f"{int(_v(row, 'spoof_sequences'))} fills bracketed by larger opposite orders "
                              "cancelled soon after"})
    if _v(row, "trades_ahead_of_dealer_flow") >= 1:
        flags.append({"flag": "ahead_of_dealer_flow",
                      "text": "traded just before larger same-side orders placed through the same dealer"})
    if _v(row, "ret_prior_3d_bps") >= 500 and abs(_v(row, "net_buy_share_3d")) >= 0.5:
        flags.append({"flag": "run_up_context",
                      "text": "one-sided trading during a 3-day price run-up of more than 5%"})
    return flags


def evidence_level(n_flags: int, model_score: float) -> str:
    if n_flags >= 2 or (n_flags >= 1 and model_score >= 0.8):
        return "strong"
    if n_flags >= 1 or model_score >= 0.5:
        return "moderate"
    return "weak"


ALLOWED = {
    "strong": {"ESCALATE", "REVIEW_FURTHER", "DISMISS"},
    "moderate": {"REVIEW_FURTHER", "DISMISS"},
    "weak": {"REVIEW_FURTHER", "DISMISS"},
}


def strongest_allowed(level: str) -> str:
    return "ESCALATE" if level == "strong" else "REVIEW_FURTHER"
