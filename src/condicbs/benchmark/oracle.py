"""
Oracle ground-truth computation for directive scenarios.

Ground truth must be computed by a defined, checkable procedure — never
"what I decided felt right." Every function here documents its method
so it can be cited in the paper's benchmark section.
"""

import json

DEADLINE_BUFFER_FACTOR = 1.5  # documented assumption — deadline = 1.5x unconstrained shortest path cost


def compute_deadlines(conflict_log):
    """
    B02 oracle helper: deadline(agent) = 1.5 * agent's cost at the ROOT node
    (branch_num_constraints == 0), i.e. its unconstrained shortest path cost.
    """
    root_entry = next((c for c in conflict_log if c["branch_num_constraints"] == 0), None)
    if root_entry is None:
        raise ValueError("No root-level conflict (branch_num_constraints=0) found in log")

    deadlines = {}
    for agent_id, cost in root_entry["agent_costs_under_branch"].items():
        deadlines[agent_id] = cost * DEADLINE_BUFFER_FACTOR
    return deadlines


def oracle_b02_slack(conflict_entry, deadlines):
    """
    B02: "Give way to whichever agent has less remaining schedule slack."

    slack(agent) = deadline(agent) - current_cost_under_this_branch(agent)

    Ground truth: the agent with LOWER slack has priority (keeps its path).
    The agent with HIGHER slack should give way (accept the new constraint).

    Returns a result with excluded_reason set if the two agents have EQUAL
    slack — no defensible ground truth exists for a true tie.
    """
    agents = conflict_entry["conflicting_agents"]
    costs = conflict_entry["agent_costs_under_branch"]

    slacks = {
        str(a): deadlines[str(a)] - costs[str(a)]
        for a in agents
    }

    values = list(slacks.values())
    if values[0] == values[1]:
        return {
            "directive_id": "B02",
            "conflict_agents": agents,
            "slacks": slacks,
            "priority_agent": None,
            "give_way_agent": None,
            "excluded_reason": "tied slacks — no defensible ground truth",
            "method": "deadline = 1.5x root unconstrained cost; "
                      "slack = deadline - cost_under_current_branch; "
                      "lower slack = priority"
        }

    priority_agent = min(slacks, key=slacks.get)
    give_way_agent = max(slacks, key=slacks.get)

    return {
        "directive_id": "B02",
        "conflict_agents": agents,
        "slacks": slacks,
        "priority_agent": priority_agent,
        "give_way_agent": give_way_agent,
        "excluded_reason": None,
        "method": "deadline = 1.5x root unconstrained cost; "
                  "slack = deadline - cost_under_current_branch; "
                  "lower slack = priority"
    }


def oracle_b01_alternatives(conflict_entry):
    """
    B01: "Don't force the agent with fewer alternative routes into a detour."

    Uses the widths already computed by CBS+PC's own DAG-based path counting
    (the same mechanism it uses to classify cardinal/semi-cardinal conflicts).

    Ground truth: the agent with FEWER alternative routes (lower width)
    keeps priority; the agent with MORE alternatives gives way.

    Returns None if widths are missing from the log (predates instrumentation
    update). Returns a result with excluded_reason set if the two agents are
    tied on widths — no defensible ground truth exists for that case.
    """
    agents = conflict_entry["conflicting_agents"]
    widths = conflict_entry.get("agent_widths_at_conflict")
    if not widths:
        return None  # log predates the widths field — needs rerun

    widths = {str(a): widths[str(a)] for a in agents}
    values = list(widths.values())

    if values[0] == values[1]:
        return {
            "directive_id": "B01",
            "conflict_agents": agents,
            "widths": widths,
            "priority_agent": None,
            "give_way_agent": None,
            "excluded_reason": "tied widths — no defensible ground truth",
            "method": "widths = DAG-based count of optimal alternative paths at "
                      "conflict timestep, computed by CBS+PC's own low-level search; "
                      "fewer alternatives = priority"
        }

    priority_agent = min(widths, key=widths.get)
    give_way_agent = max(widths, key=widths.get)

    return {
        "directive_id": "B01",
        "conflict_agents": agents,
        "widths": widths,
        "priority_agent": priority_agent,
        "give_way_agent": give_way_agent,
        "excluded_reason": None,
        "method": "widths = DAG-based count of optimal alternative paths at "
                  "conflict timestep, computed by CBS+PC's own low-level search; "
                  "fewer alternatives = priority (avoid forcing a detour on the "
                  "less flexible agent)"
    }


def run_b02_on_log(log_path, map_name, n_agents, rseed):
    with open(log_path) as f:
        conflict_log = json.load(f)
    deadlines = compute_deadlines(conflict_log)
    results = []
    for entry in conflict_log:
        if len(entry["conflicting_agents"]) == 2:
            r = oracle_b02_slack(entry, deadlines)
            r["source_map"] = map_name
            r["source_n_agents"] = n_agents
            r["source_rseed"] = rseed
            results.append(r)

    usable = [r for r in results if r["excluded_reason"] is None]
    excluded = [r for r in results if r["excluded_reason"] is not None]
    print(f"  B02 ({map_name}, {n_agents}a, rseed{rseed}): {len(usable)} usable, {len(excluded)} excluded")
    return results


def run_b01_on_log(log_path, map_name, n_agents, rseed):
    with open(log_path) as f:
        conflict_log = json.load(f)
    results = []
    for entry in conflict_log:
        if len(entry["conflicting_agents"]) == 2:
            r = oracle_b01_alternatives(entry)
            if r:
                r["source_map"] = map_name
                r["source_n_agents"] = n_agents
                r["source_rseed"] = rseed
                results.append(r)

    usable = [r for r in results if r["excluded_reason"] is None]
    excluded = [r for r in results if r["excluded_reason"] is not None]
    print(f"  B01 ({map_name}, {n_agents}a, rseed{rseed}): {len(usable)} usable, {len(excluded)} excluded")
    return results


if __name__ == "__main__":
    import glob

    print("Checking B01/B02 yield across all available logs...\n")
    for log_path in sorted(glob.glob("results/logs/*.json")):
        if log_path.endswith("_summary.json") or os.path.basename(log_path).startswith("_divergent"):
            continue
        try:
            with open(log_path) as f:
                conflict_log = json.load(f)
            if not conflict_log:
                continue

            b01_results = []
            for entry in conflict_log:
                if len(entry["conflicting_agents"]) == 2:
                    r = oracle_b01_alternatives(entry)
                    if r:
                        b01_results.append(r)
            b01_usable = sum(1 for r in b01_results if r["excluded_reason"] is None)

            print(f"{log_path}: {len(conflict_log)} conflicts, "
                  f"B01 usable: {b01_usable}/{len(b01_results)}")
        except Exception as e:
            print(f"{log_path}: skipped ({e})")