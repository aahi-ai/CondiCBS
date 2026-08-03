"""
Static compiler baseline: resolves each directive into a FIXED priority
ordering once, using only root-level (branch-independent) information —
exactly what an upfront NL-to-constraint compiler (CaStL-style) would do.

This is deliberately unable to see branch-specific facts. On Class B
directives, this SHOULD diverge from the oracle ground truth whenever the
correct answer depends on branch state that changes after the root.
"""

import json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from src.condicbs.benchmark.oracle import compute_deadlines, DEADLINE_BUFFER_FACTOR


def get_root_slacks_for_log(log_path):
    """
    Root-level slack for every agent in a log: deadline - root_cost.
    Since deadline = 1.5x root_cost, root slack = 0.5x root_cost for everyone —
    a real, checkable consequence of the deadline definition, not hand-picked.
    """
    with open(log_path) as f:
        conflict_log = json.load(f)
    deadlines = compute_deadlines(conflict_log)
    root_entry = next(c for c in conflict_log if c["branch_num_constraints"] == 0)
    root_costs = root_entry["agent_costs_under_branch"]
    return {aid: deadlines[aid] - root_costs[aid] for aid in root_costs}


def get_root_widths_for_log(log_path, target_pair):
    """
    Root-level widths: from the FIRST logged conflict involving this exact
    pair (lowest branch_node_entry), not the scenario's own (possibly
    deeper-branch) conflict.
    """
    with open(log_path) as f:
        conflict_log = json.load(f)
    candidates = [
        c for c in conflict_log
        if len(c["conflicting_agents"]) == 2
        and tuple(sorted(str(a) for a in c["conflicting_agents"])) == target_pair
        and c.get("agent_widths_at_conflict")
    ]
    if not candidates:
        return None
    earliest = min(candidates, key=lambda c: c["branch_node_entry"])
    return {str(a): v for a, v in earliest["agent_widths_at_conflict"].items()}


def compile_static_priority(root_facts):
    """Fixed priority = min value at ROOT, applied to every later conflict for this pair."""
    return min(root_facts, key=root_facts.get)


def evaluate_static_baseline_b02(scenarios, log_paths_by_source):
    results = []
    slack_cache = {}
    for s in scenarios:
        gt = s.oracle_ground_truth
        if "slacks" not in gt:
            continue
        log_path = log_paths_by_source[(s.map_name, s.n_agents, s.rseed)]
        if log_path not in slack_cache:
            slack_cache[log_path] = get_root_slacks_for_log(log_path)
        root_slacks = slack_cache[log_path]

        agents = list(gt["slacks"].keys())
        root_facts = {a: root_slacks[a] for a in agents}
        static_priority = compile_static_priority(root_facts)
        oracle_priority = gt.get("priority_agent")
        correct = str(static_priority) == str(oracle_priority)

        results.append({
            "scenario_id": s.id,
            "root_slacks_used": root_facts,
            "static_priority_agent": static_priority,
            "oracle_priority_agent": oracle_priority,
            "correct": correct,
        })
    return results


def evaluate_static_baseline_b01(scenarios, log_paths_by_source):
    results = []
    for s in scenarios:
        gt = s.oracle_ground_truth
        if "widths" not in gt:
            continue
        log_path = log_paths_by_source[(s.map_name, s.n_agents, s.rseed)]
        agents = list(gt["widths"].keys())
        pair = tuple(sorted(agents))
        root_facts = get_root_widths_for_log(log_path, pair)

        if root_facts is None:
            results.append({"scenario_id": s.id, "error": "no root conflict found for pair"})
            continue

        static_priority = compile_static_priority(root_facts)
        oracle_priority = gt.get("priority_agent")
        correct = str(static_priority) == str(oracle_priority)

        results.append({
            "scenario_id": s.id,
            "root_widths_used": root_facts,
            "static_priority_agent": static_priority,
            "oracle_priority_agent": oracle_priority,
            "correct": correct,
        })
    return results


if __name__ == "__main__":
    from src.condicbs.directives.library import SCENARIOS

    class_b = [s for s in SCENARIOS if s.directive_class == "B"]

    log_paths_by_source = {
        ("room-32-32-4", 8, 42): "results/logs/room-32-32-4_8agents_rseed42.json",
        ("room-32-32-4", 12, 1): "results/logs/room-32-32-4_12agents_rseed1.json",
        ("room-32-32-4", 12, 42): "results/logs/room-32-32-4_12agents_rseed42.json",
        ("maze-32-32-2", 10, 239): "results/logs/maze-32-32-2_10agents_rseed239.json",
    }

    b02_results = evaluate_static_baseline_b02(class_b, log_paths_by_source)
    b01_results = evaluate_static_baseline_b01(class_b, log_paths_by_source)
    all_results = b02_results + b01_results

    n_correct = sum(1 for r in all_results if r.get("correct"))
    n_total = len([r for r in all_results if "error" not in r])
    print(f"Static baseline accuracy: {n_correct}/{n_total}\n")
    for r in all_results:
        print(f"  {r['scenario_id']}: correct={r.get('correct')}, "
              f"static={r.get('static_priority_agent')}, oracle={r.get('oracle_priority_agent')}")

    os.makedirs("results/tables", exist_ok=True)
    with open("results/tables/static_baseline_v1.json", "w") as f:
        json.dump(all_results, f, indent=2)
    print("\nSaved to results/tables/static_baseline_v1.json")