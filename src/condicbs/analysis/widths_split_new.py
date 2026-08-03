import json, glob, os, collections, time

CUTOFF = time.time() - 3600   # logs written in the last hour

within, beyond, missing = collections.Counter(), collections.Counter(), 0
files = 0
for path in glob.glob("results/logs/*.json"):
    if os.path.basename(path).startswith("_"):
        continue
    if os.path.getmtime(path) < CUTOFF:
        continue
    try:
        log = json.load(open(path))
    except Exception:
        continue
    if not isinstance(log, list):
        continue
    files += 1
    for e in log:
        w = e.get("agent_widths_at_conflict") or {}
        valid = e.get("agent_width_valid") or {}
        for aid, val in w.items():
            if val is None:
                missing += 1
            elif valid.get(aid, True):
                within[val] += 1
            else:
                beyond[val] += 1

def show(name, c):
    tot = sum(c.values())
    if not tot:
        print(f"\n{name}: none")
        return
    print(f"\n{name}: {tot} observations")
    for v, n in sorted(c.items())[:8]:
        print(f"  width {v}: {n} ({100*n/tot:.1f}%)")

print(f"logs from fixed logger: {files}")
print(f"missing (None): {missing}")
show("WITHIN path (valid lookup)", within)
show("BEYOND path (clamped)", beyond)
