"""
pc_ablation.py — is width degeneracy a selection effect?

CBS+PC prioritises cardinal conflicts, and a cardinal conflict is by
definition width-one for both agents. So the width-one rate we measure may
reflect WHICH conflicts CBS+PC chooses to split on rather than the width
distribution of conflicts in general.

To separate the two we need widths measured independently of the search that
selected the conflict. This script runs each instance twice:

  use_pc=True   CBS+PC. Conflict selection prefers cardinal conflicts.
  use_pc=False  Plain CBS. Selection takes the first conflict found.

In both cases widths are recomputed AFTER the fact, by re-running the low
level with use_pc=True on the constraint set recorded at that conflict. So
the measurement instrument is identical in both arms; only conflict selection
differs.

Matched on the same instances, so instance difficulty is controlled.

Place at src/condicbs/analysis/pc_ablation.py, run from repo root.
"""

import sys, os, json, collections, argparse, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../external/cbs_icbs"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from low_level_policy import AStar, manhattan_distance
from src.condicbs.solver.instrumented_hcbs import HCBS_instrumented
from src.condicbs.solver.pbs import load_instance


def width_for(MAPF_instance, agent, constraints, t):
    """Recompute width for one agent at timestep t under a given constraint
    set, using the PC low level regardless of how the search was run."""
    try:
        res = AStar(MAPF_instance, agent, use_pc=True,
                    constraints=constraints,
                    heuristic_function=manhattan_distance)
    except Exception:
        return None
    if res is None or len(res) < 3 or not res[2]:
        return None
    w = res[2]
    if not w:
        return None
    return w.get(min(t, max(w.keys())))


def measure(MAPF_instance, agents, use_pc, max_time, cap):
    id_to_agent = {a.id: a for a in agents}
    log = []
    HCBS_instrumented(MAPF_instance, agents, use_pc=use_pc, max_time=max_time,
                      heuristic_function=manhattan_distance, conflict_log=log)

    widths = collections.Counter()
    missing = 0
    # cap the number of conflicts we re-measure; each costs a full A* call
    step = max(1, len(log) // cap) if cap and len(log) > cap else 1
    sampled = log[::step][:cap] if cap else log

    for e in sampled:
        ag = e["conflicting_agents"]
        if len(ag) != 2:
            continue
        t = (e["vertex_and_time"][-1] if e["conflict_type"] == "v"
             else e["vertex_and_time"][0][-1])
        cons = set(tuple(c) for c in e.get("branch_constraints", []))
        for aid in ag:
            w = width_for(MAPF_instance, id_to_agent[aid], cons, t)
            if w is None:
                missing += 1
            else:
                widths[w] += 1
    return widths, missing, len(log), len(sampled)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-time", type=float, default=30)
    ap.add_argument("--cap", type=int, default=60,
                    help="conflicts re-measured per run (each costs an A* call)")
    args = ap.parse_args()

    instances = [
        ("room-32-32-4", 12, 0), ("room-32-32-4", 12, 2),
        ("room-32-32-4", 12, 3), ("room-32-32-4", 16, 1),
        ("room-32-32-4", 16, 2), ("empty-32-32", 12, 0),
        ("empty-32-32", 16, 3), ("empty-32-32", 20, 5),
    ]

    totals = {True: collections.Counter(), False: collections.Counter()}
    miss = {True: 0, False: 0}
    rows = []

    for mp, na, rs in instances:
        row = {"instance": f"{mp}_{na}a_r{rs}"}
        for use_pc in (True, False):
            m, agents = load_instance(mp, na, rs)
            t0 = time.time()
            w, ms, n_log, n_s = measure(m, agents, use_pc, args.max_time, args.cap)
            tot = sum(w.values())
            pct = 100 * w[1] / tot if tot else None
            totals[use_pc] += w
            miss[use_pc] += ms
            row[f"pc={use_pc}"] = {
                "conflicts_logged": n_log, "sampled": n_s,
                "measured": tot, "missing": ms, "width1_pct": pct,
                "secs": round(time.time() - t0, 1),
            }
            print(f"  {row['instance']:24s} pc={str(use_pc):5s} "
                  f"conflicts={n_log:5d} measured={tot:4d} "
                  f"width1={(f'{pct:5.1f}%' if pct is not None else '   n/a')} "
                  f"({time.time()-t0:.0f}s)")
        rows.append(row)
        print()

    print("=== pooled ===")
    for use_pc in (True, False):
        w = totals[use_pc]
        tot = sum(w.values())
        if not tot:
            print(f"  use_pc={use_pc}: no measurements")
            continue
        print(f"  use_pc={use_pc}: {tot} measured, {miss[use_pc]} missing")
        for v, n in sorted(w.items())[:6]:
            print(f"    width {v}: {n} ({100*n/tot:.1f}%)")

    os.makedirs("results/tables", exist_ok=True)
    with open("results/tables/pc_ablation.json", "w") as f:
        json.dump(rows, f, indent=2, default=str)
    print("\nsaved results/tables/pc_ablation.json")


if __name__ == "__main__":
    main()