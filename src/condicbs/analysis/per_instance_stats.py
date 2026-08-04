"""
Per-instance versions of the Section 4 statistics.

The corpus figures pool observations across runs of wildly different lengths,
so a handful of hard instances (2000-3000 conflicts each) dominate. These
compute each statistic per instance, then average across instances.
"""
import json, glob, os, collections, statistics as st

rows = []
for p in sorted(glob.glob("results/logs/*.json")):
    if os.path.basename(p).startswith("_"):
        continue
    try:
        log = json.load(open(p))
    except Exception:
        continue
    if not isinstance(log, list) or not log:
        continue
    root = next((c for c in log if c["branch_num_constraints"] == 0), None)
    if root is None:
        continue
    rc = root["agent_costs_under_branch"]

    n_conf = asym = 0
    w = collections.Counter()
    for e in log:
        ag = e["conflicting_agents"]
        if len(ag) != 2:
            continue
        a, b = str(ag[0]), str(ag[1])
        bc = e["agent_costs_under_branch"]
        if a in rc and b in rc:
            n_conf += 1
            if bc[a] - rc[a] != bc[b] - rc[b]:
                asym += 1
        for x in (a, b):
            v = (e.get("agent_widths_at_conflict") or {}).get(x)
            if v is not None:
                w[x if False else v] += 1

    wt = sum(w.values())
    rows.append({
        "name": os.path.basename(p),
        "conflicts": len(log),
        "delay_asym": (100 * asym / n_conf) if n_conf else None,
        "width1": (100 * w[1] / wt) if wt else None,
    })

def report(key, pooled_label):
    vals = [r[key] for r in rows if r[key] is not None]
    print(f"\n{key}:")
    print(f"  per-instance mean   {st.mean(vals):.1f}% +/- {st.stdev(vals):.1f}"
          f"   median {st.median(vals):.1f}%   (n={len(vals)} instances)")
    print(f"  (pooled corpus figure currently in paper: {pooled_label})")

print(f"instances: {len(rows)}")
report("delay_asym", "69.8%")
report("width1", "97.6%")

# difficulty relationship
print("\nwidth1 by instance difficulty:")
for lo, hi, label in [(0, 10, "<10 conflicts"), (10, 100, "10-99"),
                      (100, 1000, "100-999"), (1000, 10**9, "1000+")]:
    sel = [r["width1"] for r in rows
           if r["width1"] is not None and lo <= r["conflicts"] < hi]
    if sel:
        print(f"  {label:15s} n={len(sel):3d}  width1 mean {st.mean(sel):5.1f}%"
              f"  median {st.median(sel):5.1f}%")
        
print("\ndelay asymmetry by instance difficulty:")
for lo, hi, label in [(0, 10, "<10 conflicts"), (10, 100, "10-99"),
                      (100, 1000, "100-999"), (1000, 10**9, "1000+")]:
    sel = [r["delay_asym"] for r in rows
           if r["delay_asym"] is not None and lo <= r["conflicts"] < hi]
    if sel:
        print(f"  {label:15s} n={len(sel):3d}  asym mean {st.mean(sel):5.1f}%"
              f"  median {st.median(sel):5.1f}%")

# correlation between difficulty and each statistic
import math
def corr(xs, ys):
    n = len(xs)
    mx, my = st.mean(xs), st.mean(ys)
    num = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    den = math.sqrt(sum((x-mx)**2 for x in xs) * sum((y-my)**2 for y in ys))
    return num/den if den else 0

for key in ("delay_asym", "width1"):
    pts = [(math.log10(max(r["conflicts"], 1)), r[key])
           for r in rows if r[key] is not None]
    xs, ys = zip(*pts)
    print(f"\ncorr(log10 conflicts, {key}) = {corr(xs, ys):+.3f}  (n={len(pts)})")