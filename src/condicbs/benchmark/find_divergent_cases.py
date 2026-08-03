"""
Mines conflict logs for cases where root-level facts (what a static
compiler sees) and branch-level facts (what CondiCBS sees) disagree on
priority. These divergent cases are the actual evidence for the necessity
argument — non-divergent conflicts don't distinguish the two approaches.

CRITICAL: tied cases (no defensible ground truth per oracle.py's
excluded_reason) are filtered out here, at the source — a tie has no real
"correct answer" for static to get wrong, so it can never count as a
genuine divergent case.
"""

import sys, os, json, glob
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from src.condicbs.benchmark.oracle import (
    compute_deadlines, oracle_b02_slack, oracle_b01_alternatives
)


def find_b02_divergences(log_path):
    with open(log_path) as f:
        conflict_log = json.load(f)

    deadlines = compute_deadlines(conflict_log)
    root_entry = next(c for c in conflict_log if c["branch_num_constraints"] == 0)
    root_costs = root_entry["agent_costs_under_branch"]
    root_slacks = {aid: deadlines[aid] - root_costs[aid] for aid in root_costs}

    divergent = []
    for entry in conflict_log:
        if len(entry["conflicting_agents"]) != 2:
            continue
        r = oracle_b02_slack(entry, deadlines)

        # skip tied cases — no real ground truth, cannot be "divergent"
        if r["excluded_reason"] is not None:
            continue

        agents = r["conflict_agents"]
        a0, a1 = str(agents[0]), str(agents[1])

        # also skip if root itself was tied (no static answer to diverge from)
        if root_slacks[a0] == root_slacks[a1]:
            continue

        static_priority = a0 if root_slacks[a0] < root_slacks[a1] else a1
        branch_priority = r["priority_agent"]

        if static_priority != branch_priority:
            divergent.append({
                "log_path": log_path,
                "branch_node_entry": entry["branch_node_entry"],
                "branch_num_constraints": entry["branch_num_constraints"],
                "conflict_agents": agents,
                "root_slacks": {a0: root_slacks[a0], a1: root_slacks[a1]},
                "branch_slacks": r["slacks"],
                "static_would_say": static_priority,
                "actual_correct_answer": branch_priority,
            })
    return divergent


def find_b01_divergences(log_path):
    with open(log_path) as f:
        conflict_log = json.load(f)

    by_pair_earliest = {}
    for entry in conflict_log:
        if len(entry["conflicting_agents"]) != 2 or not entry.get("agent_widths_at_conflict"):
            continue
        pair = tuple(sorted(str(a) for a in entry["conflicting_agents"]))
        if pair not in by_pair_earliest or entry["branch_node_entry"] < by_pair_earliest[pair]["branch_node_entry"]:
            by_pair_earliest[pair] = entry

    divergent = []
    for entry in conflict_log:
        if len(entry["conflicting_agents"]) != 2:
            continue
        r = oracle_b01_alternatives(entry)
        if not r or r["excluded_reason"] is not None:
            continue

        pair = tuple(sorted(r["conflict_agents"]))
        earliest = by_pair_earliest.get(pair)
        if not earliest or entry is earliest:
            continue

        earliest_r = oracle_b01_alternatives(earliest)
        if not earliest_r or earliest_r["excluded_reason"] is not None:
            continue

        static_would_say = earliest_r["priority_agent"]
        actual_answer = r["priority_agent"]

        if static_would_say != actual_answer:
            divergent.append({
                "log_path": log_path,
                "branch_node_entry": entry["branch_node_entry"],
                "conflict_agents": r["conflict_agents"],
                "root_widths": earliest_r["widths"],
                "branch_widths": r["widths"],
                "static_would_say": static_would_say,
                "actual_correct_answer": actual_answer,
            })
    return divergent


def diagnose_pair_reconflicts(log_path):
    with open(log_path) as f:
        log = json.load(f)

    pair_counts = defaultdict(int)
    for entry in log:
        if len(entry["conflicting_agents"]) == 2:
            pair = tuple(sorted(str(a) for a in entry["conflicting_agents"]))
            pair_counts[pair] += 1

    repeated = {p: c for p, c in pair_counts.items() if c > 1}
    print(f"  {log_path}")
    print(f"    Total unique pairs: {len(pair_counts)}")
    print(f"    Pairs that reconflict (>1 time): {len(repeated)}")
    if pair_counts:
        print(f"    Max reconflicts for one pair: {max(pair_counts.values())}")
    else:
        print("    No 2-agent conflicts in this log")


def diagnose_b01_usable_rate(log_path):
    with open(log_path) as f:
        conflict_log = json.load(f)

    usable, excluded = 0, 0
    for entry in conflict_log:
        if len(entry["conflicting_agents"]) != 2:
            continue
        r = oracle_b01_alternatives(entry)
        if r is None:
            continue
        if r["excluded_reason"] is None:
            usable += 1
        else:
            excluded += 1

    total = usable + excluded
    rate = (usable / total * 100) if total else 0
    print(f"  {log_path}: {usable} usable / {total} total 2-agent conflicts ({rate:.1f}%)")


if __name__ == "__main__":
    logs = [
        p for p in glob.glob("results/logs/*.json")
        if not p.endswith("_summary.json")
        and not os.path.basename(p).startswith("_divergent")
    ]

    print("=== B02 divergent cases (root slack disagrees with branch slack) ===")
    all_b02_divergent = []
    for log in logs:
        try:
            d = find_b02_divergences(log)
            all_b02_divergent.extend(d)
            if d:
                print(f"{log}: {len(d)} divergent")
        except Exception as e:
            print(f"{log}: ERROR - {e}")
    print(f"Total B02 divergent cases found: {len(all_b02_divergent)}\n")

    print("=== B01 divergent cases (root widths disagree with branch widths) ===")
    all_b01_divergent = []
    for log in logs:
        try:
            d = find_b01_divergences(log)
            all_b01_divergent.extend(d)
            if d:
                print(f"{log}: {len(d)} divergent")
        except Exception as e:
            print(f"{log}: ERROR - {e}")
    print(f"Total B01 divergent cases found: {len(all_b01_divergent)}\n")

    os.makedirs("results/logs", exist_ok=True)
    with open("results/logs/_divergent_b02.json", "w") as f:
        json.dump(all_b02_divergent, f, indent=2, default=str)
    with open("results/logs/_divergent_b01.json", "w") as f:
        json.dump(all_b01_divergent, f, indent=2, default=str)
    print("Saved to results/logs/_divergent_b02.json and _divergent_b01.json")

    if all_b02_divergent:
        print("\n--- Sample B02 divergent case ---")
        print(json.dumps(all_b02_divergent[0], indent=2, default=str))
    if all_b01_divergent:
        print("\n--- Sample B01 divergent case ---")
        print(json.dumps(all_b01_divergent[0], indent=2, default=str))

    print("\n=== Diagnostic: pair reconflict rates per log ===")
    for log in logs:
        try:
            diagnose_pair_reconflicts(log)
        except Exception as e:
            print(f"  {log}: skipped ({e})")

    print("\n=== Diagnostic: B01 usable (non-tied) rate per log ===")
    for log in logs:
        try:
            diagnose_b01_usable_rate(log)
        except Exception as e:
            print(f"  {log}: skipped ({e})")