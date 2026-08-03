def build_grounding_prompt(directive_text, conflict_agents, relevant_data):
    """
    relevant_data: dict of agent_id -> {fact_name: value}, e.g.
    {"6": {"schedule_slack": 6.0}, "7": {"schedule_slack": 21.0}}
    """
    data_lines = []
    for agent_id, facts in relevant_data.items():
        fact_str = ", ".join(f"{k}={v}" for k, v in facts.items())
        data_lines.append(f"  Agent {agent_id}: {fact_str}")
    data_block = "\n".join(data_lines)

    return f"""You are resolving a conflict between two robots in a multi-agent path planning system.

Mission directive: "{directive_text}"

Two robots are about to collide and one must give way to the other:
{data_block}

Based ONLY on the directive above and the data given, decide which agent should keep priority (its current path) and which should give way (accept a new constraint and replan).

Respond with ONLY a JSON object, no other text:
{{"priority_agent": "<agent_id>", "give_way_agent": "<agent_id>", "reasoning": "<one sentence>"}}"""