import json, glob, os, collections

within = collections.Counter()
beyond = collections.Counter()

for path in glob.glob("results/logs/*.json"):
    if os.path.basename(path).startswith("_"):
        continue
    try:
        log = json.load(open(path))
    except Exception:
        continue
    if not isinstance(log, list):
        continue
    for e in log:
        if e["conflict_type"] != "v":
            continue
        t = e["vertex_and_time"][-1]
        w = e.get("agent_widths_at_conflict") or {}
        for aid, cost in e["agent_costs_under_branch"].items():
            if aid not in w:
                continue
            (beyond if t > cost else within)[w[aid]] += 1

def show(name, c):
    tot = sum(c.values())
    print(f"\n{name}: {tot} observations")
    for v, n in sorted(c.items())[:6]:
        print(f"  width {v}: {n} ({100*n/tot:.1f}%)")

show("WITHIN path length", within)
show("BEYOND path length", beyond)
