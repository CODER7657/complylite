"""Ranked alert queue and case notes for the simulated surveillance dataset.

Read-only. The dataset is whatever ``COMPLYLITE_SURVEILLANCE_DIR`` points at (default
``data/sim/default``) after ``scripts/run_eval.py`` has written the ranked queue into it.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query

from app.surveillance.agent.case_note import draft_case_note
from app.surveillance.agent.llm import ChatClient, GroqClient, load_api_key
from app.surveillance.agent.tools import ReadOnlyTools, open_readonly
from app.surveillance.paths import MARKET_DB, dataset_dir

router = APIRouter()


def get_dataset() -> Path:
    return dataset_dir()


def get_llm() -> ChatClient | None:
    """Groq when a key is configured, else None, which makes case notes use the SQL-only template."""
    return GroqClient() if load_api_key() else None


def _db(ds: Path) -> Path:
    db = ds / MARKET_DB
    if not db.exists():
        raise HTTPException(503, "No surveillance dataset found. Run scripts/simulate.py and scripts/run_eval.py.")
    return db


@router.get("/queue")
def ranked_queue(trade_date: str | None = Query(None, description="YYYY-MM-DD; default is the latest holdout day"),
                 limit: int = Query(50, ge=1, le=200), ds: Path = Depends(get_dataset)):
    con = open_readonly(_db(ds))
    try:
        try:
            if trade_date is None:
                trade_date = str(con.execute(
                    "SELECT MAX(trade_date) FROM alert_scores WHERE split = 'test'").fetchone()[0])[:10]
            rows = con.execute(
                "SELECT alert_id, daily_rank, client_id, symbol, CAST(trade_date AS VARCHAR), final_score, "
                "rules_fired, evidence_level, red_flags, top_reasons FROM alert_scores "
                "WHERE trade_date = CAST(? AS DATE) AND in_queue ORDER BY daily_rank LIMIT ?",
                [trade_date, limit]).fetchall()
        except duckdb.Error as e:
            raise HTTPException(400, f"cannot read the alert queue: {str(e).splitlines()[0]}") from e
    finally:
        con.close()
    return {
        "trade_date": trade_date,
        "simulated_data": True,
        "alerts": [{"alert_id": r[0], "rank": r[1], "client_id": r[2], "symbol": r[3], "trade_date": r[4],
                    "score": round(float(r[5]), 4), "rules_fired": r[6] or None, "evidence_level": r[7],
                    "red_flags": json.loads(r[8]), "top_reasons": json.loads(r[9])} for r in rows],
    }


@router.get("/alerts/{alert_id}/note")
def case_note(alert_id: str, ds: Path = Depends(get_dataset), llm: ChatClient | None = Depends(get_llm)):
    tools = ReadOnlyTools(_db(ds))
    try:
        try:
            res = draft_case_note(alert_id, tools, llm)
        except KeyError as e:
            raise HTTPException(404, f"unknown alert {alert_id}") from e
    finally:
        tools.close()
    return res.as_dict()
