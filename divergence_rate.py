import json, glob, os

FACTORS = [1.1, 1.25, 1.5, 2.0, 3.0]

logs = [p for p in glob.glob("results/logs/*.json")
        if not os.path.basename(p).startswith("_")]

for f in FACTORS:
    total = usable = divergent = 0
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
        deadlines = {a: c * f for a, c in rc.items()}

        for e in log:
            ag = e["conflicting_agents"]
            if len(ag) != 2:
                continue
            total += 1
            a0, a1 = str(ag[0]), str(ag[1])
            bc = e["agent_costs_under_branch"]
            try:
                bs = {a: deadlines[a] - bc[a] for a in (a0, a1)}
                rs = {a: deadlines[a] - rc[a] for a in (a0, a1)}
            except KeyError:
                continue
            if bs[a0] == bs[a1] or rs[a0] == rs[a1]:
                continue
            usable += 1
            if min(bs, key=bs.get) != min(rs, key=rs.get):
                divergent += 1

    pct = 100*divergent/usable if usable else 0
    print(f"f={f}: {total} conflicts, {usable} usable, "
          f"{divergent} divergent ({pct:.1f}% of usable)")
