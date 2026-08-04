"""
directed_sweep.py — directed CBS at scale.

The n=6 pilot in directed_hcbs.py showed compliance 18.9% -> 100% at 8.3%
cost overhead with 91% fewer nodes. Six instances is not enough to report:
one instance dominated the node counts, and prune's completeness was never
stressed.

This runs the same three modes over a configurable sweep and reports, per
map and overall: mean +/- std for cost overhead, node ratio, runtime, and
compliance, plus the rate at which prune fails on instances baseline solves.

Only instances where BASELINE succeeds within the time limit are counted, so
cost comparisons are always like-for-like. Prune failures on those instances
are reported separately rather than dropped.

Run from repo root. No API calls.
"""

import sys, os, json, time, random, argparse, statistics as stats
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from src.condicbs.solver.directed_hcbs import (
    HCBS_directed, load_instance, DELAY_PREDICATE_SRC,
)
from low_level_policy import manhattan_distance


def build_instances(maps, agent_counts, seeds_per_config):
    out = []
    for mp in maps:
        for na in agent_counts:
            for rs in range(seeds_per_config):
                out.append((mp, na, rs))
    return out


def run_one(mp, na, rs, pred, mode, record_only, max_time):
    m, agents = load_instance(mp, na, rs)
    t0 = time.time()
    sol, st = HCBS_directed(m, agents, use_pc=True, max_time=max_time,
                            heuristic_function=manhattan_distance,
                            predicate=pred, mode=mode, record_only=record_only)
    st["solved"] = sol is not False
    st["wall"] = time.time() - t0
    return st


def summarise(name, values):
    vals = [v for v in values if v is not None]
    if not vals:
        return f"  {name:22s} n/a"
    if len(vals) == 1:
        return f"  {name:22s} {vals[0]:.2f}  (n=1)"
    return (f"  {name:22s} {stats.mean(vals):7.2f} +/- {stats.stdev(vals):5.2f}"
            f"   median {stats.median(vals):7.2f}   (n={len(vals)})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--maps", default="room-32-32-4,maze-32-32-2,empty-32-32")
    ap.add_argument("--agents", default="8,12,16")
    ap.add_argument("--seeds", type=int, default=5,
                    help="seeds per (map, agent-count) pair")
    ap.add_argument("--max-time", type=float, default=30)
    ap.add_argument("--out", default="results/tables/directed_sweep.json")
    args = ap.parse_args()

    ns = {}
    exec(DELAY_PREDICATE_SRC, ns)
    pred = ns["priority"]

    maps = args.maps.split(",")
    counts = [int(x) for x in args.agents.split(",")]
    instances = build_instances(maps, counts, args.seeds)
    print(f"{len(instances)} instances x 3 modes, {args.max_time}s limit\n")

    rows = []
    baseline_solved = prune_failed = 0
    t_start = time.time()

    for k, (mp, na, rs) in enumerate(instances, 1):
        rec = {"map": mp, "n_agents": na, "rseed": rs}
        try:
            b = run_one(mp, na, rs, pred, "baseline", True, args.max_time)
        except Exception as e:
            print(f"  [{k}/{len(instances)}] {mp} {na}a r{rs}: setup error {e}")
            continue

        rec["baseline"] = b
        if not b["solved"]:
            print(f"  [{k}/{len(instances)}] {mp:16s} {na:3d}a r{rs}  "
                  f"baseline unsolved -- skipped")
            rows.append(rec)
            continue
        baseline_solved += 1
        if b["nodes_created"] < 5:
            print(f"  [{k}/{len(instances)}] {mp:16s} {na:3d}a r{rs}  "
                  f"trivial ({b['nodes_created']} nodes) -- skipped")
            rows.append(rec)
            continue

        pf = run_one(mp, na, rs, pred, "prefer", False, args.max_time)
        pr = run_one(mp, na, rs, pred, "prune", False, args.max_time)
        rec["prefer"], rec["prune"] = pf, pr
        if not pr["solved"]:
            prune_failed += 1

        over = (100 * (pr["cost"] - b["cost"]) / b["cost"]) if pr["solved"] else None
        noder = (100 * pr["nodes_created"] / b["nodes_created"]) if pr["solved"] else None
        print(f"  [{k}/{len(instances)}] {mp:16s} {na:3d}a r{rs}  "
              f"base {b['cost']:>5} / {b['nodes_created']:>5}n "
              f"comp {100*(b.get('compliance') or 0):3.0f}%  |  "
              f"prune " +
              (f"{pr['cost']:>5} (+{over:4.1f}%) / {noder:5.1f}%n comp 100%"
               if pr["solved"] else "FAILED"))
        rows.append(rec)

    elapsed = time.time() - t_start
    print(f"\ndone in {elapsed/60:.1f} min\n")

    # ---- aggregate ----
    def collect(pred_fn):
        return [pred_fn(r) for r in rows
                if r.get("baseline", {}).get("solved")
                and r.get("prune", {}).get("solved")]

    print("=== overall (instances where baseline and prune both solved) ===")
    def collect_comp(mode):
        return [100 * r[mode]["compliance"] for r in rows
                if r.get("baseline", {}).get("solved")
                and r.get("prune", {}).get("solved")
                and r.get(mode, {}).get("compliance") is not None]

    print(summarise("baseline compliance %", collect_comp("baseline")))
    print(summarise("prefer compliance %", collect_comp("prefer")))
    print(summarise("prune compliance %", collect_comp("prune")))
    print(summarise("prune cost overhead %",
                    collect(lambda r: 100 * (r["prune"]["cost"] - r["baseline"]["cost"])
                            / r["baseline"]["cost"])))
    print(summarise("prune nodes (% of base)",
                    collect(lambda r: 100 * r["prune"]["nodes_created"]
                            / r["baseline"]["nodes_created"])))
    print(summarise("prefer nodes (% of base)",
                    collect(lambda r: 100 * r["prefer"]["nodes_created"]
                            / r["baseline"]["nodes_created"])))
    print(summarise("prune runtime (% of base)",
                    collect(lambda r: 100 * r["prune"]["wall"]
                            / max(r["baseline"]["wall"], 1e-6))))

    print(f"\n  baseline solved:        {baseline_solved}/{len(instances)}")
    print(f"  prune failed on those:  {prune_failed}"
          f" ({100*prune_failed/baseline_solved:.1f}%)" if baseline_solved else "")

    # ---- per map ----
    print("\n=== per map ===")
    by_map = defaultdict(list)
    for r in rows:
        if r.get("baseline", {}).get("solved") and r.get("prune", {}).get("solved"):
            by_map[r["map"]].append(r)
    for mp, rs_ in by_map.items():
        comp = [100 * (r["baseline"].get("compliance") or 0) for r in rs_]
        over = [100 * (r["prune"]["cost"] - r["baseline"]["cost"]) / r["baseline"]["cost"]
                for r in rs_]
        nod = [100 * r["prune"]["nodes_created"] / r["baseline"]["nodes_created"]
               for r in rs_]
        print(f"  {mp:16s} n={len(rs_):3d}  "
              f"base compliance {stats.mean(comp):5.1f}%  "
              f"overhead {stats.mean(over):5.2f}%  "
              f"nodes {stats.mean(nod):6.1f}%")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(rows, f, indent=2, default=str)
    print(f"\nsaved {args.out}")


if __name__ == "__main__":
    main()