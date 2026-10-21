"""Draft a SEBI-style case note for one ranked alert.

Flow: build the alert context -> the planner calls read-only tools -> it returns a JSON note ->
the deterministic checker verifies it -> on failure, one retry with the checker's feedback ->
if that also fails, a templated note built only from SQL results.

The language model is allowed to choose queries and to write prose. It is not allowed to decide
what counts as a fact (the checker recomputes every figure), to touch anything but a read-only
connection, or to reach a conclusion stronger than the evidence level computed in code.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.surveillance.agent.checker import FACT_SQL, check_note, compute_facts
from app.surveillance.agent.llm import ChatClient
from app.surveillance.agent.tools import TOOL_SCHEMAS, ReadOnlyTools
from app.surveillance.evidence import ALLOWED, strongest_allowed
from app.surveillance.features import FEATURES

MAX_TOOL_ROUNDS = 8

SYSTEM_PROMPT = """You help a compliance analyst at a small Indian stock broker investigate one surveillance alert \
and draft a case note of the kind a broker keeps on file for SEBI and the exchanges.

Use the tools to look at the actual orders and trades before writing anything. Then reply with ONLY a JSON object:
{"headline": str,
 "findings": [{"text": str, "trade_ids": [str, ...], "facts": [{"metric": str, "value": number}]}],
 "conclusion": "ESCALATE" | "REVIEW_FURTHER" | "DISMISS",
 "rationale": str}

Rules the note is checked against by code:
- Every finding cites the trade IDs it is about. Only cite trades in the alert's symbol on the alert's day where \
the alert's client is buyer, seller or counterparty.
- facts are recomputed from that finding's cited trades. Allowed metrics: %s.
- Any number you write in the text must equal a fact in the note or a value a tool returned (rounding is fine). \
Do not compute new numbers in your head; put them in facts or query them.
- The conclusion must be one of the allowed conclusions given in the alert. Surveillance data shows patterns, not \
intent: write "consistent with", never "proves", "confirmed", "intentional" or "fraudulent".
- 2 to 5 findings, plain English, short sentences.""" % ", ".join(FACT_SQL)


@dataclass
class NoteResult:
    alert_id: str
    note: dict
    source: str  # llm_first_try | llm_after_retry | template
    checks: list[dict] = field(default_factory=list)
    tool_calls: int = 0
    latency_s: float = 0.0
    error: str | None = None

    def as_dict(self) -> dict:
        return {"alert_id": self.alert_id, "source": self.source, "note": self.note, "checks": self.checks,
                "tool_calls": self.tool_calls, "latency_s": round(self.latency_s, 2), "error": self.error}


def alert_context(tools: ReadOnlyTools, alert_id: str) -> dict:
    df = tools.con.execute(
        "SELECT a.*, f.* EXCLUDE (client_id, symbol, trade_date) FROM alert_scores a "
        "JOIN features f USING (client_id, symbol, trade_date) WHERE a.alert_id = ?", [alert_id]).df()
    if df.empty:
        raise KeyError(f"unknown alert {alert_id}")
    r = df.iloc[0].to_dict()
    flags = json.loads(r["red_flags"])
    reasons = json.loads(r["top_reasons"])
    level = r["evidence_level"]
    ctx = {
        "alert_id": alert_id, "client_id": r["client_id"], "symbol": r["symbol"],
        "trade_date": str(r["trade_date"])[:10], "daily_rank": int(r["daily_rank"]),
        "model_score": round(float(r["gbm_score"]), 3), "rules_fired": r["rules_fired"] or "none",
        "red_flags": flags, "evidence_level": level,
        "allowed_conclusions": sorted(ALLOWED[level]), "strongest_allowed_conclusion": strongest_allowed(level),
        "model_reasons": [{"feature": FEATURES.get(x["feature"], x["feature"]), "value": x["value"]}
                          for x in reasons],
    }
    nums = [ctx["daily_rank"], ctx["model_score"], len(flags)]
    nums += [x["value"] for x in reasons if x["value"] is not None]
    for fl in flags:
        nums += [float(n) for n in re.findall(r"\d+(?:\.\d+)?", fl["text"])]
    ctx["context_numbers"] = nums
    return ctx


def _parse_json(text: str | None) -> dict | None:
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _visible_ctx(ctx: dict) -> dict:
    return {k: v for k, v in ctx.items() if k != "context_numbers"}


def _run_planner(llm: ChatClient, tools: ReadOnlyTools, messages: list[dict]) -> tuple[dict | None, int]:
    n_calls = 0
    for _ in range(MAX_TOOL_ROUNDS):
        msg = llm.chat(messages, TOOL_SCHEMAS)
        calls = msg.get("tool_calls") or []
        if calls:
            messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
            for c in calls:
                try:
                    args = json.loads(c["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                out = tools.call(c["function"]["name"], args)
                n_calls += 1
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": out[:4000]})
            continue
        messages.append({"role": "assistant", "content": msg.get("content") or ""})
        return _parse_json(msg.get("content")), n_calls
    messages.append({"role": "user", "content": "Stop calling tools now and reply with the JSON note."})
    msg = llm.chat(messages, None)
    messages.append({"role": "assistant", "content": msg.get("content") or ""})
    return _parse_json(msg.get("content")), n_calls


def draft_case_note(alert_id: str, tools: ReadOnlyTools, llm: ChatClient | None) -> NoteResult:
    t0 = time.perf_counter()
    tools.reset()
    ctx = alert_context(tools, alert_id)
    checks: list[dict] = []
    n_calls = 0
    error = None
    if llm is not None:
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": "Investigate this alert and draft the case note.\nALERT:"
                     + json.dumps(_visible_ctx(ctx))}]
        try:
            for attempt in (1, 2):
                note, k = _run_planner(llm, tools, messages)
                n_calls += k
                res = check_note(note or {}, ctx, tools.con, tools.ledger) if note else None
                checks.append({"attempt": attempt, **(res.as_dict() if res else
                                                      {"passed": False, "failures": ["reply was not a JSON note"]})})
                if res and res.passed:
                    return NoteResult(alert_id, note, "llm_first_try" if attempt == 1 else "llm_after_retry", checks,
                                      n_calls, time.perf_counter() - t0)
                if attempt == 1:
                    fails = checks[-1]["failures"][:12]
                    messages.append({"role": "user", "content": "The checker rejected the note:\n- "
                                     + "\n- ".join(fails) + "\nFix these problems. You may call tools again. "
                                     "Reply with the corrected JSON note only."})
        except Exception as e:  # network or API failure: fall back, but say so
            error = f"{type(e).__name__}: {str(e)[:200]}"
    note = template_note(ctx, tools)
    res = check_note(note, ctx, tools.con, tools.ledger)
    checks.append({"attempt": "template", **res.as_dict()})
    return NoteResult(alert_id, note, "template", checks, n_calls, time.perf_counter() - t0, error)


EVIDENCE_SQL = {
    "linked_counterparty": "AND (t.counterparty_id = t.client_id OR t.counterparty_id IN "
                           "(SELECT linked_id FROM link_pairs WHERE client_id = t.client_id))",
    "repeated_internal_counterparty": "AND t.counterparty_id = (SELECT counterparty_id FROM trades x WHERE "
                                      "x.client_id = t.client_id AND x.symbol = t.symbol AND CAST(x.timestamp AS DATE)"
                                      " = CAST(t.timestamp AS DATE) AND x.counterparty_id <> 'EXT' GROUP BY 1 "
                                      "ORDER BY COUNT(*) DESC LIMIT 1)",
}


def template_note(ctx: dict, tools: ReadOnlyTools) -> dict:
    """A plain note built only from SQL. Used when the model's drafts fail the checker twice."""
    con = tools.con
    base = ("SELECT t.trade_id FROM trades t WHERE t.client_id = ? AND t.symbol = ? "
            "AND CAST(t.timestamp AS DATE) = CAST(? AS DATE) {extra} ORDER BY t.timestamp LIMIT 40")
    params = [ctx["client_id"], ctx["symbol"], ctx["trade_date"]]
    all_ids = [r[0] for r in con.execute(base.format(extra=""), params).fetchall()]
    findings = []
    if all_ids:
        f = compute_facts(con, all_ids, ["trade_count", "buy_count", "sell_count", "total_quantity",
                                         "net_quantity", "time_span_minutes"])
        findings.append({
            "text": (f"On {ctx['trade_date']} {ctx['client_id']} made {f['trade_count']:.0f} trades in "
                     f"{ctx['symbol']} ({f['buy_count']:.0f} buys, {f['sell_count']:.0f} sells, "
                     f"{f['total_quantity']:.0f} shares, net {f['net_quantity']:.0f}) over "
                     f"{f['time_span_minutes']:.1f} minutes."),
            "trade_ids": all_ids,
            "facts": [{"metric": k, "value": v} for k, v in f.items()],
        })
    for fl in ctx["red_flags"][:4]:
        extra = EVIDENCE_SQL.get(fl["flag"], "")
        ids = [r[0] for r in con.execute(base.format(extra=extra), params).fetchall()] if extra else all_ids[:10]
        if ids:
            findings.append({"text": f"Red flag: {fl['text']}.", "trade_ids": ids, "facts": [
                {"metric": "trade_count", "value": float(len(ids))}]})
    if not findings:
        findings.append({"text": "No trades were found for this alert; it rests on orders only.",
                         "trade_ids": [], "facts": []})
    concl = strongest_allowed(ctx["evidence_level"]) if ctx["red_flags"] else "REVIEW_FURTHER"
    return {
        "headline": f"{ctx['client_id']} / {ctx['symbol']} / {ctx['trade_date']}: "
                    f"{len(ctx['red_flags'])} red flag(s), evidence {ctx['evidence_level']}",
        "findings": findings,
        "conclusion": concl,
        "rationale": ("Generated from SQL results only, without the language model. The activity is consistent "
                      "with the red flags listed; an analyst should review the cited trades before deciding."),
    }


def make_tools(dataset_dir: str | Path) -> ReadOnlyTools:
    return ReadOnlyTools(Path(dataset_dir))
