"""Run the case-note agent on the top-ranked holdout alerts and report how the checker scored it.

    python scripts/run_agent_eval.py                 # Groq, 20 alerts, writes reports/AGENT_EVAL.md
    python scripts/run_agent_eval.py --llm stub --n 3 --out reports_ci   # offline, for CI
    python scripts/run_agent_eval.py --false-alerts 8    # highest-ranked holdout alerts that are NOT manipulation,
                                                         # writes reports/AGENT_EVAL_FALSE.md

Needs scripts/run_eval.py to have written the alert queue first. Ground-truth labels are read only
to report agreement at the end; the agent never sees them.
"""
import argparse
import json
import statistics
import time
from pathlib import Path

import _bootstrap  # noqa: F401
import duckdb

from app.surveillance.agent.case_note import draft_case_note, make_tools
from app.surveillance.agent.llm import GroqClient, StubLLM
from app.surveillance.paths import DEFAULT_DATASET_DIR, LABELS_DB, REPORTS_DIR

CATEGORIES = [
    ("does not exist", "cited a trade ID that does not exist"),
    ("is not a", "cited a trade outside the alert"),
    ("cites no trade", "finding without trade IDs"),
    ("but the cited trades give", "fact did not match SQL"),
    ("cannot be computed", "fact did not match SQL"),
    ("unknown fact metric", "used an unknown fact metric"),
    ("does not match any figure", "number in text not traceable to data"),
    ("claims more than", "overclaiming wording"),
    ("exceeds the evidence", "conclusion stronger than the evidence"),
    ("not a JSON", "reply was not a valid note"),
    ("missing field", "reply was not a valid note"),
    ("findings must be", "reply was not a valid note"),
]


def category(msg: str) -> str:
    for key, name in CATEGORIES:
        if key in msg:
            return name
    return "other"


def pick_alerts(con, n: int) -> list[str]:
    days = [r[0] for r in con.execute(
        "SELECT DISTINCT trade_date FROM alert_scores WHERE split = 'test' ORDER BY 1").fetchall()]
    per_day = max(1, -(-n // max(1, len(days))))
    ids = [r[0] for r in con.execute(
        "SELECT alert_id FROM alert_scores WHERE split = 'test' AND daily_rank <= ? ORDER BY trade_date, daily_rank",
        [per_day]).fetchall()]
    return ids[:n]


def load_truth(data: str) -> dict[str, str]:
    """alert_id -> simulator pattern. Units absent from the map are not manipulation."""
    lab = duckdb.connect(str(Path(data) / LABELS_DB), read_only=True)
    try:
        return {f"{d.strftime('%Y%m%d')}-{c}-{s}": p for c, s, d, p in lab.execute(
            "SELECT client_id, symbol, CAST(trade_date AS DATE), MIN(pattern) FROM event_units GROUP BY ALL"
        ).fetchall()}
    finally:
        lab.close()


def pick_false_alerts(con, truth: dict[str, str], n: int) -> list[str]:
    """The n highest-ranked in-queue holdout alerts whose ground truth is not a manipulation, best first."""
    rows = con.execute(
        "SELECT alert_id FROM alert_scores WHERE split = 'test' AND in_queue ORDER BY final_score DESC, alert_id"
    ).fetchall()
    return [a for (a,) in rows if a not in truth][:n]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(DEFAULT_DATASET_DIR))
    ap.add_argument("--out", default=str(REPORTS_DIR))
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--false-alerts", type=int, default=None, metavar="N",
                    help="instead of the top alerts, run the N highest-ranked holdout alerts that are not "
                         "manipulation in the simulator (writes AGENT_EVAL_FALSE.md / agent_eval_false.json)")
    ap.add_argument("--pace", type=float, default=None, help="seconds to wait between alerts (default 4 for groq)")
    ap.add_argument("--llm", choices=["groq", "stub", "stub-mistakes"], default="groq")
    ap.add_argument("--max-wait", type=float, default=None,
                    help="longest rate-limit wait (s) to sit out instead of falling back (default 75)")
    ap.add_argument("--model", default=None, help="Groq model id (default: openai/gpt-oss-120b)")
    args = ap.parse_args()

    tools = make_tools(args.data)
    if args.max_wait is not None:
        import app.surveillance.agent.llm as llm_module

        llm_module.MAX_WAIT_S = args.max_wait
    if args.llm == "groq":
        llm = GroqClient(model=args.model) if args.model else GroqClient()
    else:
        llm = StubLLM(mistakes=1 if args.llm == "stub-mistakes" else 0)
    truth = load_truth(args.data)
    false_mode = args.false_alerts is not None
    alerts = pick_false_alerts(tools.con, truth, args.false_alerts) if false_mode else pick_alerts(tools.con, args.n)

    pace = args.pace if args.pace is not None else (4.0 if args.llm == "groq" else 0.0)
    results = []
    t_all = time.perf_counter()
    for i, a in enumerate(alerts, 1):
        r = draft_case_note(a, tools, llm).as_dict()
        r["truth"] = truth.get(a, "none")
        results.append(r)
        print(f"[{i}/{len(alerts)}] {a} {r['source']} {r['latency_s']}s tools={r['tool_calls']}"
              + (f" error={r['error']}" if r["error"] else ""), flush=True)
        if pace and i < len(alerts):
            time.sleep(pace)
    wall = time.perf_counter() - t_all
    tools.close()

    n = len(results)
    first = sum(r["source"] == "llm_first_try" for r in results)
    retry = sum(r["source"] == "llm_after_retry" for r in results)
    tmpl = sum(r["source"] == "template" for r in results)
    tmpl_pass = sum(r["source"] == "template" and r["checks"][-1]["passed"] for r in results)
    errors = sum(1 for r in results if r["error"])
    lat = sorted(r["latency_s"] for r in results)
    fail_cats: dict[str, int] = {}
    for r in results:
        for c in r["checks"]:
            if c["attempt"] == 1 and not c["passed"]:
                for cat in sorted({category(m) for m in c["failures"]}):
                    fail_cats[cat] = fail_cats.get(cat, 0) + 1
    agree = {"true_alert": {}, "false_alert": {}}
    for r in results:
        key = "true_alert" if r["truth"] != "none" else "false_alert"
        concl = r["note"]["conclusion"]
        agree[key][concl] = agree[key].get(concl, 0) + 1
    summary = {
        "llm": llm.name, "alerts": n,
        "pass_first_try": first, "pass_after_retry": retry, "fallback_template": tmpl,
        "template_passed_checker": tmpl_pass, "api_errors": errors,
        "pass_rate_first_try": round(first / n, 3) if n else 0,
        "pass_rate_after_retry": round((first + retry) / n, 3) if n else 0,
        "latency_s": {"median": round(statistics.median(lat), 1) if lat else 0,
                      "p95": round(lat[min(len(lat) - 1, int(0.95 * len(lat)))], 1) if lat else 0,
                      "max": round(lat[-1], 1) if lat else 0},
        "wall_clock_s": round(wall, 1),
        "mean_tool_calls": round(sum(r["tool_calls"] for r in results) / n, 1) if n else 0,
        "first_try_failure_reasons": fail_cats,
        "conclusion_vs_truth": agree,
        "usage": getattr(llm, "usage", None),
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = "agent_eval_false" if false_mode else "agent_eval"
    (out / f"{stem}.json").write_text(json.dumps({"summary": summary, "results": results}, indent=2, default=str),
                                         encoding="utf-8")
    write_md(summary, results, out / ("AGENT_EVAL_FALSE.md" if false_mode else "AGENT_EVAL.md"), args.data,
             false_mode)
    print(json.dumps(summary, indent=2))


def render_note(r: dict) -> list[str]:
    note = r["note"]
    lines = [f"**{note.get('headline', '')}**", ""]
    for i, f in enumerate(note.get("findings", []), 1):
        ids = f.get("trade_ids", [])
        shown = ", ".join(ids[:6]) + (f" and {len(ids) - 6} more" if len(ids) > 6 else "")
        lines.append(f"{i}. {f.get('text', '')} (trades: {shown})")
    lines += ["", f"Conclusion: **{note.get('conclusion')}**. {note.get('rationale', '')}"]
    return lines


def write_md(s: dict, results: list[dict], path: Path, data: str, false_mode: bool = False) -> None:
    L = []
    a = L.append
    n = s["alerts"]
    a("# Case-note agent on false alerts: checker results" if false_mode else "# Case-note agent: checker results")
    a("")
    if false_mode:
        a(f"Generated by `scripts/run_agent_eval.py --false-alerts` with `{s['llm']}` on the highest-ranked holdout")
        a(f"alerts of the simulated dataset (`{Path(data).name}`) that are NOT manipulation in the simulator: the")
        a("model's false positives, hard negatives included. **The trading data is simulated**; the language model is")
        a("real. The question is whether the agent can say DISMISS or REVIEW_FURTHER instead of ESCALATE.")
    else:
        a(f"Generated by `scripts/run_agent_eval.py` with `{s['llm']}` on the top-ranked holdout alerts of the")
        a(f"simulated dataset (`{Path(data).name}`, two per day). **The trading data is simulated**; the language")
        a("model is real.")
    a("")
    a("Every note goes through the deterministic checker in `app/surveillance/agent/checker.py`: cited trade IDs")
    a("must exist and belong to the alert, every stated figure is recomputed in SQL, every number in the prose")
    a("must trace back to a tool result, and the conclusion may not exceed the evidence level computed in code.")
    a("A failed draft gets one retry with the checker's feedback; a second failure falls back to a templated note.")
    a("")
    a("| Measure | Value |")
    a("|---|---|")
    a(f"| Alerts | {n} |")
    a(f"| Passed the checker on the first draft | {s['pass_first_try']} ({s['pass_rate_first_try']:.0%}) |")
    a(f"| Passed after one retry with feedback | {s['pass_first_try'] + s['pass_after_retry']} "
      f"({s['pass_rate_after_retry']:.0%}) |")
    a(f"| Fell back to the templated note | {s['fallback_template']} "
      f"(template passed the checker in {s['template_passed_checker']} of them) |")
    a(f"| API errors | {s['api_errors']} |")
    a(f"| Latency per note, median / p95 / max | {s['latency_s']['median']} s / {s['latency_s']['p95']} s / "
      f"{s['latency_s']['max']} s |")
    a(f"| Tool calls per note, mean | {s['mean_tool_calls']} |")
    if s.get("usage"):
        u = s["usage"]
        a(f"| Tokens (prompt / completion), all notes | {u['prompt_tokens']:,} / {u['completion_tokens']:,} |")
        a(f"| Requests / rate-limit waits | {u['requests']} / {u['rate_limit_waits']} |")
    a("")
    if s["first_try_failure_reasons"]:
        a("Why first drafts failed (a draft can fail for more than one reason):")
        a("")
        a("| Reason | Drafts |")
        a("|---|---|")
        for k, v in sorted(s["first_try_failure_reasons"].items(), key=lambda x: -x[1]):
            a(f"| {k} | {v} |")
        a("")
    a("Conclusions against the simulator's ground truth (the agent never sees it):")
    a("")
    a("| | ESCALATE | REVIEW_FURTHER | DISMISS |")
    a("|---|---|---|---|")
    for key, label in (("true_alert", "True alerts"), ("false_alert", "False alerts")):
        d = s["conclusion_vs_truth"][key]
        a(f"| {label} | {d.get('ESCALATE', 0)} | {d.get('REVIEW_FURTHER', 0)} | {d.get('DISMISS', 0)} |")
    a("")
    a("Latency includes waiting out the API's rate limits on a free-tier key, so it says more about the key than")
    a("the model.")
    a("")
    a("## Example notes")
    a("")
    llm_notes = [r for r in results if r["source"] != "template"]
    examples = (llm_notes[:2] if len(llm_notes) >= 2 else llm_notes + [r for r in results if r["source"] == "template"])
    for r in examples[:2]:
        a(f"### {r['alert_id']} ({r['source'].replace('_', ' ')}, ground truth: {r['truth'].replace('_', ' ')})")
        a("")
        L.extend(render_note(r))
        a("")
    fallback = [r for r in results if r["source"] == "template"]
    if fallback and fallback[0] not in examples[:2]:
        r = fallback[0]
        a(f"### {r['alert_id']} (templated fallback, ground truth: {r['truth'].replace('_', ' ')})")
        a("")
        fails = [m for c in r["checks"] if c["attempt"] != "template" for m in c["failures"]][:4]
        if fails:
            a("The model's drafts were rejected for: " + "; ".join(fails) + ".")
            a("")
        L.extend(render_note(r))
        a("")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
