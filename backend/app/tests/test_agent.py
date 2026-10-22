"""Offline tests for the case-note agent and its API. The language model is always the stub."""
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import surveillance
from app.surveillance.agent.case_note import alert_context, draft_case_note, template_note
from app.surveillance.agent.checker import check_note
from app.surveillance.agent.llm import StubLLM
from app.surveillance.agent.sql_guard import SqlGuardError, check_select
from app.surveillance.agent.tools import ReadOnlyTools
from app.surveillance.pipeline import run_evaluation
from app.surveillance.simulator import make_config, simulate


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    out = tmp_path_factory.mktemp("agent_sim")
    simulate(make_config("tiny", seed=3)).write(out)
    run_evaluation(out, k=50, holdout=True, lopo=False)
    return out


@pytest.fixture
def tools(dataset):
    t = ReadOnlyTools(dataset)
    yield t
    t.close()


def top_alert(tools):
    return tools.con.execute(
        "SELECT alert_id FROM alert_scores WHERE split = 'test' ORDER BY trade_date, daily_rank LIMIT 1").fetchone()[0]


@pytest.mark.parametrize("sql", [
    "DROP TABLE trades", "SELECT 1; DELETE FROM trades", "COPY trades TO 'x.csv'", "INSERT INTO trades VALUES (1)",
    "SELECT * FROM read_csv('a.csv')", "SELECT * FROM 'data.parquet'", "ATTACH 'x.db'", "PRAGMA database_list",
])
def test_sql_guard_rejects_writes_and_file_access(sql):
    with pytest.raises(SqlGuardError):
        check_select(sql)


def test_sql_guard_allows_select_and_ignores_keywords_in_strings():
    assert check_select("SELECT COUNT(*) FROM trades WHERE side = 'DELETE'")
    assert check_select("WITH a AS (SELECT 1) SELECT * FROM a")


def test_tools_are_read_only_and_row_limited(tools):
    assert "rejected" in tools.sql_query("DELETE FROM trades")
    out = tools.sql_query("SELECT * FROM generate_series(1, 5000)")
    assert '"truncated":true' in out and '"row_count":200' in out
    with pytest.raises(Exception):
        tools.con.execute("CREATE TABLE x AS SELECT 1")


def test_checker_accepts_stub_and_rejects_invented_trade(tools):
    aid = top_alert(tools)
    good = draft_case_note(aid, tools, StubLLM())
    assert good.source == "llm_first_try" and good.checks[0]["passed"]
    ctx = alert_context(tools, aid)
    bad = {"headline": "x", "rationale": "y", "conclusion": "REVIEW_FURTHER",
           "findings": [{"text": "t", "trade_ids": ["T99999999"], "facts": []}]}
    res = check_note(bad, ctx, tools.con, [])
    assert not res.passed and any("does not exist" in f for f in res.failures)


def test_checker_catches_wrong_numbers_and_overclaiming(tools):
    aid = top_alert(tools)
    ctx = alert_context(tools, aid)
    ids = [r[0] for r in tools.con.execute(
        "SELECT trade_id FROM trades WHERE client_id = ? AND symbol = ? AND CAST(timestamp AS DATE) = CAST(? AS DATE)",
        [ctx["client_id"], ctx["symbol"], ctx["trade_date"]]).fetchall()]
    assert ids
    note = {"headline": "h", "rationale": "This proves intentional manipulation of 123456 shares.",
            "conclusion": "REVIEW_FURTHER",
            "findings": [{"text": "t", "trade_ids": ids, "facts": [{"metric": "trade_count", "value": len(ids) + 1}]}]}
    fails = " | ".join(check_note(note, ctx, tools.con, []).failures)
    assert "trade_count" in fails and "claims more than" in fails and "123456" in fails


def test_retry_recovers_a_bad_first_draft(tools):
    res = draft_case_note(top_alert(tools), tools, StubLLM(mistakes=1))
    assert res.source == "llm_after_retry"
    assert [c["passed"] for c in res.checks] == [False, True]


def test_template_fallback_when_there_is_no_model_and_it_passes_the_checker(tools):
    aid = top_alert(tools)
    res = draft_case_note(aid, tools, None)
    assert res.source == "template" and res.checks[-1]["passed"]
    ctx = alert_context(tools, aid)
    assert check_note(template_note(ctx, tools), ctx, tools.con, tools.ledger).passed


class BrokenLLM:
    name = "broken"

    def chat(self, messages, tools):
        raise RuntimeError("network down")


def test_api_failure_falls_back_to_template(tools):
    res = draft_case_note(top_alert(tools), tools, BrokenLLM())
    assert res.source == "template" and "network down" in res.error


@pytest.fixture
def client(dataset):
    app = FastAPI()
    app.include_router(surveillance.router, prefix="/api/v1/surveillance")
    app.dependency_overrides[surveillance.get_dataset] = lambda: dataset
    app.dependency_overrides[surveillance.get_llm] = lambda: StubLLM()
    return TestClient(app)


def test_queue_endpoint_is_ranked(client):
    r = client.get("/api/v1/surveillance/queue", params={"limit": 10})
    assert r.status_code == 200
    body = r.json()
    ranks = [a["rank"] for a in body["alerts"]]
    assert body["simulated_data"] is True and ranks == sorted(ranks) and ranks[0] == 1
    assert {"alert_id", "score", "evidence_level", "red_flags", "top_reasons"} <= set(body["alerts"][0])


def test_note_endpoint_cites_trades(client):
    alert_id = client.get("/api/v1/surveillance/queue").json()["alerts"][0]["alert_id"]
    r = client.get(f"/api/v1/surveillance/alerts/{alert_id}/note")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "llm_first_try" and body["checks"][0]["passed"]
    assert all(f["trade_ids"] for f in body["note"]["findings"])


def test_note_endpoint_unknown_alert_is_404(client):
    assert client.get("/api/v1/surveillance/alerts/nope/note").status_code == 404


def test_groq_client_gives_up_fast_on_a_daily_quota_and_retries_a_short_limit():
    import httpx

    from app.surveillance.agent.llm import GroqClient

    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "0.01"}, json={"error": {"message": "burst"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}], "usage": {"total_tokens": 5}})

    c = GroqClient(api_key="test-key")
    c._http = httpx.Client(transport=httpx.MockTransport(handler))
    assert c.chat([{"role": "user", "content": "hi"}], None)["content"] == "ok" and calls["n"] == 2

    c._http = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(429, headers={"retry-after": "3000"}, json={"error": {"message": "day"}})))
    with pytest.raises(RuntimeError, match="quota"):
        c.chat([{"role": "user", "content": "hi"}], None)


def test_groq_client_retries_without_tools_when_the_model_invents_one():
    import httpx

    from app.surveillance.agent.llm import GroqClient

    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if "tools" in body:
            msg = "Tool call validation failed: attempted to call tool 'json' which was not in request.tools"
            return httpx.Response(400, json={"error": {"message": msg}})
        reply = {"choices": [{"message": {"content": "{\"ok\": true}"}}], "usage": {"total_tokens": 10}}
        return httpx.Response(200, json=reply)

    client = GroqClient(api_key="test-not-real")
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    out = client.chat([{"role": "user", "content": "hi"}], [{"type": "function", "function": {"name": "sql_query"}}])
    assert out["content"] == "{\"ok\": true}"
    assert "tools" in bodies[0] and "tools" not in bodies[1]
    assert client.usage["invented_tool_retries"] == 1
