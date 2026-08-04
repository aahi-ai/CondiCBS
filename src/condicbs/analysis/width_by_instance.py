import json, glob, os, collections
rows = []
for p in glob.glob("results/logs/*.json"):
    if os.path.basename(p).startswith("_"): continue
    try: log = json.load(open(p))
    except Exception: continue
    if not isinstance(log, list) or not log: continue
    w = collections.Counter()
    for e in log:
        for v in (e.get("agent_widths_at_conflict") or {}).values():
            if v is not None: w[v] += 1
    t = sum(w.values())
    if t: rows.append((len(log), 100*w[1]/t, os.path.basename(p)))
rows.sort()
for n, pct, name in rows[:8]:  print(f"{n:6d} conflicts  width1={pct:5.1f}%  {name}")
print("...")
for n, pct, name in rows[-8:]: print(f"{n:6d} conflicts  width1={pct:5.1f}%  {name}")