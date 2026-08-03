import sys, os, time, json
from collections import defaultdict

# make the cloned repo importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../external/cbs_icbs"))

from node import CTNode
from open import CTOpen
from low_level_policy import AStar


def HCBS_instrumented(MAPF_instance, agents, use_pc=False, max_time=300,
                       low_level_policy=AStar, open_type=CTOpen,
                       conflict_log=None, **kwargs):
    """
    Copy of HCBS (external/cbs_icbs/high_level_policy.py) with a logging
    hook inserted at each conflict discovery. conflict_log, if provided,
    is a list that gets one dict appended per conflict encountered,
    recording the branch state at that moment.
    """
    if conflict_log is None:
        conflict_log = []

    OPEN = open_type()
    entry = 0
    root = CTNode(constraints=None, solution=None, cost=None, parent=None, entry=entry)
    id_to_agent = {agent.id: agent for agent in agents}
    root.constraints = set()
    root.solution = {agent.id: low_level_policy(MAPF_instance, agent, use_pc=use_pc,
                                                 constraints=root.extract_all_constraints(), **kwargs)
                      for agent in agents}
    root.cost = sum([root.solution[agent.id][1] for agent in agents])
    OPEN.add_node(root)
    start_time = time.time()

    while len(OPEN) != 0:
        p = OPEN.get_best_node()

        conflict = p.validate_conflicts(use_pc=use_pc)
        runtime = time.time() - start_time
        if runtime > max_time:
            return False, conflict_log

        if not conflict:
            solution = {agent_id: p.solution[agent_id][0:2] for agent_id in p.solution}
            return solution, conflict_log

        if conflict[0] == 'v':
            conflicting_agents = conflict[1:-3]
            vertex_and_time = conflict[-3:]
        else:
            conflicting_agents = conflict[1:3]
            vertex_and_time1 = conflict[3:]
            vertex_and_time2 = vertex_and_time1[2:4] + vertex_and_time1[0:2] + vertex_and_time1[-1:]
            vertex_and_time = (vertex_and_time1, vertex_and_time2)

        # --- widths at conflict: alternative-path counts from CBS+PC's own DAG search ---
        if conflict[0] == 'v':
            conflict_t = vertex_and_time[-1]
        else:
            conflict_t = vertex_and_time[0][-1]

        agent_widths_at_conflict = {}
        for aid in conflicting_agents:
            widths = p.solution[aid][2] if len(p.solution[aid]) > 2 else {}
            agent_widths_at_conflict[aid] = widths.get(conflict_t, 1) or 1

        # --- LOGGING HOOK: branch state at the moment of conflict ---
        branch_constraints = p.extract_all_constraints()
        agent_costs_under_branch = {
            aid: p.solution[aid][1] for aid in p.solution
        }
        conflict_log.append({
            "conflict_type": conflict[0],
            "conflicting_agents": list(conflicting_agents),
            "vertex_and_time": vertex_and_time,
            "branch_num_constraints": len(branch_constraints),
            "branch_constraints": [list(c) for c in branch_constraints],
            "agent_costs_under_branch": agent_costs_under_branch,
            "agent_widths_at_conflict": agent_widths_at_conflict,
            "branch_total_cost": p.cost,
            "branch_node_entry": p.entry,
        })
        # --- end hook ---

        if conflict[0] == 'e':
            for i in range(2):
                a = CTNode(constraints=set(), solution=p.solution.copy(), cost=None, parent=p, entry=0)
                a.constraints.add((conflicting_agents[i], *vertex_and_time[i]))
                a.solution[conflicting_agents[i]] = low_level_policy(
                    MAPF_instance, id_to_agent[conflicting_agents[i]], use_pc=use_pc,
                    constraints=a.extract_all_constraints(), **kwargs)
                a.cost = sum([a.solution[agent.id][1] for agent in agents])
                entry += 1
                if a.cost < float('inf'):
                    a.entry = entry
                    OPEN.add_node(a)
        else:
            for i in conflicting_agents:
                a = CTNode(constraints=set(), solution=p.solution.copy(), cost=None, parent=p, entry=0)
                for agent_id in conflicting_agents:
                    if i != agent_id:
                        a.constraints.add((agent_id, *vertex_and_time))
                        a.solution[agent_id] = low_level_policy(
                            MAPF_instance, id_to_agent[agent_id], use_pc=use_pc,
                            constraints=a.extract_all_constraints(), **kwargs)
                a.cost = sum([a.solution[agent.id][1] for agent in agents])
                entry += 1
                if a.cost < float('inf'):
                    a.entry = entry
                    OPEN.add_node(a)

    return False, conflict_log