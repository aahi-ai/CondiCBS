import json, glob, os, collections
buckets = collections.defaultdict(lambda: collections.Counter())
asym = collections.defaultdict(lambda: [0,0])
for p in glob.glob("results/logs/*.json"):
    if os.path.basename(p).startswith("_"): continue
    try: log = json.load(open(p))
    except Exception: continue
    if not isinstance(log, list) or not log: continue
    root = next((c for c in log if c["branch_num_constraints"]==0), None)
    if root is None: continue
    rc = root["agent_costs_under_branch"]
    for e in log:
        ag = e["conflicting_agents"]
        if len(ag)!=2: continue
        d = e["branch_num_constraints"]
        b = "0-3" if d<=3 else ("4-6" if d<=6 else "7+")
        a0,a1 = str(ag[0]),str(ag[1])
        bc = e["agent_costs_under_branch"]
        if a0 in rc and a1 in rc:
            asym[b][1]+=1
            if bc[a0]-rc[a0] != bc[a1]-rc[a1]: asym[b][0]+=1
        for x in (a0,a1):
            w=(e.get("agent_widths_at_conflict") or {}).get(x)
            if w is not None: buckets[b][w]+=1

for b in ("0-3","4-6","7+"):
    n=sum(buckets[b].values()); h,t=asym[b]
    print(f"depth {b}: delay asym {100*h/t if t else 0:.1f}% (n={t}) | "
          f"width==1 {100*buckets[b][1]/n if n else 0:.1f}% (n={n})")