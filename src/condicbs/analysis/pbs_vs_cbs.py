"""
pbs_vs_cbs.py — do the CBS findings hold in a solver without a constraint tree?

CBS reference numbers (Sections 4.1-4.3):
  delay asymmetry            69.8% of conflicts
  delay vs route-length      47.7% disagreement
  width == 1                 99.3% of valid observations
  constraint count vs delay  99.5% agreement
"""
import json, glob, os, collections

logs = sorted(glob.glob("results/pbs_logs/*.json"))
logs = [p for p in logs if not os.path.basename(p).startswith("_")]

tot = asym = disagree_route = 0
widths = collections.Counter()
w_missing = 0
hp_total = hp_agree = 0
depths = []

for path in logs:
    try:
        log = json.load(open(path))
    except Exception:
        continue
    for e in log:
        ag = e["conflicting_agents"]
        a, b = str(ag[0]), str(ag[1])
        bc, rc = e["agent_costs_under_branch"], e["root_costs"]
        if a not in rc or b not in rc:
            continue
        tot += 1
        depths.append(e["branch_depth"])

        d = {x: bc[x] - rc[x] for x in (a, b)}
        if d[a] != d[b]:
            asym += 1
            if rc[a] != rc[b]:
                delay_pick = a if d[a] > d[b] else b
                route_pick = a if rc[a] > rc[b] else b
                disagree_route += (delay_pick != route_pick)

            hp = e.get("higher_priority_count", {})
            if a in hp and b in hp and hp[a] != hp[b]:
                hp_total += 1
                hp_pick = a if hp[a] > hp[b] else b
                hp_agree += (hp_pick == (a if d[a] > d[b] else b))

        for x in (a, b):
            w = (e.get("agent_widths_at_conflict") or {}).get(x)
            if w is None:
                w_missing += 1
            else:
                widths[w] += 1

print(f"logs: {len(logs)}   conflicts: {tot}")
if depths:
    depths.sort()
    print(f"priority-tree depth Q1/med/Q3: "
          f"{depths[len(depths)//4]}/{depths[len(depths)//2]}/{depths[3*len(depths)//4]}")

print(f"\n--- delay ---")
print(f"  pair differs in delay:      {asym}/{tot} "
      f"({100*asym/tot:.1f}%)     [CBS: 69.8%]")
if asym:
    print(f"  disagrees with route order: {disagree_route}/{asym} "
          f"({100*disagree_route/asym:.1f}%)     [CBS: 47.7%]")

print(f"\n--- width ---")
wtot = sum(widths.values())
if wtot:
    print(f"  valid observations: {wtot}   missing: {w_missing}")
    for v, n in sorted(widths.items())[:6]:
        print(f"    width {v}: {n} ({100*n/wtot:.1f}%)"
              + ("     [CBS: 99.3%]" if v == 1 else ""))
else:
    print("  no width data")

print(f"\n--- higher-priority count vs delay ---")
if hp_total:
    print(f"  same ordering: {hp_agree}/{hp_total} "
          f"({100*hp_agree/hp_total:.1f}%)     [CBS constraint count: 99.5%]")
else:
    print("  insufficient data")