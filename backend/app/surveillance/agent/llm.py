"""Chat clients for the planner: Groq's OpenAI-compatible API, and a deterministic stub for tests/CI."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Protocol

import httpx

from app.surveillance.paths import REPO_ROOT

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "openai/gpt-oss-120b"


class ChatClient(Protocol):
    name: str

    def chat(self, messages: list[dict], tools: list[dict] | None) -> dict:
        """Return one assistant message: {'role': 'assistant', 'content': str|None, 'tool_calls': [...]}."""


def load_api_key(var: str = "GROQ_API_KEY") -> str | None:
    """Read the key from the environment, else from the repo's git-ignored .env. Never logged."""
    if os.environ.get(var):
        return os.environ[var]
    env = REPO_ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(f"{var}="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                return val or None
    return None


class GroqClient:
    name = "groq:" + GROQ_MODEL

    def __init__(self, api_key: str | None = None, model: str = GROQ_MODEL, base_url: str = GROQ_BASE_URL,
                 timeout: float = 40.0, temperature: float = 0.2, max_retries: int = 6,
                 tpm_budget: int = 6500):
        key = api_key or load_api_key()
        if not key:
            raise RuntimeError("GROQ_API_KEY is not set (environment or .env)")
        self._headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        self.model, self.base_url, self.temperature = model, base_url.rstrip("/"), temperature
        self.max_retries = max_retries
        self.tpm_budget = tpm_budget  # tokens per minute we allow ourselves (the free tier caps at 8000)
        self._window: list[tuple[float, int]] = []
        self._http = httpx.Client(timeout=timeout)
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "requests": 0, "rate_limit_waits": 0}

    def _wait_for_budget(self, estimate: int) -> None:
        """Sleep until the last 60 s of usage plus this request fits the per-minute token budget."""
        while True:
            now = time.monotonic()
            self._window = [(t, n) for t, n in self._window if now - t < 60]
            used = sum(n for _, n in self._window)
            if not self._window or used + estimate <= self.tpm_budget:
                return
            self.usage["rate_limit_waits"] += 1
            time.sleep(max(1.0, 60 - (now - self._window[0][0]) + 0.5))

    def chat(self, messages: list[dict], tools: list[dict] | None) -> dict:
        body = {"model": self.model, "messages": messages, "temperature": self.temperature,
                "max_completion_tokens": 2048,
                "reasoning_effort": "low"}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        self._wait_for_budget(len(json.dumps(body)) // 3 + body["max_completion_tokens"] // 2)
        for attempt in range(self.max_retries):
            try:
                r = self._http.post(f"{self.base_url}/chat/completions", headers=self._headers, json=body)
            except httpx.TransportError:  # timeout or dropped connection: try again
                self.usage["rate_limit_waits"] += 1
                continue
            if r.status_code == 429 or r.status_code >= 500:
                wait = float(r.headers.get("retry-after", 0) or 0) or min(60.0, 4.0 * (attempt + 1))
                self.usage["rate_limit_waits"] += 1
                time.sleep(min(wait, 60.0))
                continue
            if r.status_code >= 400:
                # The body never contains the key; keep only the message.
                try:
                    msg = r.json().get("error", {}).get("message", "")[:300]
                except ValueError:
                    msg = r.text[:300]
                raise RuntimeError(f"Groq API error {r.status_code}: {msg}")
            data = r.json()
            u = data.get("usage") or {}
            self.usage["prompt_tokens"] += int(u.get("prompt_tokens", 0))
            self.usage["completion_tokens"] += int(u.get("completion_tokens", 0))
            self.usage["requests"] += 1
            self._window.append((time.monotonic(), int(u.get("total_tokens", 0))))
            msg = data["choices"][0]["message"]
            return {"role": "assistant", "content": msg.get("content"), "tool_calls": msg.get("tool_calls") or []}
        raise RuntimeError("Groq API kept rate-limiting; gave up")


class StubLLM:
    """Deterministic planner used offline. It queries the unit's trades, looks at the client, and writes
    a note from what came back. ``mistakes=1`` makes the first draft cite a trade that does not exist and
    overstate the conclusion, to exercise the checker and the retry path."""

    name = "stub"

    def __init__(self, mistakes: int = 0):
        self.mistakes = mistakes

    def chat(self, messages: list[dict], tools: list[dict] | None) -> dict:
        ctx = json.loads(next(m["content"] for m in messages if m["role"] == "user").split("ALERT:", 1)[1])
        tool_msgs = [m for m in messages if m["role"] == "tool"]
        feedback = any(m["role"] == "user" and m["content"].startswith("The checker rejected") for m in messages)
        if not tool_msgs:
            q = (f"SELECT trade_id, side, quantity, price, counterparty_id, timestamp FROM trades "
                 f"WHERE client_id = '{ctx['client_id']}' AND symbol = '{ctx['symbol']}' "
                 f"AND CAST(timestamp AS DATE) = DATE '{ctx['trade_date']}' ORDER BY timestamp")
            return _call("call_1", "sql_query", {"query": q})
        if len(tool_msgs) == 1:
            return _call("call_2", "client_profile", {"client_id": ctx["client_id"], "as_of": ctx["trade_date"]})
        res = json.loads(tool_msgs[0]["content"])
        rows = res.get("rows", [])[:20]
        ids = [r[0] for r in rows]
        qty = sum(int(r[2]) for r in rows)
        bad = self.mistakes > 0 and not feedback
        note = {
            "headline": f"{ctx['client_id']} in {ctx['symbol']} on {ctx['trade_date']}: {len(ids)} trades reviewed",
            "findings": [{
                "text": f"The client executed {len(ids)} trades for {qty} shares in total.",
                "trade_ids": ids + (["T99999999"] if bad else []),
                "facts": [{"metric": "trade_count", "value": len(ids)}, {"metric": "total_quantity", "value": qty}],
            }] + [{"text": fl["text"], "trade_ids": ids[:5], "facts": []} for fl in ctx["red_flags"][:2]],
            "conclusion": "ESCALATE" if bad else ctx["strongest_allowed_conclusion"],
            "rationale": "The activity above is consistent with the flagged pattern and needs an analyst's review.",
        }
        return {"role": "assistant", "content": json.dumps(note), "tool_calls": []}


def _call(cid: str, name: str, args: dict) -> dict:
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


def env_file_path() -> Path:
    return REPO_ROOT / ".env"
