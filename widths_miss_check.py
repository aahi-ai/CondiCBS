import json, glob, os

hits = misses = 0
examples = []
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
        # cost is a proxy for path length; if conflict_t exceeds it, agent is parked
        for aid, cost in e["agent_costs_under_branch"].items():
            if aid not in w:
                continue
            if t > cost:
                misses += 1
                if len(examples) < 5:
                    examples.append((t, cost, w[aid]))
            else:
                hits += 1

tot = hits + misses
print(f"conflict_t within agent path length: {hits} ({100*hits/tot:.1f}%)")
print(f"conflict_t beyond  agent path length: {misses} ({100*misses/tot:.1f}%)")
print("\nsamples (conflict_t, agent_cost, logged_width):")
for x in examples:
    print("  ", x)
