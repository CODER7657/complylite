"""scripts/export_demo.py: holdout queue only, labels joined, JSON shape the demo reads."""
import importlib.util
import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[3]


def _export():
    spec = importlib.util.spec_from_file_location("export_demo", ROOT / "scripts" / "export_demo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _dataset(tmp_path):
    m = duckdb.connect(str(tmp_path / "market.duckdb"))
    m.execute("""CREATE TABLE alert_scores AS SELECT * FROM (VALUES
      ('a1','C1','S1',DATE '2026-04-01','test',1,TRUE,0.99,'WASH_TRADE,SELF_TRADE','strong',
       '[{"flag":"linked_counterparty","text":"3 trades against itself"}]',
       '[{"feature":"max_trades_same_cp","value":3,"contribution":2.5}]'),
      ('a2','C2','S2',DATE '2026-04-01','test',2,TRUE,0.40,'','weak','[]','[]'),
      ('a3','C3','S3',DATE '2026-04-01','test',51,FALSE,0.10,'','weak','[]','[]'),
      ('a4','C1','S1',DATE '2026-03-01','train',1,TRUE,0.90,'','weak','[]','[]')
    ) t(alert_id,client_id,symbol,trade_date,split,daily_rank,in_queue,final_score,
        rules_fired,evidence_level,red_flags,top_reasons)""")
    m.close()
    lab = duckdb.connect(str(tmp_path / "labels.duckdb"))
    lab.execute("CREATE TABLE event_units AS SELECT * FROM (VALUES "
                "('C1','S1','2026-04-01',1,'wash_trade')) t(client_id,symbol,trade_date,event_id,pattern)")
    lab.close()
    return tmp_path


def test_exports_only_queued_holdout_alerts_with_labels(tmp_path):
    doc = _export().export(_dataset(tmp_path))
    assert doc["simulated"] is True
    assert list(doc["days"]) == ["2026-04-01"]  # the training day is excluded
    rows = doc["days"]["2026-04-01"]
    assert [r["rank"] for r in rows] == [1, 2]  # rank 51 did not make the queue
    first = rows[0]
    assert first["pattern"] == "wash_trade" and rows[1]["pattern"] is None
    assert first["rules"] == ["WASH_TRADE", "SELF_TRADE"] and rows[1]["rules"] == []
    assert first["flags"][0]["text"] == "3 trades against itself"
    assert first["reasons"] == [{"feature": "max_trades_same_cp", "contribution": 2.5}]


def test_main_writes_compact_json(tmp_path):
    out = tmp_path / "queue.json"
    assert _export().main(["--dataset", str(_dataset(tmp_path)), "--out", str(out)]) == 0
    assert json.loads(out.read_text())["days"]["2026-04-01"][0]["score"] == 0.99
