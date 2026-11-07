"""Property tests for alert scoring and daily-queue ranking.

Example-based tests pin known cases; these pin the invariants that must hold for
*any* input: scores are finite and bounded below by the rule score, the queue is a
stable top-k per day, and adding an alert never reorders the others.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from app.surveillance.metrics import daily_queue_mask
from app.surveillance.modeling import rules_score

SETTINGS = settings(max_examples=60, deadline=None)
DAY0 = date(2026, 3, 2)

row = st.fixed_dictionaries({
    "rule_score": st.one_of(st.just(0.0), st.floats(min_value=0, max_value=100, allow_nan=False)),
    "self_trade_hit": st.integers(0, 1),
    "wash_trade_hit": st.integers(0, 1),
    "high_frequency_hit": st.integers(0, 1),
})
rule_frames = st.lists(row, min_size=1, max_size=40).map(pd.DataFrame)

# Scores drawn from a small set so ties are common.
tied = st.sampled_from([0.0, 0.1, 0.5, 0.5, 0.9, 1.0])
queue_rows = st.lists(st.tuples(st.integers(0, 3), tied), min_size=1, max_size=40)


def queue_frame(rows: list[tuple[int, float]]) -> tuple[pd.DataFrame, np.ndarray]:
    df = pd.DataFrame({"trade_date": [DAY0 + timedelta(days=d) for d, _ in rows]})
    return df, np.array([s for _, s in rows], dtype=float)


# ------------------------------------------------------------------ rules_score

@SETTINGS
@given(rule_frames)
def test_rules_score_is_finite_nonnegative_and_not_below_rule_score(df):
    s = rules_score(df)
    assert s.shape == (len(df),)
    assert np.isfinite(s).all()
    assert (s >= 0).all()
    pos = df["rule_score"].to_numpy() > 0
    assert (s[pos] >= df["rule_score"].to_numpy()[pos]).all()


@SETTINGS
@given(rule_frames)
def test_rules_score_is_zero_exactly_when_no_rule_scored(df):
    s = rules_score(df)
    assert (s[df["rule_score"].to_numpy() <= 0] == 0).all()
    assert (s[df["rule_score"].to_numpy() > 0] > 0).all()


@SETTINGS
@given(rule_frames)
def test_rules_score_is_deterministic(df):
    assert np.array_equal(rules_score(df), rules_score(df.copy()))


@SETTINGS
@given(rule_frames, row)
def test_appending_an_alert_does_not_change_the_others(df, extra):
    before = rules_score(df)
    after = rules_score(pd.concat([df, pd.DataFrame([extra])], ignore_index=True))
    assert np.array_equal(before, after[: len(df)])
    # Same scores, so the relative order of the originals is unchanged too.
    assert list(np.argsort(-before, kind="stable")) == [
        i for i in np.argsort(-after, kind="stable") if i < len(df)
    ]


# --------------------------------------------------------------- daily_queue_mask

@SETTINGS
@given(queue_rows, st.integers(1, 6))
def test_queue_takes_at_most_k_per_day_and_the_highest_scores(rows, k):
    df, score = queue_frame(rows)
    mask = daily_queue_mask(df, score, k)
    for day in df["trade_date"].unique():
        idx = (df["trade_date"] == day).to_numpy()
        chosen, rest = score[idx & mask], score[idx & ~mask]
        assert len(chosen) == min(k, idx.sum())
        if len(rest):
            assert chosen.min() >= rest.max()


@SETTINGS
@given(queue_rows, st.integers(1, 6))
def test_queue_breaks_ties_by_original_order(rows, k):
    df, score = queue_frame(rows)
    mask = daily_queue_mask(df, score, k)
    for day in df["trade_date"].unique():
        idx = np.flatnonzero((df["trade_date"] == day).to_numpy())
        for value in set(score[idx]):
            tied_idx = [i for i in idx if score[i] == value]
            flags = [bool(mask[i]) for i in tied_idx]
            # Among equal scores the queue takes a prefix: no later row is in while an earlier one is out.
            assert flags == sorted(flags, reverse=True)


@SETTINGS
@given(queue_rows, st.integers(1, 6))
def test_queue_is_deterministic(rows, k):
    df, score = queue_frame(rows)
    assert np.array_equal(daily_queue_mask(df, score, k), daily_queue_mask(df.copy(), score.copy(), k))


@SETTINGS
@given(queue_rows, st.integers(1, 6), st.integers(0, 3), tied)
def test_adding_an_alert_never_promotes_another(rows, k, day, new_score):
    df, score = queue_frame(rows)
    before = daily_queue_mask(df, score, k)
    df2, score2 = queue_frame([*rows, (day, new_score)])
    after = daily_queue_mask(df2, score2, k)[: len(rows)]
    assert not (after & ~before).any()


@SETTINGS
@given(queue_rows)
def test_without_k_only_positive_scores_are_queued(rows):
    df, score = queue_frame(rows)
    assert np.array_equal(daily_queue_mask(df, score, None), score > 0)
