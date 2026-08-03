import json, glob, collections
vals = []
for p in glob.glob("results/logs/room-32-32-4_*.json") + glob.glob("results/logs/maze-*.json"):
    try:
        log = json.load(open(p))
    except Exception:
        continue
    if not isinstance(log, list):
        continue
    for e in log:
        if isinstance(e, dict) and "agent_widths_at_conflict" in e:
            vals.extend(e["agent_widths_at_conflict"].values())

c = collections.Counter(vals)
print(f"total width observations: {len(vals)}")
for v, n in sorted(c.items())[:10]:
    print(f"  width {v}: {n} ({100*n/len(vals):.1f}%)")
