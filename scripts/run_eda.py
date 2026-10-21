"""Exploratory look at the simulated data; writes reports/EDA.md and four charts.

    python scripts/run_eda.py [--data data/sim/default]

Labels are used here only to colour and split the charts, never as features.
"""
import argparse
import math
from pathlib import Path

import _bootstrap  # noqa: F401
import duckdb
import numpy as np
import pandas as pd

from app.surveillance import charts
from app.surveillance.paths import DEFAULT_DATASET_DIR, LABELS_DB, MARKET_DB, REPORTS_DIR


def q(con, sql):
    return con.execute(sql).df()


def otr_by_type(con, fig_path):
    import matplotlib.pyplot as plt
    df = q(con, """
        SELECT c.client_type, o.client_id, o.symbol, CAST(o.timestamp AS DATE) AS d,
               COUNT(*) AS n_orders, COUNT(*) FILTER (WHERE o.filled_quantity > 0) AS n_filled,
               COUNT(*) FILTER (WHERE o.status = 'CANCELLED') AS n_cancel
        FROM orders o JOIN clients c USING (client_id) GROUP BY ALL""")
    df["otr"] = df["n_orders"] / df["n_filled"].clip(lower=1)
    df["cancel_rate"] = df["n_cancel"] / df["n_orders"]
    order = ["RETAIL", "DAY_TRADER", "INSTITUTIONAL", "MARKET_MAKER"]
    fig, ax = plt.subplots(figsize=(7, 3.6))
    data = [np.log10(df.loc[df["client_type"] == t, "otr"]) for t in order]
    bp = ax.boxplot(data, orientation="horizontal", widths=0.5, patch_artist=True, showfliers=False)
    for i, b in enumerate(bp["boxes"]):
        b.set_facecolor(charts.SERIES[i])
        b.set_alpha(0.85)
        b.set_edgecolor(charts.SURFACE)
    for med in bp["medians"]:
        med.set_color(charts.TEXT)
    ax.set_yticks(range(1, 5), [t.replace("_", " ").title() for t in order])
    ax.set_xticks([0, 0.5, 1, 1.5], ["1", "3", "10", "32"])
    ax.set_xlabel("Orders per filled order (log scale), per client-symbol-day")
    ax.set_title("Order-to-trade ratio by client type")
    ax.grid(axis="y", visible=False)
    charts.save(fig, fig_path)
    stats = df.groupby("client_type").agg(median_otr=("otr", "median"), cancel_rate=("cancel_rate", "mean"),
                                          units=("otr", "size"))
    return stats


def cancel_clustering(con, fig_path):
    """Seconds from a client's own fill to the cancel of its opposite-side resting orders."""
    import matplotlib.pyplot as plt
    df = q(con, """
        WITH c AS (
            SELECT o.order_id, o.client_id, o.symbol, o.side, o.quantity, o.end_time
            FROM orders o WHERE o.status = 'CANCELLED'
        ),
        f AS (SELECT client_id, symbol, side, timestamp, quantity FROM trades)
        SELECT c.order_id, c.client_id, c.symbol, CAST(c.end_time AS DATE) AS trade_date,
               MIN(date_diff('millisecond', f.timestamp, c.end_time)) / 1000.0 AS secs_after_fill,
               MAX(c.quantity) / MAX(f.quantity) AS size_vs_fill
        FROM c JOIN f ON f.client_id = c.client_id AND f.symbol = c.symbol AND f.side <> c.side
         AND f.timestamp <= c.end_time AND f.timestamp >= c.end_time - INTERVAL 60 SECOND
        GROUP BY ALL""")
    df["trade_date"] = df["trade_date"].astype(str)
    lab = q(con, "SELECT client_id, symbol, CAST(trade_date AS VARCHAR) AS trade_date, MIN(pattern) AS pattern "
                 "FROM lab.event_units GROUP BY ALL")
    ctype = q(con, "SELECT client_id, client_type FROM clients")
    df = df.merge(lab, on=["client_id", "symbol", "trade_date"], how="left").merge(ctype, on="client_id")
    df["group"] = np.where(df["pattern"] == "spoofing", "spoofing",
                           np.where(df["client_type"] == "MARKET_MAKER", "market maker", "everyone else"))
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
    bins = np.linspace(0, 60, 31)
    groups = ["market maker", "spoofing", "everyone else"]
    for i, g in enumerate(groups):
        sub = df[df["group"] == g]
        if len(sub):
            axes[0].hist(sub["secs_after_fill"], bins=bins, density=True, histtype="step", linewidth=2,
                         color=charts.SERIES[i], label=f"{g} (n={len(sub):,})")
    axes[0].set_xlabel("Seconds from own opposite-side fill to cancel")
    axes[0].set_ylabel("Density")
    axes[0].set_title("When do cancels follow a fill?")
    axes[0].legend()
    sb = np.linspace(-1.5, 1.5, 31)
    for i, g in enumerate(groups):
        sub = df[df["group"] == g]
        if len(sub):
            axes[1].hist(np.log10(sub["size_vs_fill"].clip(lower=0.03)), bins=sb, density=True, histtype="step",
                         linewidth=2, color=charts.SERIES[i], label=g)
    axes[1].set_xticks([-1, 0, 1], ["0.1x", "1x", "10x"])
    axes[1].set_xlabel("Cancelled order size vs the fill it followed")
    axes[1].set_title("How big is what gets cancelled?")
    charts.save(fig, fig_path)
    return df.groupby("group").agg(n=("secs_after_fill", "size"), median_secs=("secs_after_fill", "median"),
                                   median_size_ratio=("size_vs_fill", "median"))


def pair_network(con, fig_path):
    import matplotlib.pyplot as plt
    pairs = q(con, """
        SELECT LEAST(client_id, counterparty_id) AS a, GREATEST(client_id, counterparty_id) AS b,
               COUNT(*) / 2 AS n_trades, COUNT(DISTINCT CAST(timestamp AS DATE)) AS days
        FROM trades WHERE counterparty_id <> 'EXT' GROUP BY ALL""")
    links = q(con, """
        SELECT DISTINCT LEAST(a.client_id, b.client_id) AS a, GREATEST(a.client_id, b.client_id) AS b
        FROM clients a JOIN clients b ON a.client_id < b.client_id
         AND (a.mobile_hash = b.mobile_hash OR a.email_hash = b.email_hash OR a.address_hash = b.address_hash)""")
    links["linked"] = True
    ev = q(con, "SELECT clients FROM lab.events WHERE pattern IN ('wash_trade', 'pump_and_dump')")
    ring_pairs = set()
    for cl in ev["clients"]:
        m = sorted(cl.split(","))
        ring_pairs |= {(x, y) for i, x in enumerate(m) for y in m[i + 1:]}
    pairs = pairs.merge(links, on=["a", "b"], how="left")
    pairs["linked"] = pairs["linked"].notna()
    pairs["ring"] = [(a, b) in ring_pairs for a, b in zip(pairs["a"], pairs["b"])]
    pairs["kind"] = np.where(pairs["ring"], "manipulation ring",
                             np.where(pairs["linked"], "linked, legitimate (family)", "unlinked, legitimate"))
    strong = pairs[pairs["n_trades"] >= 3]
    nodes = sorted(set(strong["a"]) | set(strong["b"]))
    ang = {n: 2 * math.pi * i / max(1, len(nodes)) for i, n in enumerate(nodes)}
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.6), gridspec_kw={"width_ratios": [1.1, 1]})
    ax = axes[0]
    colors = {"manipulation ring": charts.SERIES[1], "linked, legitimate (family)": charts.SERIES[0],
              "unlinked, legitimate": charts.MUTED}
    for kind in ("unlinked, legitimate", "linked, legitimate (family)", "manipulation ring"):
        sub = strong[strong["kind"] == kind]
        for a, b, n in zip(sub["a"], sub["b"], sub["n_trades"]):
            xa, ya = math.cos(ang[a]), math.sin(ang[a])
            xb, yb = math.cos(ang[b]), math.sin(ang[b])
            ax.plot([xa, xb], [ya, yb], color=colors[kind], linewidth=0.5 + 2.5 * min(1, n / 30), alpha=0.8)
        ax.plot([], [], color=colors[kind], label=f"{kind} ({len(sub)})")
    ax.scatter([math.cos(ang[n]) for n in nodes], [math.sin(ang[n]) for n in nodes], s=8, color=charts.TEXT_2,
               zorder=3)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("Client pairs with 3+ internal trades (40 days)")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.18), fontsize=7.5)
    ax2 = axes[1]
    for i, kind in enumerate(("unlinked, legitimate", "linked, legitimate (family)", "manipulation ring")):
        sub = pairs[pairs["kind"] == kind]
        ax2.scatter(sub["days"] + np.random.default_rng(i).uniform(-0.2, 0.2, len(sub)), sub["n_trades"], s=10,
                    color=colors[kind], alpha=0.7, label=kind)
    ax2.set_yscale("log")
    ax2.set_xlabel("Days the pair traded with each other")
    ax2.set_ylabel("Trades between the pair (log)")
    ax2.set_title("Repetition separates rings from chance matches")
    charts.save(fig, fig_path)
    return pairs.groupby("kind").agg(pairs=("n_trades", "size"), median_trades=("n_trades", "median"),
                                     median_days=("days", "median"))


def impact_windows(con, fig_path):
    import matplotlib.pyplot as plt
    # Spoofing: align on each cycle's first fake order; sign by the fake side.
    spoof = q(con, """
        WITH eo AS (
            SELECT o.order_id, o.symbol, o.side, o.timestamp, o.quantity, o.filled_quantity, eo.event_id
            FROM orders o JOIN lab.event_orders eo USING (order_id) JOIN lab.events e USING (event_id)
            WHERE e.pattern = 'spoofing' AND o.status = 'CANCELLED'
        )
        SELECT event_id, symbol, side, MIN(timestamp) AS t0 FROM eo
        GROUP BY event_id, symbol, side, time_bucket(INTERVAL 5 MINUTE, timestamp)""")
    fr = q(con, """
        SELECT eo.event_id, o.symbol, o.side, o.timestamp AS t0
        FROM orders o JOIN lab.event_orders eo USING (order_id) JOIN lab.events e USING (event_id)
        WHERE e.pattern = 'front_running'
        QUALIFY ROW_NUMBER() OVER (PARTITION BY eo.event_id ORDER BY o.timestamp) = 1""")
    base = q(con, """
        SELECT t.symbol, t.side, t.timestamp AS t0 FROM trades t JOIN clients c USING (client_id)
        WHERE c.client_type = 'RETAIL' USING SAMPLE 400 ROWS (reservoir, 7)""")
    bars = q(con, "SELECT symbol, ts, mid FROM market_bars")
    bars = {s: g.set_index("ts")["mid"] for s, g in bars.groupby("symbol")}

    def path(events, offsets_min):
        out = []
        for s, side, t0 in zip(events["symbol"], events["side"], events["t0"]):
            ser = bars[s]
            t0 = pd.Timestamp(t0).floor("min")
            if t0 not in ser.index:
                continue
            p0 = ser.loc[t0]
            sgn = 1 if side == "BUY" else -1
            row = []
            for m in offsets_min:
                t = t0 + pd.Timedelta(minutes=int(m))
                row.append(sgn * (ser.loc[t] / p0 - 1) * 1e4 if (t in ser.index and t.date() == t0.date())
                           else np.nan)
            out.append(row)
        return np.nanmean(np.array(out, dtype=float), axis=0), len(out)

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
    off_s = np.arange(-3, 8)
    sp, n_sp = path(spoof, off_s)
    bs, n_bs = path(base, off_s)
    axes[0].plot(off_s, sp, color=charts.SERIES[1], marker="o", markersize=4, label=f"spoof cycles (n={n_sp})")
    axes[0].plot(off_s, bs, color=charts.MUTED, marker="o", markersize=4, label=f"random retail trades (n={n_bs})")
    axes[0].axvline(0, color=charts.GRID, linewidth=1)
    axes[0].set_xlabel("Minutes from the first layered order")
    axes[0].set_ylabel("Mid move in the layered side's direction (bps)")
    axes[0].set_title("Spoofing: price leans toward the fake side, then returns")
    axes[0].legend()
    off_f = np.arange(-30, 121, 10)
    fp_, n_fr = path(fr, off_f)
    bf, _ = path(base, off_f)
    axes[1].plot(off_f, fp_, color=charts.SERIES[0], marker="o", markersize=4,
                 label=f"front-running entries (n={n_fr})")
    axes[1].plot(off_f, bf, color=charts.MUTED, marker="o", markersize=4, label="random retail trades")
    axes[1].axvline(0, color=charts.GRID, linewidth=1)
    axes[1].set_xlabel("Minutes from the front-runner's entry")
    axes[1].set_ylabel("Mid move in the entry's direction (bps)")
    axes[1].set_title("Front-running: the big order lands after the entry")
    axes[1].legend()
    charts.save(fig, fig_path)
    i5 = list(off_s).index(1)
    i60 = list(off_f).index(60)
    return {"spoof_1m_bps": float(sp[i5]), "base_1m_bps": float(bs[i5]), "fr_60m_bps": float(fp_[i60]),
            "base_60m_bps": float(bf[i60]), "n_spoof": n_sp, "n_fr": n_fr}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DEFAULT_DATASET_DIR))
    ap.add_argument("--out", default=str(REPORTS_DIR))
    args = ap.parse_args()
    ds, out = Path(args.data), Path(args.out)
    fig_dir = out / "figures"
    charts.style()
    con = duckdb.connect(str(ds / MARKET_DB), read_only=True)
    con.execute(f"ATTACH '{(ds / LABELS_DB).as_posix()}' AS lab (READ_ONLY)")
    otr = otr_by_type(con, fig_dir / "eda_order_to_trade.png")
    canc = cancel_clustering(con, fig_dir / "eda_cancel_clustering.png")
    net = pair_network(con, fig_dir / "eda_pair_network.png")
    imp = impact_windows(con, fig_dir / "eda_price_impact.png")
    con.close()

    def o(t, col):
        return otr.loc[t, col]

    L = []
    a = L.append
    a("# Exploratory analysis of the simulated order book")
    a("")
    a("Generated by `scripts/run_eda.py` from `data/sim/default` (seed 42). **All data is simulated.** Labels are")
    a("used here only to colour the charts. The point is to check that the simulator behaves the way the")
    a("detectors assume, and to see which signals overlap with legitimate trading.")
    a("")
    a("## 1. Order-to-trade ratios")
    a("")
    a("![Order-to-trade ratio](figures/eda_order_to_trade.png)")
    a("")
    a(f"Market makers send a median of {o('MARKET_MAKER', 'median_otr'):.1f} orders per fill and cancel "
      f"{o('MARKET_MAKER', 'cancel_rate'):.0%} of their orders. Retail clients sit at "
      f"{o('RETAIL', 'median_otr'):.1f} orders per fill ({o('RETAIL', 'cancel_rate'):.0%} cancelled), intraday "
      f"traders at {o('DAY_TRADER', 'median_otr'):.1f}. A high cancel rate on its own mostly finds market makers,")
    a("which is why it is a poor alert by itself and why the unsupervised IsolationForest score keeps")
    a("surfacing them.")
    a("")
    a("## 2. Cancel clustering")
    a("")
    a("![Cancel clustering](figures/eda_cancel_clustering.png)")
    a("")

    def c(g, col):
        return canc.loc[g, col] if g in canc.index else float("nan")
    a("Market makers and spoofers both cancel resting orders shortly after a fill on the other side. Market")
    a(f"makers pull the rest of a ladder fast (median {c('market maker', 'median_secs'):.1f} s); spoofers take longer "
      f"(median {c('spoofing', 'median_secs'):.1f} s), but both land inside the same short window, and market "
      f"makers produce {int(c('market maker', 'n')):,} such cancels against {int(c('spoofing', 'n')):,} for "
      "spoofers. A timing rule alone would bury the spoofers. Size separates them more cleanly: what a spoofer "
      f"cancels is a median {c('spoofing', 'median_size_ratio'):.1f}x the fill it followed, against "
      f"{c('market maker', 'median_size_ratio'):.1f}x for a market maker.")
    a("That is why `cancel_fill_size_ratio` and the placed-versus-filled imbalance matter more than the raw")
    a("cancel count.")
    a("")
    a("## 3. Client-pair network")
    a("")
    a("![Pair network](figures/eda_pair_network.png)")
    a("")

    def nt(k, col):
        return net.loc[k, col] if k in net.index else float("nan")
    a(f"Internal matches between clients happen by chance all the time: {int(nt('unlinked, legitimate', 'pairs')):,} "
      f"unlinked legitimate pairs traded with each other at least once, "
      f"a median of {nt('unlinked, legitimate', 'median_trades'):.0f} trade on "
      f"{nt('unlinked, legitimate', 'median_days'):.0f} "
      f"day. Manipulation-ring pairs ({int(nt('manipulation ring', 'pairs'))}) trade with each other a median of "
      f"{nt('manipulation ring', 'median_trades'):.0f} times over {nt('manipulation ring', 'median_days'):.0f} days. "
      f"The {int(nt('linked, legitimate (family)', 'pairs'))} family pairs that traded with each other did so a "
      f"median of {nt('linked, legitimate (family)', 'median_trades'):.0f} times on "
      f"{nt('linked, legitimate (family)', 'median_days'):.0f} day, usually moving holdings between relatives. So")
    a("being linked is weak evidence on its own; repeated trading between the same two accounts over several")
    a("days is much stronger.")
    a("")
    a("## 4. Price impact around injected windows")
    a("")
    a("![Price impact](figures/eda_price_impact.png)")
    a("")
    a(f"One minute after a spoofer starts layering, the mid has moved {imp['spoof_1m_bps']:.1f} bps toward the fake "
      f"side on average (random retail trades: {imp['base_1m_bps']:.1f} bps), then drifts back once the orders are "
      f"pulled. An hour after a front-runner's entry the price has moved {imp['fr_60m_bps']:.0f} bps in its favour "
      f"(baseline {imp['base_60m_bps']:.1f} bps), because the institution's order lands in between. These moves "
      "are small next to normal volatility, which is why the price-impact features help but cannot carry a "
      "case alone.")
    a("")
    a("## What this means for the detectors")
    a("")
    a("- No single signal is clean. Cancels point at market makers, internal matches happen by chance, and")
    a("  linked accounts are usually families. The signal is in combinations: size plus timing for spoofing,")
    a("  repetition plus near-zero price change for wash trades, timing against dealer flow for front-running.")
    a("- These are properties of the simulator. They match how the patterns are usually described, but real")
    a("  data will be noisier and the overlaps larger.")
    (out / "EDA.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(otr, canc, net, imp, sep="\n")


if __name__ == "__main__":
    main()
