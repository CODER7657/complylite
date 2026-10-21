"""Generate a labeled, seeded surveillance dataset.

    python scripts/simulate.py                       # default preset, seed 42
    python scripts/simulate.py --preset tiny --out data/sim/tiny
    python scripts/simulate.py --days 60 --seed 7 --out data/sim/d60
"""
import argparse
import json
import time

import _bootstrap  # noqa: F401
from app.surveillance.paths import REPO_ROOT
from app.surveillance.simulator import PRESETS, make_config, simulate


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preset", default="default", choices=sorted(PRESETS))
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--days", type=int, default=None, help="number of trading days")
    ap.add_argument("--retail", type=int, default=None, help="number of retail clients")
    ap.add_argument("--out", default=None, help="output directory (default data/sim/<preset>)")
    args = ap.parse_args()

    cfg = make_config(args.preset, seed=args.seed, n_days=args.days, n_retail=args.retail)
    out = args.out or str(REPO_ROOT / "data" / "sim" / args.preset)
    t0 = time.perf_counter()
    res = simulate(cfg)
    res.write(out)
    summary = res.summary()
    summary["seconds"] = round(time.perf_counter() - t0, 1)
    summary["out"] = out
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
