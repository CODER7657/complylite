"""Filesystem locations used by the surveillance pipeline."""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SQL_DIR = Path(__file__).resolve().parent / "sql"
DEFAULT_DATASET_DIR = REPO_ROOT / "data" / "sim" / "default"
REPORTS_DIR = REPO_ROOT / "reports"

MARKET_DB = "market.duckdb"
LABELS_DB = "labels.duckdb"


def dataset_dir() -> Path:
    """Dataset used by the API. Override with COMPLYLITE_SURVEILLANCE_DIR."""
    env = os.environ.get("COMPLYLITE_SURVEILLANCE_DIR")
    return Path(env) if env else DEFAULT_DATASET_DIR
