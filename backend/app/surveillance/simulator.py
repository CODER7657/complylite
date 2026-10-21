"""Seeded, labeled market simulator for broker-side trade surveillance.

What it produces (one dataset directory):

* ``market.duckdb``: what a broker can actually see. Tables ``clients``,
  ``symbols``, ``orders``, ``trades``, ``market_bars`` and ``dataset_meta``.
  No labels live in this file, so nothing downstream can leak them by accident.
* ``labels.duckdb``: ground truth. ``events`` (one row per injected
  manipulation), ``event_orders``, ``event_units`` (the client/symbol/day units
  each event touches) and ``scenario_units`` (hard negatives, tagged by type).
* ``config.json``: the seed and the full config, so any dataset can be rebuilt.

Normal flow comes from four client types (retail, intraday traders, market
makers, institutions) with a U-shaped intraday activity curve. On top of that
the simulator injects wash trades, spoofing/layering, pump-and-dump rings and
front-running by dealer-linked accounts, plus hard negatives that look similar
but are legitimate: market makers that cancel most of their quotes, intraday
round trips, family accounts trading the same names, news-driven buying,
retail clients who happen to share a dealer with an institution.

Everything here is simulated. It is useful for checking that a pipeline can
find patterns we planted; it says nothing about how often these patterns occur
in a real Indian brokerage, or what real manipulators do differently.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from app.surveillance.paths import LABELS_DB, MARKET_DB

GENERATOR_VERSION = "1.0"
SESSION_MINUTES = 375  # 09:15 to 15:30 IST
SESSION_SEC = SESSION_MINUTES * 60
TICK = 0.05
PATTERNS = ("wash_trade", "spoofing", "pump_and_dump", "front_running")


@dataclass
class SimConfig:
    seed: int = 42
    n_days: int = 40
    start_date: str = "2026-03-02"
    n_large_caps: int = 20
    n_small_caps: int = 10
    n_retail: int = 600
    n_day_traders: int = 70
    n_market_makers: int = 2
    mm_symbols: int = 6
    mm_quotes_per_symbol_day: float = 350.0
    n_institutional: int = 12
    n_dealers: int = 6
    n_family_groups: int = 40
    n_rings: int = 16
    wash_per_day: float = 7.0
    spoof_per_day: float = 6.0
    front_run_per_day: float = 3.0
    pump_dump_start_prob: float = 0.33
    news_per_day: float = 0.4
    internal_cross_prob: float = 0.08
    # How blatant the manipulation is. The "hard" preset turns these down.
    wash_max_round_trips: int = 12
    wash_fixed_price_prob: float = 0.6
    spoof_max_layers: int = 5
    spoof_size_mult_max: float = 12.0
    front_run_via_dealer_prob: float = 0.6
    pump_rise_max: float = 0.22
    pump_circular_prob: float = 0.4
    notes: dict = field(default_factory=dict)


PRESETS: dict[str, dict] = {
    "default": {},
    "tiny": dict(
        n_days=8, n_large_caps=8, n_small_caps=4, n_retail=120, n_day_traders=15,
        n_market_makers=1, mm_symbols=3, mm_quotes_per_symbol_day=120.0,
        n_institutional=4, n_dealers=3, n_family_groups=8, n_rings=6,
        wash_per_day=3.0, spoof_per_day=3.0, front_run_per_day=1.5, pump_dump_start_prob=0.5,
    ),
    "hard": dict(
        wash_max_round_trips=4, wash_fixed_price_prob=0.3, spoof_max_layers=3, spoof_size_mult_max=4.0,
        front_run_via_dealer_prob=0.3, pump_rise_max=0.10, pump_circular_prob=0.15,
    ),
    "large": dict(n_days=80, n_retail=1200, n_day_traders=140, n_family_groups=80, n_rings=30),
}


def make_config(preset: str = "default", **overrides) -> SimConfig:
    params = dict(PRESETS[preset])
    params.update({k: v for k, v in overrides.items() if v is not None})
    return SimConfig(**params)


def trading_days(start: str, n: int) -> list[date]:
    d = date.fromisoformat(start)
    out: list[date] = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _intraday_weights() -> np.ndarray:
    m = np.arange(SESSION_MINUTES)
    w = 1.0 + 2.2 * ((m - SESSION_MINUTES / 2) / (SESSION_MINUTES / 2)) ** 2
    return w / w.sum()


def round_tick(p: float) -> float:
    return round(round(p / TICK) * TICK, 2)


class _Book:
    """Column buffers for orders and trades, filled one row at a time."""

    def __init__(self) -> None:
        self.o = {k: [] for k in ("client", "trader", "sym", "side", "qty", "price", "day", "t",
                                  "otype", "status", "filled", "end_t", "event")}
        self.tr = {k: [] for k in ("order", "client", "cp", "sym", "side", "qty", "price", "day", "t",
                                   "event")}

    def add_order(self, **kw) -> int:
        for k, v in kw.items():
            self.o[k].append(v)
        return len(self.o["client"]) - 1

    def add_trade(self, **kw) -> int:
        for k, v in kw.items():
            self.tr[k].append(v)
        return len(self.tr["client"]) - 1


class MarketSimulator:
    def __init__(self, cfg: SimConfig):
        self.cfg = cfg
        self.rng = np.random.default_rng(cfg.seed)
        self.days = trading_days(cfg.start_date, cfg.n_days)
        self.w_intraday = _intraday_weights()
        self.cdf_intraday = np.cumsum(self.w_intraday)
        self.book = _Book()
        self.events: list[dict] = []
        self.scenario_units: list[tuple[int, int, int, str]] = []

    # ------------------------------------------------------------------ setup
    def _build_symbols(self) -> None:
        cfg, rng = self.cfg, self.rng
        names, seg, base, vol, hs, adv = [], [], [], [], [], []
        for i in range(cfg.n_large_caps):
            names.append(f"LC{i + 1:02d}")
            seg.append("LARGE")
            base.append(rng.uniform(300, 3000))
            vol.append(rng.uniform(0.011, 0.016))
            hs.append(rng.uniform(1.5, 3.5))
            adv.append(rng.uniform(1.0e6, 5.0e6))
        for i in range(cfg.n_small_caps):
            names.append(f"SC{i + 1:02d}")
            seg.append("SMALL")
            base.append(rng.uniform(25, 150))
            vol.append(rng.uniform(0.022, 0.035))
            hs.append(rng.uniform(8, 20))
            adv.append(rng.uniform(5.0e4, 3.0e5))
        self.sym_names = names
        self.sym_segment = np.array(seg)
        self.sym_base = np.array(base)
        self.sym_vol = np.array(vol)
        self.half_spread = np.array(hs)
        self.sym_adv = np.array(adv)
        self.large = np.where(self.sym_segment == "LARGE")[0]
        self.small = np.where(self.sym_segment == "SMALL")[0]

    def _new_client(self, ctype: str, dealer: str, role: str) -> int:
        rng = self.rng
        idx = len(self.c_type)
        self.c_type.append(ctype)
        self.c_dealer.append(dealer)
        self.c_role.append(role)
        self.c_attrs.append({k: f"{k[0]}{rng.integers(1e9, 1e10)}" for k in ("mobile", "email", "address")})
        if ctype == "RETAIL":
            p = float(rng.beta(2, 6))
        elif ctype == "DAY_TRADER":
            p = float(rng.uniform(0.55, 0.9))
        else:
            p = 0.5
        self.c_pactive.append(p)
        # Ticket size varies a lot between clients; manipulators trade at their own usual size.
        self.c_size.append(float(np.exp(rng.normal(0, 0.8))) if ctype in ("RETAIL", "DAY_TRADER") else 1.0)
        fav_large = rng.choice(self.large, size=min(3, len(self.large)), replace=False)
        fav_small = rng.choice(self.small, size=min(1, len(self.small)), replace=False)
        self.c_fav.append(np.concatenate([fav_large, fav_small]))
        return idx

    def _build_clients(self) -> None:
        cfg, rng = self.cfg, self.rng
        self.c_type, self.c_dealer, self.c_role, self.c_attrs, self.c_pactive, self.c_fav = [], [], [], [], [], []
        self.c_size: list[float] = []
        self.dealers = [f"D{i + 1:02d}" for i in range(cfg.n_dealers)]
        self.retail = [
            self._new_client("RETAIL", rng.choice(self.dealers) if rng.random() < 0.3 else "ONLINE", "normal")
            for _ in range(cfg.n_retail)
        ]
        self.day_traders = [self._new_client("DAY_TRADER", "ONLINE", "normal") for _ in range(cfg.n_day_traders)]
        # About a third of intraday traders scalp: many short round trips of the same size.
        self.scalpers = {c for c in self.day_traders if rng.random() < 0.3}
        self.mms = [self._new_client("MARKET_MAKER", "DMA", "normal") for _ in range(cfg.n_market_makers)]
        self.insts = [self._new_client("INSTITUTIONAL", rng.choice(self.dealers), "normal")
                      for _ in range(cfg.n_institutional)]
        self.mm_syms = {
            mm: rng.choice(self.large, size=min(cfg.mm_symbols, len(self.large)), replace=False) for mm in self.mms
        }
        # Family groups: legitimate linked accounts (shared address, sometimes mobile).
        self.families: list[list[int]] = []
        pool = list(rng.permutation(self.retail))
        for _ in range(cfg.n_family_groups):
            size = int(rng.integers(2, 4))
            if len(pool) < size:
                break
            members = [int(pool.pop()) for _ in range(size)]
            addr = self.c_attrs[members[0]]["address"]
            mob = self.c_attrs[members[0]]["mobile"]
            for m in members:
                self.c_attrs[m]["address"] = addr
                if rng.random() < 0.5:
                    self.c_attrs[m]["mobile"] = mob
                self.c_role[m] = "family"
            self.families.append(members)
        self.family_of = {m: fam for fam in self.families for m in fam}
        # Manipulation rings: half share a mobile or email (linkable), half do not.
        self.rings: list[dict] = []
        for _ in range(cfg.n_rings):
            size = int(rng.integers(2, 5))
            members = [
                self._new_client("RETAIL" if rng.random() < 0.6 else "DAY_TRADER", "ONLINE", "ring")
                for _ in range(size)
            ]
            linked = bool(rng.random() < 0.5)
            if linked:
                key = "mobile" if rng.random() < 0.5 else "email"
                val = self.c_attrs[members[0]][key]
                for m in members:
                    self.c_attrs[m][key] = val
            self.rings.append({"members": members, "linked": linked})
        # One dealer-linked account per dealer: the front-running candidates.
        self.fr_accounts = {d: self._new_client("RETAIL", d, "dealer_linked") for d in self.dealers}
        # Shuffle IDs so the client number says nothing about type or role.
        n = len(self.c_type)
        perm = rng.permutation(n)
        self.client_ids = [f"C{int(p) + 1:05d}" for p in perm]

    # --------------------------------------------------------------- helpers
    def sample_secs(self, n: int, lo: float = 0.0, hi: float = SESSION_SEC) -> np.ndarray:
        """Sample times (seconds after 09:15) from the U-shaped intraday curve, restricted to [lo, hi)."""
        lo_m, hi_m = int(lo // 60), max(int(lo // 60) + 1, int(math.ceil(hi / 60)))
        hi_m = min(hi_m, SESSION_MINUTES)
        w = self.w_intraday[lo_m:hi_m]
        mins = self.rng.choice(np.arange(lo_m, hi_m), size=n, p=w / w.sum())
        secs = mins * 60 + self.rng.uniform(0, 60, size=n)
        return np.clip(secs, lo, hi - 0.5)

    def mid(self, s: int, d: int, sec: float) -> float:
        x = min(max(sec, 0.0), SESSION_SEC) / 60.0
        m = int(x)
        if m >= SESSION_MINUTES:
            return math.exp(self.lp[s, d, SESSION_MINUTES])
        f = x - m
        return math.exp(self.lp[s, d, m] * (1 - f) + self.lp[s, d, m + 1] * f)

    def notional_qty(self, s: int, d: int, notional: float) -> int:
        return max(1, int(notional / self.mid(s, d, SESSION_SEC / 2)))

    def order(self, c: int, s: int, d: int, sec: float, side: str, qty: int, otype: str, *,
              offset_bps: float = 0.0, lifetime: float = 60.0, p_fill: float | None = None,
              fill_delay: float | None = None, price: float | None = None, cp: int | str = "EXT",
              event: int = -1, trader: str | None = None) -> tuple[int, int]:
        """Place one order and, if it fills, its trade. Returns (order_idx, trade_idx or -1)."""
        rng = self.rng
        sec = float(min(max(sec, 0.0), SESSION_SEC - 1.0))
        qty = int(max(1, qty))
        sgn = 1 if side == "BUY" else -1
        m = self.mid(s, d, sec)
        trader = trader or self.c_dealer[c]
        if otype == "MARKET":
            fill_t = sec + float(rng.uniform(0.05, 0.8))
            px = round_tick(m * (1 + sgn * self.half_spread[s] * 1e-4))
            filled = True
        else:
            px = price if price is not None else round_tick(m * (1 - sgn * offset_bps * 1e-4))
            if p_fill is None:
                p_fill = float(np.clip(0.95 * math.exp(-max(offset_bps, 0.0) / 12.0), 0.02, 0.95))
            filled = bool(rng.random() < p_fill)
            fill_t = sec + (fill_delay if fill_delay is not None else float(rng.uniform(0.1, max(lifetime, 0.2))))
        if filled and fill_t >= SESSION_SEC:
            filled = False
        end_t = fill_t if filled else min(sec + lifetime, SESSION_SEC)
        oi = self.book.add_order(client=c, trader=trader, sym=s, side=side, qty=qty, price=px, day=d, t=sec,
                                 otype=otype, status="FILLED" if filled else "CANCELLED",
                                 filled=qty if filled else 0, end_t=end_t, event=event)
        ti = -1
        if filled:
            ti = self.book.add_trade(order=oi, client=c, cp=cp, sym=s, side=side, qty=qty, price=px, day=d,
                                     t=fill_t, event=event)
        return oi, ti

    def cross(self, buyer: int, seller: int, s: int, d: int, sec: float, qty: int, price: float,
              event: int = -1) -> None:
        """Two internal clients trade with each other: two orders, two mirrored trades."""
        rng = self.rng
        sec = float(min(sec, SESSION_SEC - 10))
        first, second = (buyer, seller) if rng.random() < 0.5 else (seller, buyer)
        t2 = sec + float(rng.uniform(0.2, 3.0))
        fill_t = t2 + float(rng.uniform(0.05, 0.5))
        for c, t in ((first, sec), (second, t2)):
            side = "BUY" if c == buyer else "SELL"
            other = seller if c == buyer else buyer
            oi = self.book.add_order(client=c, trader=self.c_dealer[c], sym=s, side=side, qty=qty, price=price,
                                     day=d, t=t, otype="LIMIT", status="FILLED", filled=qty, end_t=fill_t,
                                     event=event)
            self.book.add_trade(order=oi, client=c, cp=other, sym=s, side=side, qty=qty, price=price, day=d,
                                t=fill_t, event=event)

    # ------------------------------------------------------- phase 1: schedule
    def _schedule(self) -> None:
        cfg, rng = self.cfg, self.rng
        D = cfg.n_days
        self.parents: list[dict] = []
        for d in range(D):
            for inst in self.insts:
                if rng.random() > 0.5:
                    continue
                for _ in range(1 + int(rng.random() < 0.3)):
                    s = int(rng.choice(self.large) if rng.random() < 0.8 else rng.choice(self.small))
                    dur = float(rng.uniform(20, 120) * 60)
                    start = float(rng.uniform(15 * 60, SESSION_SEC - dur - 30 * 60))
                    frac_adv = float(rng.uniform(0.01, 0.05))
                    impact = 100.0 * math.sqrt(frac_adv) * (1.6 if self.sym_segment[s] == "SMALL" else 1.0)
                    self.parents.append(dict(inst=inst, dealer=self.c_dealer[inst], s=s, d=d, start=start, dur=dur,
                                             side="BUY" if rng.random() < 0.5 else "SELL", frac_adv=frac_adv,
                                             impact_bps=impact, front_run=None))
        self.sched: dict[str, list[dict]] = {p: [] for p in PATTERNS}
        self.news: list[dict] = []
        linked_rings = [r for r in self.rings if r["linked"]]
        unlinked_rings = [r for r in self.rings if not r["linked"]]
        for d in range(D):
            for _ in range(rng.poisson(cfg.wash_per_day)):
                u = rng.random()
                if u < 0.55 and linked_rings:
                    variant, ring = "linked_accounts", linked_rings[rng.integers(len(linked_rings))]
                elif u < 0.8 and unlinked_rings:
                    variant, ring = "unlinked_accounts", unlinked_rings[rng.integers(len(unlinked_rings))]
                else:
                    variant, ring = "external_counterparty", self.rings[rng.integers(len(self.rings))]
                members = list(rng.choice(ring["members"], size=2, replace=False))
                s = int(rng.choice(self.small) if rng.random() < 0.6 else rng.choice(self.large))
                n_rt = int(rng.integers(1, cfg.wash_max_round_trips + 1))
                start = float(rng.uniform(10 * 60, SESSION_SEC - 100 * 60))
                self.sched["wash_trade"].append(dict(variant=variant, members=[int(x) for x in members], s=s, d=d,
                                                     start=start, n_rt=n_rt))
            for _ in range(rng.poisson(cfg.spoof_per_day)):
                ring = self.rings[rng.integers(len(self.rings))]
                a = int(rng.choice(ring["members"]))
                s = int(rng.choice(self.large) if rng.random() < 0.6 else rng.choice(self.small))
                n_cycles = int(rng.integers(1, 6))
                cycles = []
                t0 = float(rng.uniform(10 * 60, SESSION_SEC - 80 * 60))
                for _k in range(n_cycles):
                    cycles.append(dict(t0=t0, fake_side="BUY" if rng.random() < 0.5 else "SELL",
                                       n_layers=int(rng.integers(1, cfg.spoof_max_layers + 1)),
                                       push_bps=float(rng.uniform(3, 12)),
                                       size_mult=float(rng.uniform(1.5, cfg.spoof_size_mult_max))))
                    t0 += float(rng.uniform(90, 900))
                self.sched["spoofing"].append(dict(a=a, s=s, d=d, cycles=cycles))
            day_parents = [p for p in self.parents if p["d"] == d and p["front_run"] is None]
            n_fr = min(rng.poisson(cfg.front_run_per_day), len(day_parents))
            for idx in rng.choice(len(day_parents), size=n_fr, replace=False) if n_fr else []:
                p = day_parents[int(idx)]
                if p["start"] < 20 * 60:
                    continue
                f = self.fr_accounts[p["dealer"]]
                p["front_run"] = f
                self.sched["front_running"].append(dict(f=f, parent=p, s=p["s"], d=d,
                                                        lead=float(rng.uniform(60, 1500)),
                                                        via_dealer=bool(rng.random() < cfg.front_run_via_dealer_prob),
                                                        lag=float(rng.uniform(60, 1200)),
                                                        notional=float(np.exp(rng.normal(math.log(1.2e5), 0.5)))))
            if d <= D - 3 and rng.random() < cfg.pump_dump_start_prob:
                ring = self.rings[rng.integers(len(self.rings))]
                n_acc = int(min(rng.integers(2, 5), D - 1 - d))
                s = int(rng.choice(self.small))
                self.sched["pump_and_dump"].append(dict(members=[int(m) for m in ring["members"]], s=s, d0=d,
                                                        n_acc=n_acc, rise=float(rng.uniform(0.04, cfg.pump_rise_max)),
                                                        dump_start=float(rng.uniform(20 * 60, 150 * 60))))
            if rng.random() < cfg.news_per_day:
                s = int(rng.choice(self.small) if rng.random() < 0.5 else rng.choice(self.large))
                self.news.append(dict(s=s, d=d, m=int(rng.integers(30, 300)),
                                      jump=float(rng.uniform(0.04, 0.10)) * (1 if rng.random() < 0.75 else -1)))

    # ------------------------------------------------------ phase 2: prices
    def _prices(self) -> None:
        cfg, rng = self.cfg, self.rng
        S, D, M = len(self.sym_names), cfg.n_days, SESSION_MINUTES
        P = M + 1
        G = D * P
        E = np.zeros((S, G))

        def curve(s: int, xs: list[float], ys: list[float]) -> None:
            g0 = int(max(0, math.floor(xs[0])))
            g1 = G if ys[-1] != 0 else min(G, int(math.ceil(xs[-1])) + 1)
            if g0 >= g1:
                return
            E[s, g0:g1] += np.interp(np.arange(g0, g1), xs, ys)

        def g(d: int, sec: float) -> float:
            return d * P + sec / 60.0

        for p in self.parents:
            i = p["impact_bps"] * 1e-4 * (1 if p["side"] == "BUY" else -1)
            a, b = g(p["d"], p["start"]), g(p["d"], p["start"] + p["dur"])
            curve(p["s"], [a, b, b + 30], [0.0, i, 0.4 * i])
        for ev in self.sched["spoofing"]:
            for cy in ev["cycles"]:
                sgn = 1 if cy["fake_side"] == "BUY" else -1
                a = g(ev["d"], cy["t0"])
                curve(ev["s"], [a, a + 0.7, a + 3.5], [0.0, sgn * cy["push_bps"] * 1e-4, 0.0])
        for ev in self.sched["pump_and_dump"]:
            a = g(ev["d0"], 0)
            b = g(ev["d0"] + ev["n_acc"] - 1, M * 60)
            dump_d = ev["d0"] + ev["n_acc"]
            c0 = g(dump_d, ev["dump_start"])
            rise = math.log(1 + ev["rise"])
            curve(ev["s"], [a, b, c0, c0 + 60, c0 + 120], [0.0, rise, rise, -0.25 * rise, -0.35 * rise])
        for nv in self.news:
            a = g(nv["d"], nv["m"] * 60)
            j = math.log(1 + nv["jump"])
            curve(nv["s"], [a, a + 3], [0.0, j])

        u = 1.0 + 1.2 * ((np.arange(M) - M / 2) / (M / 2)) ** 2
        u = u / math.sqrt((u ** 2).mean())
        sig = self.sym_vol / math.sqrt(M)
        inc = rng.normal(size=(S, D, M)) * sig[:, None, None] * u[None, None, :]
        gaps = rng.normal(size=(S, D)) * (self.sym_vol * 0.35)[:, None]
        gaps[:, 0] = 0.0
        intraday = np.concatenate([np.zeros((S, D, 1)), np.cumsum(inc, axis=2)], axis=2)
        day_total = intraday[:, :, -1]
        open_lp = np.log(self.sym_base)[:, None] + np.cumsum(gaps, axis=1) + np.concatenate(
            [np.zeros((S, 1)), np.cumsum(day_total, axis=1)[:, :-1]], axis=1)
        self.lp = open_lp[:, :, None] + intraday + E.reshape(S, D, P)

        vol_shape = self.w_intraday * M
        base = self.sym_adv[:, None, None] / M * vol_shape[None, None, :]
        noise = np.exp(rng.normal(0, 0.45, size=(S, D, M)))
        boost = np.ones((S, D, M))
        for nv in self.news:
            boost[nv["s"], nv["d"], nv["m"]:] *= 3.0
        for ev in self.sched["pump_and_dump"]:
            for dd in range(ev["d0"], min(D, ev["d0"] + ev["n_acc"] + 1)):
                boost[ev["s"], dd, :] *= 2.0
        self.bar_volume = np.round(base * noise * boost).astype(np.int64)

    # -------------------------------------------------- phase 3: order flow
    def _retail_flow(self) -> None:
        rng, D = self.rng, self.cfg.n_days
        actors = self.retail + [m for r in self.rings for m in r["members"] if self.c_type[m] == "RETAIL"] + list(
            self.fr_accounts.values())
        for d in range(D):
            for c in actors:
                if rng.random() > self.c_pactive[c]:
                    continue
                n_sym = min(1 + rng.poisson(0.4), 3)
                syms = rng.choice(self.c_fav[c], size=n_sym, replace=False)
                for s in syms:
                    s = int(s)
                    side_bias = 0.55
                    for sec in self.sample_secs(1 + rng.poisson(1.0)):
                        self._retail_order(c, s, d, float(sec), "BUY" if rng.random() < side_bias else "SELL")
                    if rng.random() < 0.08:
                        # An ordinary intraday round trip: in and out the same day, same size.
                        self._round_trip(c, s, d)
                    fam = self.family_of.get(c)
                    if fam:
                        for m in fam:
                            if m != c and rng.random() < 0.3:
                                side = "BUY" if rng.random() < 0.55 else "SELL"
                                self._retail_order(m, s, d, float(self.sample_secs(1)[0]), side)
            # Family members sometimes move holdings between each other through the market.
            for fam in self.families:
                if rng.random() < 0.04:
                    a, b = rng.choice(fam, size=2, replace=False)
                    s = int(rng.choice(self.c_fav[int(a)]))
                    for sec in np.sort(self.sample_secs(int(rng.integers(1, 4)))):
                        qty = self.notional_qty(s, d, float(np.exp(rng.normal(math.log(5e4), 0.6))))
                        buyer, seller = (int(a), int(b)) if rng.random() < 0.7 else (int(b), int(a))
                        self.cross(buyer, seller, s, d, float(sec), qty, round_tick(self.mid(s, d, float(sec))))
            # A few retail investors build a position in a small cap over several days.
            if self.small.size and rng.random() < 0.5:
                c = int(rng.choice(self.retail))
                s = int(rng.choice(self.small))
                for dd in range(d, min(D, d + int(rng.integers(2, 5)))):
                    for sec in self.sample_secs(int(rng.integers(1, 4))):
                        self._retail_order(c, s, dd, float(sec), "BUY")
                    self.scenario_units.append((c, s, dd, "hn_multi_day_accumulation"))

    def _retail_order(self, c: int, s: int, d: int, sec: float, side: str, event: int = -1) -> None:
        rng = self.rng
        qty = self.notional_qty(s, d, self.c_size[c] * float(np.exp(rng.normal(math.log(3.5e4), 0.7))))
        if rng.random() < 0.06:
            # A bargain-hunting order far from the market, several times the usual size, that
            # the client pulls after a while. Legitimate, but it inflates cancelled size.
            self.order(c, s, d, sec, side, int(qty * rng.uniform(3, 10)), "LIMIT",
                       offset_bps=float(rng.uniform(25, 150)),
                       lifetime=float(rng.uniform(5, 90) if rng.random() < 0.5 else rng.uniform(90, 1200)),
                       p_fill=0.02, event=event)
        if rng.random() < 0.45:
            self.order(c, s, d, sec, side, qty, "MARKET", event=event)
        else:
            off = float(rng.uniform(-3, 30))
            life = float(max(30.0, rng.exponential(40 * 60)))
            self.order(c, s, d, sec, side, qty, "LIMIT", offset_bps=off, lifetime=life,
                       p_fill=0.92 * math.exp(-max(off, 0) / 15), event=event)

    def _day_trader_flow(self) -> None:
        rng, D = self.rng, self.cfg.n_days
        actors = self.day_traders + [m for r in self.rings for m in r["members"] if self.c_type[m] == "DAY_TRADER"]
        for d in range(D):
            for c in actors:
                if rng.random() > self.c_pactive[c]:
                    continue
                n_sym = int(rng.integers(1, 4))
                pool = np.concatenate([self.c_fav[c], rng.choice(self.large, size=2)])
                for s in rng.choice(pool, size=n_sym, replace=False):
                    s = int(s)
                    n_rt = int(rng.integers(3, 11)) if c in self.scalpers else int(rng.integers(1, 6))
                    for _ in range(n_rt):
                        self._round_trip(c, s, d)

    def _round_trip(self, c: int, s: int, d: int) -> None:
        rng = self.rng
        t0 = float(self.sample_secs(1, 0, SESSION_SEC - 30 * 60)[0])
        side = "BUY" if rng.random() < 0.6 else "SELL"
        other = "SELL" if side == "BUY" else "BUY"
        qty = self.notional_qty(s, d, self.c_size[c] * float(np.exp(rng.normal(math.log(1.0e5), 0.6))))
        if rng.random() < 0.35:
            life = float(rng.uniform(5, 180))
            _, ti = self.order(c, s, d, t0, side, qty, "LIMIT", offset_bps=float(rng.uniform(8, 30)),
                               lifetime=life, p_fill=0.3)
            if ti < 0:
                t0 = t0 + life
                self.order(c, s, d, t0, side, qty, "MARKET")
        else:
            self.order(c, s, d, t0, side, qty, "MARKET")
        scalper = c in self.scalpers
        hold_mean = 150 if scalper else 900
        hold = float(np.clip(np.exp(rng.normal(math.log(hold_mean), 0.8)), 20, SESSION_SEC - t0 - 60))
        t1 = t0 + hold
        pieces = [qty] if (scalper or rng.random() < 0.75) else [qty // 2, qty - qty // 2]
        for k, q in enumerate(pieces):
            tk = t1 + k * float(rng.uniform(30, 600))
            if rng.random() < 0.6:
                self.order(c, s, d, tk, other, q, "MARKET")
            else:
                life = float(rng.uniform(10, 300))
                _, ti = self.order(c, s, d, tk, other, q, "LIMIT", offset_bps=float(rng.uniform(-2, 10)),
                                   lifetime=life, p_fill=0.8)
                if ti < 0:
                    self.order(c, s, d, tk + life, other, q, "MARKET")

    def _market_maker_flow(self) -> None:
        rng, D = self.rng, self.cfg.n_days
        for d in range(D):
            for mm in self.mms:
                for s in self.mm_syms[mm]:
                    s = int(s)
                    # Quote refreshes: a small ladder on one or both sides, pulled after a few
                    # seconds. When one side fills the rest of the ladder is usually pulled too,
                    # which is legitimate and looks a lot like layering from the outside.
                    n_ev = rng.poisson(self.cfg.mm_quotes_per_symbol_day / 3.0)
                    price_ref = self.mid(s, d, SESSION_SEC / 2)
                    for sec in np.sort(self.sample_secs(n_ev)):
                        life = float(rng.exponential(6.0) + 0.3)
                        u = rng.random()
                        sides = ("BUY", "SELL") if u < 0.6 else (("BUY",) if u < 0.8 else ("SELL",))
                        for side in sides:
                            for lvl in range(int(rng.integers(1, 4))):
                                off = float(rng.uniform(0.5, 2.5) + 2.0 * lvl)
                                q = max(1, int(rng.uniform(1e5, 4e5) * (1 + 0.5 * lvl) / price_ref))
                                self.order(mm, s, d, float(sec) + 0.05 * lvl, side, q, "LIMIT", offset_bps=off,
                                           lifetime=life * float(rng.uniform(0.8, 1.2)),
                                           p_fill=0.3 * math.exp(-off / 3.0))

    def _institutional_flow(self) -> None:
        rng = self.rng
        for p in self.parents:
            s, d, inst = p["s"], p["d"], p["inst"]
            total = int(self.sym_adv[s] * p["frac_adv"])
            n_child = int(rng.integers(8, 26))
            secs = np.sort(p["start"] + rng.uniform(0, p["dur"], size=n_child))
            w = rng.dirichlet(np.ones(n_child) * 3)
            for k in range(n_child):
                q = max(1, int(total * w[k]))
                life = float(rng.uniform(30, 300))
                _, ti = self.order(inst, s, d, float(secs[k]), p["side"], q, "LIMIT",
                                   offset_bps=float(rng.uniform(-4, 4)), lifetime=life, p_fill=0.85)
                if ti < 0 and rng.random() < 0.6:
                    self.order(inst, s, d, float(secs[k]) + life, p["side"], q, "MARKET")
            # The dealer's advisory retail clients often buy the same names around the same time.
            followers = [c for c in self.retail if self.c_dealer[c] == p["dealer"]]
            if followers and rng.random() < 0.35:
                k = min(len(followers), int(rng.integers(1, 5)))
                for c in rng.choice(followers, size=k, replace=False):
                    sec = float(p["start"] + rng.uniform(-40 * 60, 60 * 60))
                    if 0 < sec < SESSION_SEC - 60:
                        self._retail_order(int(c), s, d, sec, p["side"])
                        if rng.random() < 0.3 and sec + 600 < SESSION_SEC - 60:
                            other = "SELL" if p["side"] == "BUY" else "BUY"
                            self._retail_order(int(c), s, d, float(rng.uniform(sec + 600, SESSION_SEC - 60)), other)

    def _news_flow(self) -> None:
        rng = self.rng
        normal_retail = [c for c in self.retail if self.c_role[c] != "ring"]
        for nv in self.news:
            s, d = nv["s"], nv["d"]
            side = "BUY" if nv["jump"] > 0 else "SELL"
            followers = rng.choice(normal_retail, size=min(len(normal_retail), int(rng.integers(12, 30))),
                                   replace=False)
            for c in followers:
                c = int(c)
                sec = nv["m"] * 60 + float(rng.uniform(120, 90 * 60))
                if sec >= SESSION_SEC - 120:
                    continue
                self._retail_order(c, s, d, sec, side)
                self.scenario_units.append((c, s, d, "hn_news_momentum"))
                if rng.random() < 0.4 and sec + 300 < SESSION_SEC - 60:
                    later = float(rng.uniform(sec + 300, SESSION_SEC - 60))
                    self._retail_order(c, s, d, later, "SELL" if side == "BUY" else "BUY")

    # ---------------------------------------------- phase 3b: manipulation
    def _new_event(self, pattern: str, variant: str, s: int, d0: int, d1: int, clients: list[int],
                   strength: float, params: dict) -> int:
        eid = len(self.events)
        self.events.append(dict(event_id=eid, pattern=pattern, variant=variant, s=s, d0=d0, d1=d1,
                                clients=clients, strength=strength, params=params))
        return eid

    def _inject_wash(self) -> None:
        rng = self.rng
        for ev in self.sched["wash_trade"]:
            a, b = ev["members"]
            s, d = ev["s"], ev["d"]
            clients = [a] if ev["variant"] == "external_counterparty" else [a, b]
            eid = self._new_event("wash_trade", ev["variant"], s, d, d, clients, ev["n_rt"],
                                  {"round_trips": ev["n_rt"]})
            qty = self.notional_qty(s, d, self.c_size[a] * float(np.exp(rng.normal(math.log(8e4), 0.5))))
            t = ev["start"]
            # Some wash rings fix the price of both legs; others just trade at the market each time.
            fixed_price = bool(rng.random() < self.cfg.wash_fixed_price_prob)
            for _ in range(ev["n_rt"]):
                q = qty if rng.random() < 0.6 else max(1, int(qty * rng.uniform(0.8, 1.2)))
                p1 = round_tick(self.mid(s, d, t))
                t2 = t + float(rng.uniform(20, 600))
                if fixed_price:
                    p2 = round_tick(p1 + TICK * int(rng.integers(-1, 2)))
                else:
                    p2 = round_tick(self.mid(s, d, t2))
                if ev["variant"] == "external_counterparty":
                    self.order(a, s, d, t, "BUY", q, "LIMIT", price=p1, p_fill=1.0,
                               fill_delay=float(rng.uniform(0.2, 2)),
                               event=eid)
                    self.order(a, s, d, t2, "SELL", q, "LIMIT", price=p2, p_fill=1.0,
                               fill_delay=float(rng.uniform(0.2, 2)), event=eid)
                else:
                    self.cross(a, b, s, d, t, q, p1, event=eid)
                    self.cross(b, a, s, d, t2, q, p2, event=eid)
                t = t2 + float(rng.uniform(30, 400))
                if t > SESSION_SEC - 400:
                    break

    def _inject_spoof(self) -> None:
        rng = self.rng
        for ev in self.sched["spoofing"]:
            a, s, d = ev["a"], ev["s"], ev["d"]
            eid = self._new_event("spoofing", "layering", s, d, d, [a], len(ev["cycles"]),
                                  {"cycles": len(ev["cycles"])})
            base_qty = self.notional_qty(s, d, self.c_size[a] * float(np.exp(rng.normal(math.log(4e4), 0.5))))
            for cy in ev["cycles"]:
                fake, real = cy["fake_side"], ("SELL" if cy["fake_side"] == "BUY" else "BUY")
                t0 = cy["t0"]
                t_fill_place = t0 + float(rng.uniform(5, 90))
                t_fill = t_fill_place + float(rng.uniform(0.3, 3))
                t_cancel = t_fill + float(rng.uniform(0.5, 45))
                for j in range(cy["n_layers"]):
                    tp = t0 + j * float(rng.uniform(0.1, 1.5))
                    q = int(base_qty * cy["size_mult"] * rng.uniform(0.8, 1.2))
                    self.order(a, s, d, tp, fake, q, "LIMIT", offset_bps=3.0 + 4.0 * j + float(rng.uniform(0, 2)),
                               lifetime=max(0.5, t_cancel - tp + float(rng.uniform(0, 1.5))),
                               p_fill=0.05, event=eid)
                sgn_real = 1 if real == "BUY" else -1
                px = round_tick(self.mid(s, d, t_fill_place) * (1 + sgn_real * 0.5e-4))
                self.order(a, s, d, t_fill_place, real, base_qty, "LIMIT", price=px, p_fill=1.0,
                           fill_delay=t_fill - t_fill_place, event=eid)

    def _inject_pump_dump(self) -> None:
        rng, D = self.rng, self.cfg.n_days
        for ev in self.sched["pump_and_dump"]:
            s, members = ev["s"], ev["members"]
            dump_d = ev["d0"] + ev["n_acc"]
            if dump_d >= D:
                continue
            eid = self._new_event("pump_and_dump", "ring", s, ev["d0"], dump_d, members, ev["rise"],
                                  {"accumulation_days": ev["n_acc"], "rise": round(ev["rise"], 4)})
            held = {m: 0 for m in members}
            for d in range(ev["d0"], dump_d + 1):
                # Ordinary investors chase the rising price; they are victims, not manipulators.
                victims = rng.choice(self.retail, size=min(len(self.retail), int(rng.integers(3, 10))), replace=False)
                for c in victims:
                    side = "SELL" if (d == dump_d and rng.random() < 0.5) else "BUY"
                    for sec in self.sample_secs(int(rng.integers(1, 3))):
                        self._retail_order(int(c), s, d, float(sec), side)
                    self.scenario_units.append((int(c), s, d, "hn_pump_bystander"))
                if d == dump_d:
                    break
                for m in members:
                    if rng.random() > 0.85:
                        continue
                    for sec in self.sample_secs(int(rng.integers(1, 7))):
                        q = self.notional_qty(s, d, self.c_size[m] * float(np.exp(rng.normal(math.log(6e4), 0.6))))
                        if rng.random() < 0.5:
                            _, ti = self.order(m, s, d, float(sec), "BUY", q, "MARKET", event=eid)
                        else:
                            _, ti = self.order(m, s, d, float(sec), "BUY", q, "LIMIT",
                                               offset_bps=float(rng.uniform(-3, 3)), p_fill=0.9,
                                               lifetime=float(rng.uniform(60, 900)), event=eid)
                        if ti >= 0:
                            held[m] += q
                    if len(members) > 1 and rng.random() < self.cfg.pump_circular_prob:
                        for _ in range(int(rng.integers(1, 4))):
                            other = int(rng.choice([x for x in members if x != m]))
                            sec = float(self.sample_secs(1)[0])
                            q = self.notional_qty(s, d, float(np.exp(rng.normal(math.log(1e5), 0.5))))
                            px = round_tick(self.mid(s, d, sec) * (1 + rng.uniform(0, 20) * 1e-4))
                            self.cross(m, other, s, d, sec, q, px, event=eid)
            for m in members:
                if held[m] <= 0:
                    continue
                n_pieces = int(rng.integers(2, 6))
                start = ev["dump_start"]
                secs = np.sort(start + rng.uniform(0, rng.uniform(20, 90) * 60, size=n_pieces))
                remaining = held[m]
                for k, sec in enumerate(secs):
                    q = remaining if k == n_pieces - 1 else max(1, held[m] // n_pieces)
                    remaining -= q
                    if q > 0:
                        self.order(m, s, dump_d, float(sec), "SELL", q, "MARKET", event=eid)

    def _inject_front_running(self) -> None:
        rng = self.rng
        for ev in self.sched["front_running"]:
            f, p, s, d = ev["f"], ev["parent"], ev["s"], ev["d"]
            eid = self._new_event("front_running", "dealer_linked_account", s, d, d, [f], ev["notional"],
                                  {"dealer": p["dealer"], "lead_s": round(ev["lead"], 1)})
            qty = self.notional_qty(s, d, self.c_size[f] * ev["notional"])
            t_in = p["start"] - ev["lead"]
            t_out = min(p["start"] + p["dur"] + ev["lag"], SESSION_SEC - 30)
            exit_side = "SELL" if p["side"] == "BUY" else "BUY"
            # Some front-runners route through the dealer's terminal, others through their own
            # online login, which hides the dealer link from the order record.
            trader = p["dealer"] if ev["via_dealer"] else "ONLINE"
            if rng.random() < 0.6:
                self.order(f, s, d, t_in, p["side"], qty, "MARKET", event=eid, trader=trader)
            else:
                self.order(f, s, d, t_in, p["side"], qty, "LIMIT", offset_bps=-2.0, p_fill=1.0,
                           fill_delay=float(rng.uniform(0.5, 20)), event=eid, trader=trader)
            self.order(f, s, d, t_out, exit_side, qty, "MARKET", event=eid, trader=trader)

    # ----------------------------------------- phase 4: internal crossings
    def _internal_crossings(self, tr: pd.DataFrame, od: pd.DataFrame) -> None:
        """Pair some ordinary buys and sells that happen close together as internal matches."""
        rng = self.rng
        cand = tr[(tr["event"] < 0) & (tr["cp"] == "EXT")].copy()
        cand["bucket"] = (cand["t"] // 120).astype(int)
        cand["r"] = rng.random(len(cand))
        cand = cand.sort_values(["sym", "day", "bucket", "side", "r"])
        cand["rank"] = cand.groupby(["sym", "day", "bucket", "side"]).cumcount()
        buys = cand[cand["side"] == "BUY"]
        sells = cand[cand["side"] == "SELL"]
        pairs = buys.reset_index().merge(sells.reset_index(), on=["sym", "day", "bucket", "rank"],
                                         suffixes=("_b", "_s"))
        pairs = pairs[pairs["client_b"] != pairs["client_s"]]
        # Thin small caps match internally far more often: the other side is often another client.
        p_cross = np.where(np.isin(pairs["sym"].to_numpy(), self.small), 0.9, self.cfg.internal_cross_prob * 4)
        pairs = pairs[rng.random(len(pairs)) < np.minimum(p_cross, 0.9)]
        for _, r in pairs.iterrows():
            ib, is_ = int(r["index_b"]), int(r["index_s"])
            q = int(min(r["qty_b"], r["qty_s"]))
            t = float(max(r["t_b"], r["t_s"]))
            px = float(r["price_b"])
            for i, other in ((ib, int(r["client_s"])), (is_, int(r["client_b"]))):
                tr.at[i, "cp"] = other
                tr.at[i, "qty"] = q
                tr.at[i, "t"] = t
                tr.at[i, "price"] = px
                oi = int(tr.at[i, "order"])
                od.at[oi, "filled"] = q
                od.at[oi, "end_t"] = t
                if q < od.at[oi, "qty"]:
                    od.at[oi, "status"] = "PARTIAL"

    # ------------------------------------------------------------- run all
    def run(self) -> "SimResult":
        self._build_symbols()
        self._build_clients()
        self._schedule()
        self._prices()
        self._retail_flow()
        self._day_trader_flow()
        self._market_maker_flow()
        self._institutional_flow()
        self._news_flow()
        self._inject_wash()
        self._inject_spoof()
        self._inject_pump_dump()
        self._inject_front_running()
        return self._finalize()

    def _ts(self, day: np.ndarray, t: np.ndarray) -> np.ndarray:
        opens = np.array([np.datetime64(datetime(x.year, x.month, x.day, 9, 15)) for x in self.days],
                         dtype="datetime64[ms]")
        return opens[day] + np.round(np.asarray(t, dtype=float) * 1000).astype(np.int64).astype("timedelta64[ms]")

    def _finalize(self) -> "SimResult":
        od = pd.DataFrame(self.book.o)
        tr = pd.DataFrame(self.book.tr)
        tr["cp"] = tr["cp"].astype(object)
        self._internal_crossings(tr, od)

        cid = np.array(self.client_ids)
        sym = np.array(self.sym_names)
        od["ts"] = self._ts(od["day"].to_numpy(), od["t"].to_numpy())
        od["end_ts"] = self._ts(od["day"].to_numpy(), od["end_t"].to_numpy())
        od = od.sort_values(["ts"], kind="stable")
        od["order_id"] = [f"O{i + 1:08d}" for i in range(len(od))]
        order_id_of = pd.Series(od["order_id"].to_numpy(), index=od.index)

        tr["ts"] = self._ts(tr["day"].to_numpy(), tr["t"].to_numpy())
        tr = tr.sort_values(["ts"], kind="stable")
        tr["trade_id"] = [f"T{i + 1:08d}" for i in range(len(tr))]

        orders = pd.DataFrame({
            "order_id": od["order_id"].to_numpy(),
            "client_id": cid[od["client"].to_numpy()],
            "trader_id": od["trader"].to_numpy(),
            "symbol": sym[od["sym"].to_numpy()],
            "side": od["side"].to_numpy(),
            "quantity": od["qty"].astype(np.int64).to_numpy(),
            "price": od["price"].astype(float).round(2).to_numpy(),
            "timestamp": od["ts"].to_numpy(),
            "order_type": od["otype"].to_numpy(),
            "status": od["status"].to_numpy(),
            "filled_quantity": od["filled"].astype(np.int64).to_numpy(),
            "end_time": od["end_ts"].to_numpy(),
        })
        cp = tr["cp"].to_numpy()
        cp_ids = np.array([c if isinstance(c, str) else cid[int(c)] for c in cp])
        trades = pd.DataFrame({
            "trade_id": tr["trade_id"].to_numpy(),
            "order_id": order_id_of.loc[tr["order"].to_numpy()].to_numpy(),
            "client_id": cid[tr["client"].to_numpy()],
            "counterparty_id": cp_ids,
            "symbol": sym[tr["sym"].to_numpy()],
            "side": tr["side"].to_numpy(),
            "quantity": tr["qty"].astype(np.int64).to_numpy(),
            "price": tr["price"].astype(float).round(2).to_numpy(),
            "timestamp": tr["ts"].to_numpy(),
        })
        rng = self.rng
        n_clients = len(self.c_type)
        created = [self.days[0] - timedelta(days=int(rng.integers(30, 2000))) for _ in range(n_clients)]
        clients = pd.DataFrame({
            "client_id": cid,
            "client_name": [f"Client {c[1:]}" for c in cid],
            "client_type": self.c_type,
            "risk_rating": rng.choice(["LOW", "MEDIUM", "HIGH"], size=n_clients, p=[0.6, 0.3, 0.1]),
            "account_status": "ACTIVE",
            "created_date": created,
            "dealer_id": self.c_dealer,
            "mobile_hash": [a["mobile"] for a in self.c_attrs],
            "email_hash": [a["email"] for a in self.c_attrs],
            "address_hash": [a["address"] for a in self.c_attrs],
        }).sort_values("client_id")
        symbols = pd.DataFrame({
            "symbol": self.sym_names, "segment": self.sym_segment, "tick_size": TICK,
            "half_spread_bps": self.half_spread.round(2),
        })
        S, D = len(self.sym_names), self.cfg.n_days
        bar_ts = self._ts(np.repeat(np.arange(D), SESSION_MINUTES + 1),
                          np.tile(np.arange(SESSION_MINUTES + 1) * 60.0, D))
        vol = np.concatenate([self.bar_volume, self.bar_volume[:, :, -1:]], axis=2)
        bars = pd.DataFrame({
            "symbol": np.repeat(sym, D * (SESSION_MINUTES + 1)),
            "ts": np.tile(bar_ts, S),
            "mid": np.round(np.exp(self.lp).reshape(-1), 4),
            "volume": vol.reshape(-1),
        })

        # ---- labels
        ev_rows, unit_rows = [], []
        day_str = [x.isoformat() for x in self.days]
        for ev in self.events:
            ev_rows.append(dict(event_id=ev["event_id"], pattern=ev["pattern"], variant=ev["variant"],
                                symbol=sym[ev["s"]], start_date=day_str[ev["d0"]], end_date=day_str[ev["d1"]],
                                clients=",".join(cid[c] for c in ev["clients"]), strength=float(ev["strength"]),
                                params=json.dumps(ev["params"])))
        ev_orders = od[od["event"] >= 0]
        eo = pd.DataFrame({"order_id": ev_orders["order_id"].to_numpy(), "event_id": ev_orders["event"].to_numpy()})
        pattern_of = {ev["event_id"]: ev["pattern"] for ev in self.events}
        seen = set()
        for c, s, d, e in zip(ev_orders["client"], ev_orders["sym"], ev_orders["day"], ev_orders["event"]):
            key = (int(c), int(s), int(d), int(e))
            if key in seen:
                continue
            seen.add(key)
            unit_rows.append(dict(client_id=cid[c], symbol=sym[s], trade_date=day_str[d], event_id=int(e),
                                  pattern=pattern_of[int(e)]))
        event_units = pd.DataFrame(unit_rows, columns=["client_id", "symbol", "trade_date", "event_id", "pattern"])
        scen = self._scenario_units(od, day_str, cid, sym)
        pos_keys = set(zip(event_units["client_id"], event_units["symbol"], event_units["trade_date"]))
        scen = scen[[k not in pos_keys for k in zip(scen["client_id"], scen["symbol"], scen["trade_date"])]]
        events = pd.DataFrame(ev_rows, columns=["event_id", "pattern", "variant", "symbol", "start_date", "end_date",
                                                "clients", "strength", "params"])
        return SimResult(cfg=self.cfg, clients=clients, symbols=symbols, orders=orders, trades=trades, bars=bars,
                         events=events, event_orders=eo, event_units=event_units, scenario_units=scen)

    def _scenario_units(self, od: pd.DataFrame, day_str: list[str], cid: np.ndarray, sym: np.ndarray) -> pd.DataFrame:
        rows = [(cid[c], sym[s], day_str[d], tag) for c, s, d, tag in self.scenario_units]
        normal = od[od["event"] < 0]
        units = normal[["client", "sym", "day"]].drop_duplicates()
        ctype = np.array(self.c_type)
        for c, s, d in units.itertuples(index=False):
            t = ctype[c]
            if t == "MARKET_MAKER":
                rows.append((cid[c], sym[s], day_str[d], "hn_market_maker"))
            elif t == "INSTITUTIONAL":
                rows.append((cid[c], sym[s], day_str[d], "hn_institutional_slicing"))
        dt = normal[np.isin(normal["client"], self.day_traders)]
        both = dt.groupby(["client", "sym", "day"])["side"].nunique()
        for (c, s, d), n in both.items():
            if n == 2:
                rows.append((cid[c], sym[s], day_str[d], "hn_intraday_round_trip"))
        fam_units = units[units["client"].isin(list(self.family_of))]
        fam_id = {m: i for i, fam in enumerate(self.families) for m in fam}
        fam_units = fam_units.assign(fam=fam_units["client"].map(fam_id))
        cnt = fam_units.groupby(["fam", "sym", "day"])["client"].transform("nunique")
        for c, s, d in fam_units[cnt >= 2][["client", "sym", "day"]].itertuples(index=False):
            rows.append((cid[c], sym[s], day_str[d], "hn_family_same_symbol"))
        parent_keys = {(p["dealer"], p["s"], p["d"]) for p in self.parents}
        dealer = np.array(self.c_dealer)
        for c, s, d in units.itertuples(index=False):
            if ctype[c] == "RETAIL" and (dealer[c], s, d) in parent_keys:
                rows.append((cid[c], sym[s], day_str[d], "hn_shared_dealer_overlap"))
        df = pd.DataFrame(rows, columns=["client_id", "symbol", "trade_date", "scenario"]).drop_duplicates()
        return df.reset_index(drop=True)


@dataclass
class SimResult:
    cfg: SimConfig
    clients: pd.DataFrame
    symbols: pd.DataFrame
    orders: pd.DataFrame
    trades: pd.DataFrame
    bars: pd.DataFrame
    events: pd.DataFrame
    event_orders: pd.DataFrame
    event_units: pd.DataFrame
    scenario_units: pd.DataFrame

    def summary(self) -> dict:
        return {
            "orders": int(len(self.orders)),
            "trades": int(len(self.trades)),
            "clients": int(len(self.clients)),
            "symbols": int(len(self.symbols)),
            "days": int(self.cfg.n_days),
            "events": {p: int((self.events["pattern"] == p).sum()) for p in PATTERNS},
            "positive_units": int(len(self.event_units[["client_id", "symbol", "trade_date"]].drop_duplicates())),
            "hard_negative_units": int(
                len(self.scenario_units[["client_id", "symbol", "trade_date"]].drop_duplicates())),
        }

    def write(self, out_dir: str | Path) -> Path:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        for name in (MARKET_DB, LABELS_DB):
            p = out / name
            if p.exists():
                p.unlink()
        meta = {"generator_version": GENERATOR_VERSION, "seed": self.cfg.seed, "config": asdict(self.cfg),
                "summary": self.summary()}
        con = duckdb.connect(str(out / MARKET_DB))
        try:
            for name, df in (("clients", self.clients), ("symbols", self.symbols), ("orders", self.orders),
                             ("trades", self.trades), ("market_bars", self.bars)):
                con.register("_df", df)
                con.execute(f"CREATE TABLE {name} AS SELECT * FROM _df")
                con.unregister("_df")
            con.execute("CREATE TABLE dataset_meta (key VARCHAR, value VARCHAR)")
            con.execute("INSERT INTO dataset_meta VALUES ('meta', ?)", [json.dumps(meta)])
        finally:
            con.close()
        con = duckdb.connect(str(out / LABELS_DB))
        try:
            for name, df in (("events", self.events), ("event_orders", self.event_orders),
                             ("event_units", self.event_units), ("scenario_units", self.scenario_units)):
                con.register("_df", df)
                con.execute(f"CREATE TABLE {name} AS SELECT * FROM _df")
                con.unregister("_df")
        finally:
            con.close()
        (out / "config.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return out


def simulate(cfg: SimConfig) -> SimResult:
    return MarketSimulator(cfg).run()
