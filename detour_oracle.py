"""
Detour-based branch-relative directive, constant-free.

d_i = branch_cost_i - root_cost_i  (cost accumulated from constraints
on this branch). At the root, every d_i = 0 — a root-time compiler has
NO signal, for every conflict, not a selected subset.

Directive: "give way to whichever robot has been detoured less"
(i.e. priority to the one already forced off its optimal path).
"""
import json, glob, os, collections

logs = [p for p in glob.glob("results/logs/*.json")
        if not os.path.basename(p).startswith("_")]

total = usable = disagree_with_rootcost = 0
depths = []
detour_gaps = []

for path in logs:
    try:
        log = json.load(open(path))
    except Exception:
        continue
    if not isinstance(log, list) or not log:
        continue
    root = next((c for c in log if c["branch_num_constraints"] == 0), None)
    if root is None:
        continue
    rc = root["agent_costs_under_branch"]

    for e in log:
        ag = e["conflicting_agents"]
        if len(ag) != 2:
            continue
        a0, a1 = str(ag[0]), str(ag[1])
        bc = e["agent_costs_under_branch"]
        if a0 not in rc or a1 not in rc or a0 not in bc or a1 not in bc:
            continue
        total += 1
        d = {a: bc[a] - rc[a] for a in (a0, a1)}
        if d[a0] == d[a1]:
            continue                      # includes every root-level conflict
        usable += 1
        depths.append(e["branch_num_constraints"])
        detour_gaps.append(abs(d[a0] - d[a1]))

        # does detour give a different answer than "shorter optimal path wins"?
        detour_pick = max(d, key=d.get)
        if rc[a0] != rc[a1]:
            rootcost_pick = a0 if rc[a0] < rc[a1] else a1
            if detour_pick != rootcost_pick:
                disagree_with_rootcost += 1

print(f"2-agent conflicts:            {total}")
print(f"usable (unequal detour):      {usable} ({100*usable/total:.1f}%)")
print(f"disagrees with shortest-path: {disagree_with_rootcost} "
      f"({100*disagree_with_rootcost/usable:.1f}% of usable)")
print(f"median detour gap:            {sorted(detour_gaps)[len(detour_gaps)//2]}")
print(f"depth (constraints) quartiles: "
      f"{sorted(depths)[len(depths)//4]}, {sorted(depths)[len(depths)//2]}, "
      f"{sorted(depths)[3*len(depths)//4]}")
