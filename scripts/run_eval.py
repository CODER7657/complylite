"""Train and compare the detectors on a simulated dataset; write EVAL.md, charts and metrics JSON.

    python scripts/simulate.py                  # once, makes data/sim/default
    python scripts/run_eval.py                  # writes reports/EVAL.md, reports/metrics.json, reports/figures/
    python scripts/run_eval.py --data data/sim/hard --tag hard
    python scripts/run_eval.py --data data/sim/tiny --out reports_ci --smoke

The holdout block (the last trading days) is scored once per run. Nothing in this script picks
anything by looking at it: early stopping and the blend weight use the validation days only.
"""
import argparse
import json
from pathlib import Path

import _bootstrap  # noqa: F401
import numpy as np
from sklearn.metrics import precision_recall_curve

from app.surveillance import charts
from app.surveillance.features import FEATURES
from app.surveillance.paths import DEFAULT_DATASET_DIR, REPO_ROOT, REPORTS_DIR
from app.surveillance.pipeline import METHODS, run_evaluation
from app.surveillance.simulator import PATTERNS

LABEL = {"rules": "Rules only (fixed)", "isolation_forest": "IsolationForest", "gbm": "LightGBM",
         "rules_plus_gbm": "Rules + LightGBM"}


def fig_pr(rep, scores, path):
    import matplotlib.pyplot as plt
    df = rep["_frame"]
    part = df[df["split"] == "test"]
    fig, ax = plt.subplots(figsize=(6, 4))
    for i, m in enumerate(METHODS):
        p, r, _ = precision_recall_curve(part["y"], scores["test"][m])
        ax.plot(r, p, color=charts.SERIES[i], label=f"{LABEL[m]} (PR-AUC {rep['holdout']['methods'][m]['pr_auc']:.2f})",
                linestyle="--" if m == "rules_plus_gbm" else "-")
    base = part["y"].mean()
    ax.axhline(base, color=charts.MUTED, linewidth=1)
    ax.text(0.99, base + 0.02, f"base rate {base:.1%}", ha="right", color=charts.TEXT_2, fontsize=8)
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    ax.set_title("Precision-recall on holdout days (simulated)")
    ax.legend(loc="lower left")
    charts.save(fig, path)


def fig_queue(rep, path):
    import matplotlib.pyplot as plt
    h = rep["holdout"]
    names = [LABEL[m] for m in METHODS]
    fa = [h["methods"][m]["same_workload_as_rules"]["false_alarms_per_10k_trades"] for m in METHODS]
    pk = [h["methods"][m]["queue"]["precision_at_k_daily"] for m in METHODS]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.4))
    y = np.arange(len(METHODS))
    for ax, vals, title, fmt in ((axes[0], pk, f"Precision@{rep['k_per_day']} per day", "{:.2f}"),
                                 (axes[1], fa, "False alarms per 10k trades, same workload", "{:.0f}")):
        ax.barh(y, vals, color=[charts.SERIES[i] for i in range(len(METHODS))], height=0.6)
        for yi, v in zip(y, vals):
            ax.text(v, yi, " " + fmt.format(v), va="center", color=charts.TEXT, fontsize=8)
        ax.set_yticks(y, names)
        ax.invert_yaxis()
        ax.set_title(title)
        ax.grid(axis="y", visible=False)
    axes[0].axvline(h["oracle_precision_at_k"], color=charts.MUTED, linestyle=":", linewidth=1.2)
    axes[0].text(h["oracle_precision_at_k"] + 0.01, 0.5, "best possible", color=charts.TEXT_2, fontsize=8, va="center")
    axes[0].set_xlim(0, 1)
    axes[1].set_xlim(0, max(fa) * 1.25)
    charts.save(fig, path)


def fig_recall(rep, path):
    import matplotlib.pyplot as plt
    h = rep["holdout"]
    pats = [p for p in PATTERNS if h["positives_by_pattern"].get(p)]
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    w = 0.2
    x = np.arange(len(pats))
    for i, m in enumerate(METHODS):
        vals = [h["methods"][m]["queue"]["recall_by_pattern"].get(p, 0) for p in pats]
        ax.bar(x + (i - 1.5) * w, vals, width=w * 0.9, color=charts.SERIES[i], label=LABEL[m])
    ax.set_xticks(x, [p.replace("_", " ") for p in pats])
    ax.set_ylim(0, 1.05)
    ax.set_ylabel(f"Share caught in the daily top {rep['k_per_day']}")
    ax.set_title("Recall by manipulation pattern, holdout days (simulated)")
    ax.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    charts.save(fig, path)


def fig_importance(rep, path):
    import matplotlib.pyplot as plt
    items = list(rep["feature_importance"]["mean_abs_shap"].items())[:12]
    fig, ax = plt.subplots(figsize=(7, 4))
    y = np.arange(len(items))
    ax.barh(y, [v for _, v in items], color=charts.SERIES[0], height=0.6)
    ax.set_yticks(y, [FEATURES[f] for f, _ in items], fontsize=7.5)
    ax.invert_yaxis()
    ax.set_xlabel("Mean |SHAP contribution| (log-odds), validation and holdout units")
    ax.set_title("What the LightGBM ranking leans on")
    ax.grid(axis="y", visible=False)
    charts.save(fig, path)


def scen(t):
    return "ordinary activity" if t == "none" else t.replace("hn_", "").replace("_", " ")


def pct(x):
    return f"{100 * x:.0f}%"


def write_md(rep, path, fig_prefix, extra=None):
    h, v = rep["holdout"], rep["validation"]
    k = rep["k_per_day"]
    m = h["methods"]
    ds = rep["dataset"]
    s = ds["summary"]
    asf = h["rules_as_fired"]
    lines = []
    a = lines.append
    a("# Evaluation: ranking surveillance alerts on simulated trading data")
    a("")
    a("Generated by `scripts/run_eval.py`. Every number below comes from that script run on data from")
    a("`scripts/simulate.py`. **The data is simulated.** It shows the pipeline finds the patterns we planted")
    a("and how the methods compare on the same queue. It does not show how any of this would do on a real")
    a("broker's order book.")
    a("")
    a("## Setup")
    a("")
    a(f"- Dataset: seed {ds['seed']}, {s['days']} trading days, {s['clients']} clients, {s['symbols']} symbols,")
    a(f"  {s['orders']:,} orders, {s['trades']:,} trades. Config is in `{rel(ds['dir'])}/config.json`.")
    a("- Injected events: " + ", ".join(f"{n} {p.replace('_', ' ')}" for p, n in s["events"].items()) + ".")
    a("- Unit of review: one client trading one symbol on one day. A unit is a true alert if an injected")
    a("  manipulation touched it. Hard negatives (market makers, intraday scalpers, family accounts, news")
    a("  buyers, pump bystanders, dealer followers) are labeled 0 like everything else.")
    a(f"- Split by trading day, never at random: train {len(rep['split']['train'])} days, validation "
      f"{len(rep['split']['val'])} days, holdout {len(rep['split']['test'])} days "
      f"({rep['split']['test'][0]} to {rep['split']['test'][-1]}).")
    a(f"- Early stopping (best iteration {rep['model']['gbm_best_iteration']}) and the rules+model blend weight "
      f"({rep['model']['blend_weight_on_rules']}) were picked on validation days. The holdout was scored once.")
    a(f"- The analyst reviews about {k} alerts a day, so the queue metrics take the top {k} units per day.")
    a("")
    a(f"## Holdout results ({h['days']} days, {h['units']:,} units, {h['positive_units']} true alerts, "
      f"{h['trades']:,} trades)")
    a("")
    a(f"| Method | PR-AUC | Precision@{k} per day | False alarms per 10k trades (same workload) | " +
      " | ".join(f"Recall: {p.replace('_', ' ')}" for p in PATTERNS) + " |")
    a("|---|---|---|---|" + "---|" * len(PATTERNS))
    for meth in METHODS:
        q = m[meth]["queue"]
        sw = m[meth]["same_workload_as_rules"]
        a(f"| {LABEL[meth]} | {m[meth]['pr_auc']:.2f} | {q['precision_at_k_daily']:.2f} | "
          f"{sw['false_alarms_per_10k_trades']:.0f} | " +
          " | ".join(f"{q['recall_by_pattern'].get(p, 0):.2f}" for p in PATTERNS) + " |")
    a(f"| Best possible queue | 1.00 | {h['oracle_precision_at_k']:.2f} | "
      f"{h['oracle_same_workload_fa_10k']:.0f} | " + " | ".join("1.00" for _ in PATTERNS) + " |")
    a("")
    a(f"How to read it. PR-AUC ranks every unit on the holdout days. Precision@{k} and the recall columns use")
    a(f"a full queue: the top {k} units each day (for the rules, only units where a rule fired). False alarms")
    a("are counted at the same workload for everyone: each day every method raises as many alerts as the")
    a(f"rules did that day, capped at {k} (on average {h['rules_workload_per_day']:.0f} a day here), so a method")
    a("cannot look better just by raising fewer alerts.")
    a("")
    a(f"Precision@{k} cannot reach 1.0 here: the holdout averages "
      f"{h['positive_units'] / h['days']:.0f} true alerts a day, so a perfect queue of {k} is at most "
      f"{h['oracle_precision_at_k']:.2f} precise. Recall is the share of each pattern's units that made the "
      "daily queue.")
    a("")
    a(f"![Precision and false alarms]({fig_prefix}queue_quality.png)")
    a("")
    a(f"![Recall by pattern]({fig_prefix}recall_by_pattern.png)")
    a("")
    a(f"![PR curves]({fig_prefix}pr_curves.png)")
    a("")
    a("### What the rules do today")
    a("")
    a(f"Without a cap, the fixed rule pack raises {asf['alerts_per_day']:.0f} alerts a day on the holdout, against "
      f"a review capacity of {k}. {pct(asf['precision'])} of them are true, and it raises "
      f"{asf['false_alarms_per_10k_trades']:.0f} false alarms per 10,000 trades. Its recall is "
      + ", ".join(f"{asf['recall_by_pattern'].get(p, 0):.2f} for {p.replace('_', ' ')}" for p in PATTERNS)
      + ". The rules have nothing that looks at cancels, dealer flow or multi-day price context, so they barely "
      "see spoofing, front-running or pump-and-dump.")
    fa_scen = asf["false_alarm_share_by_scenario"]
    if fa_scen:
        top = sorted(fa_scen.items(), key=lambda x: -x[1])[:3]
        a("Most of its false alarms come from " + ", ".join(f"{scen(t)} ({pct(x)})"
                                                            for t, x in top) + ".")
    a("")
    a("### What changes with the model")
    a("")
    g = m["gbm"]["queue"]
    r = m["rules"]["queue"]
    r_sw, g_sw, rg_sw = (m[x]["same_workload_as_rules"] for x in ("rules", "gbm", "rules_plus_gbm"))
    a(f"- For the same number of alerts a day, the rules make {r_sw['false_alarms_per_10k_trades']:.0f} false alarms "
      f"per 10,000 trades, LightGBM {g_sw['false_alarms_per_10k_trades']:.0f} and rules + LightGBM "
      f"{rg_sw['false_alarms_per_10k_trades']:.0f}. The floor is {h['oracle_same_workload_fa_10k']:.0f}: with about "
      f"{h['positive_units'] / h['days']:.0f} true alerts a day, some slots must hold false ones.")
    a(f"- In the full top-{k} queue, LightGBM's precision@{k} is {g['precision_at_k_daily']:.2f} against "
      f"{r['precision_at_k_daily']:.2f} for the rules, and it catches all four patterns instead of one.")
    a(f"- IsolationForest, which never sees labels, reaches PR-AUC {m['isolation_forest']['pr_auc']:.2f}. Its "
      "false alarms are mostly legitimate but unusual clients: "
      + ", ".join(f"{scen(t)} ({pct(x)})" for t, x in
                  sorted(m['isolation_forest']['queue']['false_alarm_share_by_scenario'].items(),
                         key=lambda x: -x[1])[:3]) + ".")
    a(f"- The blend weight picked on validation was {rep['model']['blend_weight_on_rules']}: on this data the rule "
      "score adds nothing the model does not already know, so rules + LightGBM ranks almost like LightGBM alone.")
    a("")
    lo = h.get("leave_one_pattern_out")
    if lo:
        a("### A pattern the model was never shown")
        a("")
        a("The supervised scores above are close to perfect because the features were written with the four")
        a("planted patterns in mind and the model trained on labeled examples of each. To see what happens with")
        a("a new kind of manipulation, the script retrains LightGBM four times, each time removing one pattern from")
        a("the training and validation days, and checks how much of that pattern still reaches the holdout queue.")
        a("")
        a("| Pattern left out of training | Recall in the daily queue | PR-AUC for that pattern |")
        a("|---|---|---|")
        for p, x in lo.items():
            a(f"| {p.replace('_', ' ')} | {x['recall_in_queue']:.2f} | {x['pr_auc_this_pattern']:.2f} |")
        a("")
        a("This is the number to take seriously. A supervised ranker learns the manipulation it has seen; the")
        a("rules and the unsupervised score are the backstop for what it has not.")
        a("")
    if extra:
        a(extra)
        a("")
    a("## Validation days (used for early stopping and the blend weight)")
    a("")
    a(f"| Method | PR-AUC | Precision@{k} per day | False alarms per 10k trades (same workload) |")
    a("|---|---|---|---|")
    for meth in METHODS:
        q = v["methods"][meth]["queue"]
        sw = v["methods"][meth]["same_workload_as_rules"]
        a(f"| {LABEL[meth]} | {v['methods'][meth]['pr_auc']:.2f} | {q['precision_at_k_daily']:.2f} | "
          f"{sw['false_alarms_per_10k_trades']:.0f} |")
    a("")
    a("## Per-alert explanations")
    a("")
    a("Each queued alert carries its top LightGBM SHAP contributions (`pred_contrib=True`, no extra")
    a("dependency) plus the deterministic red flags in `app/surveillance/evidence.py`. Overall, the model")
    a("leans most on:")
    a("")
    a(f"![Feature importance]({fig_prefix}feature_importance.png)")
    a("")
    a("## Honest limits")
    a("")
    a("- The simulator and the features were written by the same person, so the features fit the planted")
    a("  patterns well. Real manipulation is rarer, messier and changes when people know what is watched.")
    a("- The simulator's difficulty knobs (event strength, hard-negative mix) were adjusted while looking at")
    a("  validation results, because the first version was trivially separable. Holdout days were not used.")
    a("- A broker only sees its own clients. Counterparties at other brokers show up as `EXT`, which the")
    a("  simulator models, but real exchange data has more structure than that.")
    a("- One seed, one split. Run `python scripts/simulate.py --seed N` and re-run this script to see the spread.")
    a("")
    a(f"Runtime: features and rules {rep['timing_seconds']['features_and_rules']} s, training "
      f"{rep['timing_seconds']['training']} s, whole script {rep['timing_seconds']['total']} s on a laptop CPU.")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def rel(path):
    try:
        return Path(path).resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return Path(path).as_posix()


def strip(rep):
    return {k: v for k, v in rep.items() if not k.startswith("_")}


def hard_section(hr, k):
    h = hr["holdout"]
    m = h["methods"]
    lines = ["### Harder variant", "",
             "`--preset hard` keeps the same market but makes the manipulation subtler: at most 4 wash round",
             "trips, fewer fixed-price legs, smaller and fewer spoof layers, most front-runners using their own",
             "online login instead of the dealer's terminal, smaller pumps with fewer circular trades. Full",
             "write-up in [EVAL_HARD.md](EVAL_HARD.md).", "",
             f"| Method | PR-AUC | Precision@{k} per day | False alarms per 10k trades (same workload) | "
             + " | ".join(f"Recall: {p.replace('_', ' ')}" for p in PATTERNS) + " |",
             "|---|---|---|---|" + "---|" * len(PATTERNS)]
    for meth in METHODS:
        q, sw = m[meth]["queue"], m[meth]["same_workload_as_rules"]
        lines.append(f"| {LABEL[meth]} | {m[meth]['pr_auc']:.2f} | {q['precision_at_k_daily']:.2f} | "
                     f"{sw['false_alarms_per_10k_trades']:.0f} | "
                     + " | ".join(f"{q['recall_by_pattern'].get(p, 0):.2f}" for p in PATTERNS) + " |")
    return chr(10).join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(DEFAULT_DATASET_DIR))
    ap.add_argument("--out", default=str(REPORTS_DIR))
    ap.add_argument("--tag", default="", help="suffix for output names, e.g. 'hard'")
    ap.add_argument("--k", type=int, default=50, help="alerts the analyst reviews per day")
    ap.add_argument("--smoke", action="store_true", help="tiny CI run: no leave-one-pattern-out, no charts")
    args = ap.parse_args()

    rep = run_evaluation(args.data, k=args.k, holdout=True, lopo=not args.smoke)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    sfx = f"_{args.tag}" if args.tag else ""
    (out / f"metrics{sfx}.json").write_text(json.dumps(strip(rep), indent=2, default=str), encoding="utf-8")
    if not args.smoke:
        charts.style()
        fig_dir = out / "figures"
        pre = f"eval{sfx}_"
        fig_pr(rep, rep["_scores"], fig_dir / f"{pre}pr_curves.png")
        fig_queue(rep, fig_dir / f"{pre}queue_quality.png")
        fig_recall(rep, fig_dir / f"{pre}recall_by_pattern.png")
        fig_importance(rep, fig_dir / f"{pre}feature_importance.png")
        extra = None
        hard = out / "metrics_hard.json"
        if not args.tag and hard.exists():
            extra = hard_section(json.loads(hard.read_text(encoding="utf-8")), args.k)
        write_md(rep, out / f"EVAL{sfx.upper()}.md", f"figures/{pre}", extra)
    h = rep["holdout"]
    print(json.dumps({m: {"pr_auc": h["methods"][m]["pr_auc"],
                          "p_at_k": h["methods"][m]["queue"]["precision_at_k_daily"],
                          "fa_10k": h["methods"][m]["queue"]["false_alarms_per_10k_trades"],
                          "recall": h["methods"][m]["queue"]["recall_by_pattern"]} for m in METHODS}, indent=1))
    print("timing", rep["timing_seconds"])


if __name__ == "__main__":
    main()
