import sys, os, json, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from src.condicbs.grounding.llm_client import call_llm
from src.condicbs.grounding.prompts import build_grounding_prompt


def normalize_agent_id(val):
    """
    Normalizes agent ID strings for comparison — handles cases like
    "Agent 8" vs "8" vs "agent_8" all meaning the same thing.
    """
    if val is None:
        return None
    digits = re.sub(r'\D', '', str(val))
    return digits if digits else str(val).strip().lower()


def ground_scenario(scenario):
    """
    Takes a DirectiveScenario, builds relevant_data from its oracle_ground_truth
    (the raw facts, NOT the answer), queries the LLM, and returns its decision.
    """
    gt = scenario.oracle_ground_truth

    if "branch_slacks" in gt:
        agents = list(gt["branch_slacks"].keys())
        relevant_data = {a: {"schedule_slack": gt["branch_slacks"][a]} for a in agents}
    elif "slacks" in gt:  # backward-compat with older scenario format
        agents = list(gt["slacks"].keys())
        relevant_data = {a: {"schedule_slack": gt["slacks"][a]} for a in agents}
    elif "widths" in gt:
        agents = list(gt["widths"].keys())
        relevant_data = {a: {"num_alternative_routes": gt["widths"][a]} for a in agents}
    else:
        raise ValueError(f"Don't know how to build relevant_data for {scenario.id}")

    prompt = build_grounding_prompt(scenario.directive_text, agents, relevant_data)
    raw_response = call_llm(prompt)

    match = re.search(r'\{.*\}', raw_response, re.DOTALL)
    if not match:
        return {"scenario_id": scenario.id, "error": "no JSON found", "raw": raw_response}

    try:
        parsed = json.loads(match.group())
    except json.JSONDecodeError:
        return {"scenario_id": scenario.id, "error": "JSON parse failed", "raw": raw_response}

    llm_priority_norm = normalize_agent_id(parsed.get("priority_agent"))
    oracle_priority_norm = normalize_agent_id(gt.get("priority_agent"))
    correct = llm_priority_norm == oracle_priority_norm

    return {
        "scenario_id": scenario.id,
        "llm_priority_agent": parsed.get("priority_agent"),
        "llm_give_way_agent": parsed.get("give_way_agent"),
        "llm_reasoning": parsed.get("reasoning"),
        "oracle_priority_agent": gt.get("priority_agent"),
        "correct": correct,
    }