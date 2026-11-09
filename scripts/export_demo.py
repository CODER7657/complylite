"""Export the holdout ranked queue to demo/queue.json for the static demo page.

    python scripts/simulate.py && python scripts/run_eval.py && python scripts/export_demo.py

Reads alert_scores (written by run_eval) and the simulator's labels. Only the holdout
("test") days and only alerts that made the daily queue are exported. `pattern` is the
simulator's ground-truth label: shown so a visitor can see which queued alerts were real.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.surveillance.paths import LABELS_DB, MARKET_DB, dataset_dir  # noqa: E402


def export(ds: Path) -> dict:
    con = duckdb.connect(str(ds / MARKET_DB), read_only=True)
    try:
        con.execute(f"ATTACH '{(ds / LABELS_DB).as_posix()}' AS lab (READ_ONLY)")
        rows = con.execute("""
            SELECT a.trade_date, a.daily_rank, a.client_id, a.symbol, a.final_score, a.rules_fired,
                   a.evidence_level, a.red_flags, a.top_reasons, l.pattern
            FROM alert_scores a
            LEFT JOIN (SELECT client_id, symbol, CAST(trade_date AS DATE) d, MIN(pattern) pattern
                       FROM lab.event_units GROUP BY ALL) l
              ON l.client_id = a.client_id AND l.symbol = a.symbol AND l.d = a.trade_date
            WHERE a.split = 'test' AND a.in_queue
            ORDER BY a.trade_date, a.daily_rank
        """).fetchall()
    finally:
        con.close()
    days: dict[str, list] = {}
    for d, rank, client, sym, score, fired, level, flags, reasons, pattern in rows:
        days.setdefault(d.isoformat(), []).append({
            "rank": int(rank), "client": client, "symbol": sym, "score": round(float(score), 4),
            "rules": [r for r in (fired or "").split(",") if r],
            "evidence": level, "flags": json.loads(flags or "[]"),
            "reasons": [{"feature": r["feature"], "contribution": round(r["contribution"], 3)}
                        for r in json.loads(reasons or "[]")],
            "pattern": pattern,
        })
    return {"simulated": True, "days": days}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=ROOT / "demo" / "queue.json")
    a = ap.parse_args(argv)
    doc = export(a.dataset or dataset_dir())
    a.out.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    n = sum(len(v) for v in doc["days"].values())
    real = sum(1 for v in doc["days"].values() for r in v if r["pattern"])
    print(f"{len(doc['days'])} days, {n} queued alerts ({real} planted patterns) -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
