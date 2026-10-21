"""Deterministic checks on a drafted case note. No model is involved here.

A note passes only if:
  1. it has the expected shape (headline, 1-8 findings, conclusion, rationale);
  2. every finding cites at least one trade ID, and every cited ID exists;
  3. every cited trade belongs to the alert: same symbol and day, and the alert's client is
     either side of it;
  4. every structured fact (trade_count, total_quantity, ...) equals what SQL computes from the
     finding's own cited trades;
  5. every number written in the text matches a fact in the note, a value the tools returned
     during this investigation, or a value in the alert context (within rounding);
  6. the conclusion is allowed for the alert's evidence level, and the wording does not claim
     more than surveillance data can show (no "proves", "confirmed", "intentional", ...).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import duckdb

from app.surveillance.evidence import ALLOWED, CONCLUSIONS

FACT_SQL = {
    "trade_count": "COUNT(*)",
    "buy_count": "COUNT(*) FILTER (WHERE side = 'BUY')",
    "sell_count": "COUNT(*) FILTER (WHERE side = 'SELL')",
    "total_quantity": "SUM(quantity)",
    "net_quantity": "SUM(CASE WHEN side = 'BUY' THEN quantity ELSE -quantity END)",
    "total_value": "SUM(quantity * price)",
    "min_price": "MIN(price)",
    "max_price": "MAX(price)",
    "vwap": "SUM(quantity * price) / SUM(quantity)",
    "time_span_minutes": "date_diff('second', MIN(timestamp), MAX(timestamp)) / 60.0",
    "distinct_counterparties": "COUNT(DISTINCT counterparty_id)",
}
EXACT = {"trade_count", "buy_count", "sell_count", "total_quantity", "net_quantity", "distinct_counterparties"}

OVERCLAIM = re.compile(
    r"\b(prove[sdn]?|proof|confirm(?:s|ed)?|conclusive(?:ly)?|guilty|definitely|certainly|undeniabl\w*|"
    r"beyond (?:any |reasonable )?doubt|intentional(?:ly)?|deliberate(?:ly)?|fraudulent(?:ly)?|"
    r"committed (?:fraud|manipulation)|is manipulation|was manipulation)\b",
    re.IGNORECASE,
)
# Identifiers, dates and clock times are not quantities; drop them before extracting numbers.
_IDS = re.compile(r"\b(?:[TOCD]\d{3,}|D\d{2}|[A-Z]{2}\d{2}|\d{8}-C\d+-[A-Z]{2}\d{2}|\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}"
                  r"(?::\d{2}(?:\.\d+)?)?)?|\d{1,2}:\d{2}(?::\d{2})?)\b")
_NUM = re.compile(r"(?<![\w.])[-+]?(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d+)?(?![\w])")


@dataclass
class CheckResult:
    passed: bool
    failures: list[str] = field(default_factory=list)
    checked_numbers: int = 0
    cited_trades: int = 0

    def as_dict(self) -> dict:
        return {"passed": self.passed, "failures": self.failures, "checked_numbers": self.checked_numbers,
                "cited_trades": self.cited_trades}


def compute_facts(con: duckdb.DuckDBPyConnection, trade_ids: list[str], metrics: list[str]) -> dict[str, float]:
    metrics = [m for m in metrics if m in FACT_SQL]
    if not trade_ids or not metrics:
        return {}
    sel = ", ".join(f"{FACT_SQL[m]} AS {m}" for m in metrics)
    ph = ", ".join("?" for _ in trade_ids)
    row = con.execute(f"SELECT {sel} FROM trades WHERE trade_id IN ({ph})", list(trade_ids)).fetchone()
    return {m: (None if v is None else float(v)) for m, v in zip(metrics, row)}


def _close(written: float, ref: float, decimals: int) -> bool:
    tol = max(0.5 * 10 ** (-decimals), 0.005 * abs(ref), 1e-9)
    return abs(written - ref) <= tol


def _matches_any(x: float, decimals: int, refs: list[float]) -> bool:
    for r in refs:
        if _close(x, r, decimals) or _close(x, r * 100, decimals) or _close(x, abs(r), decimals):
            return True
    return False


def extract_numbers(text: str) -> list[tuple[float, int]]:
    out = []
    for m in _NUM.finditer(_IDS.sub(" ", text or "")):
        s = m.group(0).replace(",", "")
        dec = len(s.split(".")[1]) if "." in s else 0
        try:
            out.append((float(s), dec))
        except ValueError:
            continue
    return out


def check_note(note: dict, ctx: dict, con: duckdb.DuckDBPyConnection, ledger: list[float]) -> CheckResult:
    f: list[str] = []
    if not isinstance(note, dict):
        return CheckResult(False, ["note is not a JSON object"])
    for key in ("headline", "findings", "conclusion", "rationale"):
        if key not in note:
            f.append(f"missing field: {key}")
    findings = note.get("findings") or []
    if not isinstance(findings, list) or not (1 <= len(findings) <= 8):
        f.append("findings must be a list of 1 to 8 items")
        findings = findings if isinstance(findings, list) else []
    if f:
        return CheckResult(False, f)

    all_ids = sorted({str(t) for fd in findings if isinstance(fd, dict) for t in (fd.get("trade_ids") or [])})
    known = {}
    if all_ids:
        ph = ", ".join("?" for _ in all_ids)
        rows = con.execute(f"SELECT trade_id, client_id, counterparty_id, symbol, CAST(timestamp AS DATE) "
                           f"FROM trades WHERE trade_id IN ({ph})", all_ids).fetchall()
        known = {r[0]: r for r in rows}
    fact_values: list[float] = []
    for i, fd in enumerate(findings, 1):
        if not isinstance(fd, dict):
            f.append(f"finding {i} is not an object")
            continue
        ids = [str(t) for t in (fd.get("trade_ids") or [])]
        if not ids:
            f.append(f"finding {i} cites no trade IDs")
            continue
        if len(ids) > 60:
            f.append(f"finding {i} cites more than 60 trades")
        for t in ids:
            r = known.get(t)
            if r is None:
                f.append(f"finding {i}: trade {t} does not exist")
            elif r[3] != ctx["symbol"] or str(r[4]) != ctx["trade_date"] or ctx["client_id"] not in (r[1], r[2]):
                f.append(f"finding {i}: trade {t} is not a {ctx['symbol']} trade of {ctx['client_id']} on "
                         f"{ctx['trade_date']}")
        valid = [t for t in ids if t in known]
        facts = fd.get("facts") or []
        if not isinstance(facts, list):
            f.append(f"finding {i}: facts must be a list")
            facts = []
        wanted = [x.get("metric") for x in facts if isinstance(x, dict)]
        actual = compute_facts(con, valid, [m for m in wanted if m]) if valid else {}
        for x in facts:
            if not isinstance(x, dict):
                continue
            m, v = x.get("metric"), x.get("value")
            if m not in FACT_SQL:
                f.append(f"finding {i}: unknown fact metric '{m}' (allowed: {', '.join(FACT_SQL)})")
                continue
            try:
                v = float(v)
            except (TypeError, ValueError):
                f.append(f"finding {i}: fact {m} has a non-numeric value")
                continue
            a = actual.get(m)
            if a is None:
                f.append(f"finding {i}: fact {m} cannot be computed from the cited trades")
            elif (m in EXACT and abs(v - a) > 1e-9) or (m not in EXACT and not _close(v, a, 2)):
                f.append(f"finding {i}: fact {m} = {v:g} but the cited trades give {a:g}")
            else:
                fact_values.append(v)

    refs = list(ledger) + fact_values + [float(x) for x in ctx.get("context_numbers", [])]
    n_checked = 0
    texts = [("headline", note.get("headline", "")), ("rationale", note.get("rationale", ""))]
    texts += [(f"finding {i}", fd.get("text", "")) for i, fd in enumerate(findings, 1) if isinstance(fd, dict)]
    for where, text in texts:
        for x, dec in extract_numbers(str(text)):
            n_checked += 1
            if not _matches_any(x, dec, refs):
                f.append(f"{where}: the number {x:g} does not match any figure returned by the tools or the facts")
        m = OVERCLAIM.search(str(text))
        if m:
            f.append(f"{where}: '{m.group(0)}' claims more than surveillance data can show")

    concl = note.get("conclusion")
    if concl not in CONCLUSIONS:
        f.append(f"conclusion must be one of {', '.join(CONCLUSIONS)}")
    elif concl not in ALLOWED[ctx["evidence_level"]]:
        f.append(f"conclusion {concl} exceeds the evidence: level is '{ctx['evidence_level']}', allowed "
                 f"{', '.join(sorted(ALLOWED[ctx['evidence_level']]))}")
    return CheckResult(not f, f, n_checked, len(all_ids))


def finite(x) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False
