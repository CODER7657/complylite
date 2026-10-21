"""Models for ranking review units: rules, IsolationForest, gradient boosting, and a blend.

Everything is split by trading day, never at random: the earliest days train, the next block
is for early stopping and the blend weight, and the last block is the holdout.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import duckdb
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score

from app.surveillance.features import FEATURE_COLUMNS, KEYS
from app.surveillance.paths import LABELS_DB

SEED = 7
GBM_PARAMS = dict(
    n_estimators=600, learning_rate=0.05, num_leaves=15, min_child_samples=20, subsample=0.8,
    subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, n_jobs=2, verbose=-1, random_state=SEED,
    deterministic=True, force_col_wise=True,
)
BLEND_GRID = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]


def attach_labels(df: pd.DataFrame, labels_path: str | Path) -> pd.DataFrame:
    """Add y (1 = unit touched by an injected manipulation), pattern and hard-negative scenario."""
    con = duckdb.connect(str(labels_path), read_only=True)
    try:
        eu = con.execute(
            "SELECT client_id, symbol, CAST(trade_date AS DATE) AS trade_date, MIN(pattern) AS pattern "
            "FROM event_units GROUP BY ALL"
        ).df()
        su = con.execute(
            "SELECT client_id, symbol, CAST(trade_date AS DATE) AS trade_date, MIN(scenario) AS scenario "
            "FROM scenario_units GROUP BY ALL"
        ).df()
    finally:
        con.close()
    for x in (eu, su):
        x["trade_date"] = pd.to_datetime(x["trade_date"]).dt.date
    out = df.merge(eu, on=KEYS, how="left").merge(su, on=KEYS, how="left")
    out["y"] = out["pattern"].notna().astype(int)
    out["pattern"] = out["pattern"].fillna("none")
    out["scenario"] = out["scenario"].fillna("none")
    return out


def default_labels_path(dataset_dir: str | Path) -> Path:
    return Path(dataset_dir) / LABELS_DB


def split_by_day(dates: pd.Series, train_frac: float = 0.6, val_frac: float = 0.15) -> pd.Series:
    days = sorted(pd.unique(dates))
    n = len(days)
    n_tr = max(1, int(round(n * train_frac)))
    n_va = max(1, int(round(n * val_frac)))
    tr, va = set(days[:n_tr]), set(days[n_tr:n_tr + n_va])
    return dates.map(lambda d: "train" if d in tr else ("val" if d in va else "test"))


def matrix(df: pd.DataFrame) -> pd.DataFrame:
    return df[FEATURE_COLUMNS].astype(float)


def rules_score(df: pd.DataFrame) -> np.ndarray:
    """Rules-only ranking: the rule risk score, then the number of rules fired, then a seeded
    tie-break (the original app showed alerts in arrival order, which is arbitrary too)."""
    n_fired = df[["self_trade_hit", "wash_trade_hit", "high_frequency_hit"]].astype(int).sum(axis=1).to_numpy()
    jitter = np.random.default_rng(SEED).random(len(df)) * 0.01
    s = df["rule_score"].to_numpy(dtype=float) + n_fired + jitter
    return np.where(df["rule_score"].to_numpy() > 0, s, 0.0)


def _if_transform(X: pd.DataFrame, med: pd.Series) -> np.ndarray:
    Z = X.fillna(med)
    return np.sign(Z) * np.log1p(np.abs(Z))


@dataclass
class TrainedModels:
    gbm: lgb.LGBMClassifier
    iforest: IsolationForest
    if_median: pd.Series
    blend_w: float
    best_iteration: int

    def score_gbm(self, df: pd.DataFrame) -> np.ndarray:
        return self.gbm.predict_proba(matrix(df), num_iteration=self.best_iteration)[:, 1]

    def score_if(self, df: pd.DataFrame) -> np.ndarray:
        return -self.iforest.score_samples(_if_transform(matrix(df), self.if_median))

    def score_blend(self, df: pd.DataFrame, gbm: np.ndarray | None = None) -> np.ndarray:
        g = self.score_gbm(df) if gbm is None else gbm
        return self.blend_w * df["rule_score"].to_numpy(dtype=float) / 100.0 + (1 - self.blend_w) * g

    def contributions(self, df: pd.DataFrame) -> np.ndarray:
        """Per-feature SHAP contributions (log-odds) from LightGBM; last column is the bias."""
        return self.gbm.booster_.predict(matrix(df), num_iteration=self.best_iteration, pred_contrib=True)

    def save(self, out_dir: str | Path) -> None:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        self.gbm.booster_.save_model(str(out / "gbm.txt"), num_iteration=self.best_iteration)
        (out / "model_meta.json").write_text(json.dumps({
            "features": FEATURE_COLUMNS, "blend_w": self.blend_w, "best_iteration": self.best_iteration,
            "gbm_params": {k: v for k, v in GBM_PARAMS.items()},
        }, indent=2), encoding="utf-8")


def train_models(train: pd.DataFrame, val: pd.DataFrame, k_per_day: int = 50) -> TrainedModels:
    from app.surveillance.metrics import daily_queue_precision

    gbm = lgb.LGBMClassifier(**GBM_PARAMS)
    gbm.fit(matrix(train), train["y"], eval_X=(matrix(val),), eval_y=(val["y"],), eval_metric="average_precision",
            callbacks=[lgb.early_stopping(50, verbose=False)])
    best = int(gbm.best_iteration_ or GBM_PARAMS["n_estimators"])
    med = matrix(train).median()
    iforest = IsolationForest(n_estimators=200, random_state=SEED, n_jobs=2)
    iforest.fit(_if_transform(matrix(train), med))
    models = TrainedModels(gbm=gbm, iforest=iforest, if_median=med, blend_w=0.0, best_iteration=best)

    # Blend weight: chosen on validation days only, by daily precision@k, PR-AUC as tie-break.
    g_val = models.score_gbm(val)
    best_key, best_w = None, 0.0
    for w in BLEND_GRID:
        s = w * val["rule_score"].to_numpy(dtype=float) / 100.0 + (1 - w) * g_val
        key = (round(daily_queue_precision(val, s, k_per_day), 4), round(average_precision_score(val["y"], s), 4))
        if best_key is None or key > best_key:
            best_key, best_w = key, w
    models.blend_w = best_w
    return models


def top_contributions(models: TrainedModels, df: pd.DataFrame, k: int = 3) -> list[list[dict]]:
    contrib = models.contributions(df)[:, :-1]
    X = matrix(df).to_numpy()
    out = []
    for i in range(len(df)):
        idx = np.argsort(-contrib[i])[:k]
        out.append([
            {"feature": FEATURE_COLUMNS[j], "value": None if np.isnan(X[i, j]) else round(float(X[i, j]), 4),
             "contribution": round(float(contrib[i, j]), 4)}
            for j in idx if contrib[i, j] > 0
        ])
    return out
