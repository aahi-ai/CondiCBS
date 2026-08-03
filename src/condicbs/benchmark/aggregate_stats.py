"""
Aggregate statistics across all mined logs — directly answers the
questions a reviewer (and your mentor) will ask: how often does
branch-relative divergence actually occur, not just "does it occur."
"""

import sys, os, json, glob
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from src.condicbs.benchmark.oracle import compute_deadlines, oracle_b02_slack


def analyze_log(log_path):
    with open(log_path) as f:
        conflict_log = json.load(f)
    if not conflict_log:
        return None

    try:
        deadlines = compute_deadlines(conflict_log)
    except Exception:
        return None

    root_entry = next((c for c in conflict_log if c["branch_num_constraints"] == 0), None)
    if not root_entry:
        return None
    root_costs = root_entry["agent_costs_under_branch"]
    root_slacks = {aid: deadlines[aid] - root_costs[aid] for aid in root_costs}

    total_2agent = 0
    divergent = 0
    for entry in conflict_log:
        if len(entry["conflicting_agents"]) != 2:
            continue
        total_2agent += 1
        r = oracle_b02_slack(entry, deadlines)
        agents = r["conflict_agents"]
        a0, a1 = str(agents[0]), str(agents[1])
        static_priority = a0 if root_slacks[a0] < root_slacks[a1] else a1
        if static_priority != r["priority_agent"]:
            divergent += 1

    return {
        "log_path": log_path,
        "total_2agent_conflicts": total_2agent,
        "divergent_conflicts": divergent,
        "divergence_rate": divergent / total_2agent if total_2agent else 0,
        "instance_has_any_divergence": divergent > 0,
    }


if __name__ == "__main__":
    logs = [p for p in glob.glob("results/logs/*.json")
            if not p.endswith("_summary.json")
            and not os.path.basename(p).startswith("_divergent")]

    per_instance = []
    for log in logs:
        try:
            result = analyze_log(log)
            if result:
                per_instance.append(result)
        except Exception as e:
            print(f"{log}: skipped ({e})")

    total_instances = len(per_instance)
    instances_with_divergence = sum(1 for r in per_instance if r["instance_has_any_divergence"])
    total_conflicts = sum(r["total_2agent_conflicts"] for r in per_instance)
    total_divergent = sum(r["divergent_conflicts"] for r in per_instance)

    print(f"=== Aggregate statistics across {total_instances} instances ===\n")
    print(f"Instances with at least one divergent conflict: "
          f"{instances_with_divergence}/{total_instances} "
          f"({instances_with_divergence/total_instances*100:.1f}%)")
    print(f"Total 2-agent conflicts across all instances: {total_conflicts}")
    print(f"Total divergent conflicts: {total_divergent}")
    print(f"Overall divergence rate: {total_divergent/total_conflicts*100:.2f}% of all conflicts")

    os.makedirs("results/tables", exist_ok=True)
    with open("results/tables/aggregate_stats.json", "w") as f:
        json.dump({
            "total_instances": total_instances,
            "instances_with_divergence": instances_with_divergence,
            "total_conflicts": total_conflicts,
            "total_divergent": total_divergent,
            "per_instance": per_instance,
        }, f, indent=2)
    print("\nSaved to results/tables/aggregate_stats.json")