"""
Grounding evaluation for Class A (statically groundable) directives.
Different task shape from Class B: the LLM must correctly apply a FIXED
RULE to a conflict, not compare branch-relative facts. This tests whether
CondiCBS regresses on cases that don't need reactive grounding at all.

Two sub-tests, since Class A covers two different rule shapes:
- A01 (fixed priority): "does the LLM correctly pick the named priority
  agent regardless of who it's up against" — tested against multiple
  opponent pairs.
- A02 (fixed zone/time-window): "does the LLM correctly extract the
  constraint's structure from the directive text" — a translation
  accuracy test, not a priority-pick test.
"""

import sys, os, json, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from src.condicbs.grounding.llm_client import call_llm
from src.condicbs.grounding.conflict_grounder import normalize_agent_id


def build_class_a_prompt(directive_text, conflict_agents, rule_context):
    return f"""You are resolving a conflict between two robots in a multi-agent path planning system, using a FIXED mission rule.

Mission rule: "{directive_text}"

Two robots are about to collide: Agent {conflict_agents[0]} and Agent {conflict_agents[1]}.
Additional context: {rule_context}

Apply the rule exactly as stated to decide which agent keeps priority and which gives way.

Respond with ONLY a JSON object, no other text:
{{"priority_agent": "<agent_id>", "give_way_agent": "<agent_id>", "reasoning": "<one sentence>"}}"""


def ground_class_a_scenario(scenario, test_conflict_agents):
    """
    test_conflict_agents: a (agent_a, agent_b) pair to test the rule
    against — Class A scenarios don't come from a mined conflict log,
    so we construct representative test cases ourselves.
    """
    gt = scenario.oracle_ground_truth
    rule = gt.get("rule", "")

    prompt = build_class_a_prompt(scenario.directive_text, test_conflict_agents, rule)
    raw_response = call_llm(prompt)

    match = re.search(r'\{.*\}', raw_response, re.DOTALL)
    if not match:
        return {"scenario_id": scenario.id, "test_agents": test_conflict_agents,
                "error": "no JSON found", "raw": raw_response}

    try:
        parsed = json.loads(match.group())
    except json.JSONDecodeError:
        return {"scenario_id": scenario.id, "test_agents": test_conflict_agents,
                "error": "JSON parse failed", "raw": raw_response}

    expected_priority = gt.get("priority_agent")
    llm_priority = normalize_agent_id(parsed.get("priority_agent"))
    expected_norm = normalize_agent_id(expected_priority)

    correct = llm_priority == expected_norm

    return {
        "scenario_id": scenario.id,
        "test_agents": test_conflict_agents,
        "llm_priority_agent": parsed.get("priority_agent"),
        "llm_reasoning": parsed.get("reasoning"),
        "expected_priority_agent": expected_priority,
        "correct": correct,
    }


def build_a02_prompt(directive_text):
    return f"""You are translating a mission directive into a formal constraint for a multi-agent path planning system.

Mission directive: "{directive_text}"

Extract the constraint as a structured object.

Respond with ONLY a JSON object, no other text:
{{"forbidden_cell": [row, col], "time_window": [start_timestep, end_timestep], "applies_to": "all agents or specific agent id"}}"""


def ground_a02_scenario(scenario):
    prompt = build_a02_prompt(scenario.directive_text)
    raw_response = call_llm(prompt)

    match = re.search(r'\{.*\}', raw_response, re.DOTALL)
    if not match:
        return {"scenario_id": scenario.id, "error": "no JSON found", "raw": raw_response}

    try:
        parsed = json.loads(match.group())
    except json.JSONDecodeError:
        return {"scenario_id": scenario.id, "error": "JSON parse failed", "raw": raw_response}

    gt = scenario.oracle_ground_truth
    expected_cell = gt.get("forbidden_cell")
    expected_window = gt.get("time_window")

    llm_cell = parsed.get("forbidden_cell")
    llm_window = parsed.get("time_window")

    cell_correct = llm_cell == expected_cell
    window_correct = llm_window == expected_window
    fully_correct = cell_correct and window_correct

    return {
        "scenario_id": scenario.id,
        "llm_forbidden_cell": llm_cell,
        "expected_forbidden_cell": expected_cell,
        "cell_correct": cell_correct,
        "llm_time_window": llm_window,
        "expected_time_window": expected_window,
        "window_correct": window_correct,
        "correct": fully_correct,
    }


if __name__ == "__main__":
    from src.condicbs.directives.library import SCENARIOS

    class_a = [s for s in SCENARIOS if s.directive_class == "A"]

    results = []

    # --- A01: fixed priority, tested against multiple opponents ---
    test_cases = {
        "A01_00": [("0", "5"), ("0", "12"), ("0", "3")],
    }

    a01_scenarios = [s for s in class_a if s.id in test_cases]
    for s in a01_scenarios:
        for pair in test_cases[s.id]:
            r = ground_class_a_scenario(s, pair)
            results.append(r)
            status = "✓" if r.get("correct") else "✗"
            print(f"{status} {s.id} {pair}: LLM said {r.get('llm_priority_agent')}, "
                  f"expected {r.get('expected_priority_agent')}")

    # --- A02: fixed zone/time-window, constraint-extraction accuracy ---
    a02_scenarios = [s for s in class_a if s.id == "A02_00"]
    for s in a02_scenarios:
        r = ground_a02_scenario(s)
        results.append(r)
        status = "✓" if r.get("correct") else "✗"
        print(f"{status} {s.id}: cell={r.get('llm_forbidden_cell')} "
              f"(expected {r.get('expected_forbidden_cell')}), "
              f"window={r.get('llm_time_window')} (expected {r.get('expected_time_window')})")

    n_correct = sum(1 for r in results if r.get("correct"))
    print(f"\nClass A accuracy: {n_correct}/{len(results)}")

    os.makedirs("results/tables", exist_ok=True)
    with open("results/tables/class_a_eval_v1.json", "w") as f:
        json.dump(results, f, indent=2)
    print("Saved to results/tables/class_a_eval_v1.json")