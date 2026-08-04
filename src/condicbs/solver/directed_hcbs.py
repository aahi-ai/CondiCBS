"""
directed_hcbs.py — does the compiled predicate actually change solver behaviour?

At each conflict the predicate (compiled once, pure Python, no LLM in the
loop) says which agent should keep priority. Three modes:

  baseline  vanilla CBS. The predicate is consulted only to RECORD what it
            would have wanted, so we can score the unsteered solution's
            compliance. Branching is untouched.
  prefer    compliant branch is ordered first in OPEN. Note that CTNode.__lt__
            orders by cost, then conflict count, then entry — so this only
            fires on double ties and is expected to be nearly inert. That is
            itself the finding: preference cannot steer an optimal solver.
  prune     only the compliant branch is expanded. Solves the directive-
            constrained problem; gives up optimality and completeness w.r.t.
            the unconstrained problem.

Compliance: walk the goal node's ancestry; at each conflict along that path,
did the agent the predicate wanted to yield actually yield?

Place at src/condicbs/solver/directed_hcbs.py, run from repo root.
"""

import sys, os, time, json, random, argparse
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../external/cbs_icbs"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from node import CTNode
from open import CTOpen
from low_level_policy import AStar, manhattan_distance
from map_handler import Map, read_map, read_tasks
from agent import Agent


def build_pair_state(p, agents_pair, root_costs, constraints):
    """Node-local state for the two conflicting agents, matching the schema
    the predicate was compiled against."""
    ccount = defaultdict(int)
    for c in constraints:
        ccount[str(c[0])] += 1
    out = {}
    for aid in agents_pair:
        k = str(aid)
        cur = p.solution[aid][1]
        out[k] = {
            "optimal_route_cost": root_costs[k],
            "current_route_cost": cur,
            "detour_from_optimal": cur - root_costs[k],
            "constraints_on_this_robot": ccount[k],
            "alternative_routes_at_conflict": None,
        }
    return out


def HCBS_directed(MAPF_instance, agents, use_pc=False, max_time=60,
                  low_level_policy=AStar, open_type=CTOpen,
                  predicate=None, mode="prefer", record_only=False,
                  debug=False, **kwargs):
    """
    :param predicate: f(state_a, state_b, id_a, id_b) -> id of the agent that
                      KEEPS priority (the other yields). None = vanilla CBS.
    :param record_only: consult the predicate but do not let it affect search.
    :return: (solution|False, stats)
    """
    OPEN = open_type()
    entry = 0
    root = CTNode(constraints=None, solution=None, cost=None, parent=None, entry=entry)
    id_to_agent = {a.id: a for a in agents}
    root.constraints = set()
    root.solution = {a.id: low_level_policy(MAPF_instance, a, use_pc=use_pc,
                                            constraints=root.extract_all_constraints(),
                                            **kwargs) for a in agents}
    root.cost = sum(root.solution[a.id][1] for a in agents)
    OPEN.add_node(root)

    root_costs = {str(a.id): root.solution[a.id][1] for a in agents}

    wanted = {}           # parent node entry -> (a0, a1, preferred_priority_agent)
    constrained_by = {}   # child entry -> (parent entry, agent that was constrained)

    stats = {"nodes_created": 0, "conflicts": 0, "predicate_calls": 0,
             "predicate_errors": 0, "branches_pruned": 0}
    start = time.time()

    while len(OPEN) != 0:
        p = OPEN.get_best_node()
        conflict = p.validate_conflicts(use_pc=use_pc)
        runtime = time.time() - start
        if runtime > max_time:
            stats.update(runtime=runtime, timed_out=True, nodes_created=entry + 1)
            return False, stats

        if not conflict:
            solution = {aid: p.solution[aid][0:2] for aid in p.solution}
            stats.update(runtime=runtime, timed_out=False,
                         nodes_created=entry + 1, cost=p.cost)
            stats["compliance"] = _compliance(p, wanted, constrained_by, debug)
            return solution, stats

        stats["conflicts"] += 1

        if conflict[0] == 'v':
            ca = conflict[1:-3]
            vt = conflict[-3:]
        else:
            ca = conflict[1:3]
            vt1 = conflict[3:]
            vt2 = vt1[2:4] + vt1[0:2] + vt1[-1:]
            vt = (vt1, vt2)

        prefer = None
        if predicate is not None and len(ca) == 2:
            st = build_pair_state(p, ca, root_costs, p.extract_all_constraints())
            a0, a1 = str(ca[0]), str(ca[1])
            try:
                prefer = str(predicate(st[a0], st[a1], a0, a1))
                stats["predicate_calls"] += 1
                if prefer not in (a0, a1):
                    prefer = None
            except Exception:
                stats["predicate_errors"] += 1
                prefer = None
            if prefer is not None:
                wanted[p.entry] = (a0, a1, prefer)

        steering = (prefer is not None) and (not record_only)

        if conflict[0] == 'e':
            for i in range(2):
                yielder = str(ca[i])              # this branch constrains ca[i]
                compliant = (prefer is not None and yielder != prefer)
                if steering and mode == "prune" and not compliant:
                    stats["branches_pruned"] += 1
                    continue
                a = CTNode(constraints=set(), solution=p.solution.copy(),
                           cost=None, parent=p, entry=0)
                a.constraints.add((ca[i], *vt[i]))
                a.solution[ca[i]] = low_level_policy(
                    MAPF_instance, id_to_agent[ca[i]], use_pc=use_pc,
                    constraints=a.extract_all_constraints(), **kwargs)
                a.cost = sum(a.solution[x.id][1] for x in agents)
                entry += 1
                if a.cost < float('inf'):
                    constrained_by[entry] = (p.entry, yielder)
                    a.entry = -entry if (steering and mode == "prefer" and compliant) else entry
                    OPEN.add_node(a)
        else:
            for i in ca:
                # branch i: agent i KEEPS the vertex, every other agent yields
                yielders = [str(x) for x in ca if x != i]
                compliant = (prefer is not None and str(i) == prefer)
                if steering and mode == "prune" and not compliant:
                    stats["branches_pruned"] += 1
                    continue
                a = CTNode(constraints=set(), solution=p.solution.copy(),
                           cost=None, parent=p, entry=0)
                for agent_id in ca:
                    if i != agent_id:
                        a.constraints.add((agent_id, *vt))
                        a.solution[agent_id] = low_level_policy(
                            MAPF_instance, id_to_agent[agent_id], use_pc=use_pc,
                            constraints=a.extract_all_constraints(), **kwargs)
                a.cost = sum(a.solution[x.id][1] for x in agents)
                entry += 1
                if a.cost < float('inf'):
                    constrained_by[entry] = (p.entry, yielders[0] if yielders else None)
                    a.entry = -entry if (steering and mode == "prefer" and compliant) else entry
                    OPEN.add_node(a)

    stats.update(runtime=time.time() - start, timed_out=False, nodes_created=entry + 1)
    return False, stats


def _compliance(goal, wanted, constrained_by, debug=False):
    """Fraction of decisions along the solution's ancestry that follow the
    predicate. A decision is compliant when the agent that was constrained
    (i.e. yielded) is NOT the one the predicate wanted to keep priority."""
    if not wanted:
        return None
    hits = total = 0
    cur = goal
    trace = []
    while cur.parent is not None:
        rec = constrained_by.get(abs(cur.entry))
        if rec:
            parent_entry, yielder = rec
            w = wanted.get(parent_entry)
            if w and yielder is not None:
                a0, a1, prefer = w
                ok = (yielder != prefer)
                total += 1
                hits += ok
                trace.append((parent_entry, f"pair=({a0},{a1})",
                              f"prefer={prefer}", f"yielded={yielder}",
                              "OK" if ok else "violates"))
        cur = cur.parent
    if debug:
        print("    ancestry decisions (leaf -> root):")
        for t in trace:
            print("     ", *t)
    return (hits / total) if total else None


# ---------------------------------------------------------------------------

def load_instance(map_name, n_agents, rseed):
    base = "external/cbs_icbs/demo"
    tasks = read_tasks(f"{base}/{map_name}-random-1.scen")
    mapstr = read_map(f"{base}/{map_name}.map")
    random.seed(rseed)
    picked = random.sample(tasks, n_agents)
    Agent.id = 0
    agents, width, height = [], None, None
    for t in picked:
        bucket, path, width, height, jS, iS, jG, iG, length = t
        agents.append(Agent(iS, jS, iG, jG))
    m = Map()
    m.read_from_string(mapstr, width, height, diagonal_movements=False)
    return m, agents


DELAY_PREDICATE_SRC = """
def priority(state_a, state_b, id_a, id_b):
    da = state_a['detour_from_optimal']
    db = state_b['detour_from_optimal']
    if da > db:
        return id_a
    elif db > da:
        return id_b
    return id_a if id_a < id_b else id_b
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-time", type=float, default=60)
    ap.add_argument("--debug-first", action="store_true",
                    help="print ancestry decisions for the first instance")
    ap.add_argument("--predicate-file", default=None)
    args = ap.parse_args()

    if args.predicate_file:
        d = json.load(open(args.predicate_file))
        src = d["S_detour"]["code"]
    else:
        src = DELAY_PREDICATE_SRC
    ns = {}
    exec(src, ns)
    pred = ns["priority"]

    instances = [
        ("room-32-32-4", 8, 42), ("room-32-32-4", 12, 1),
        ("room-32-32-4", 12, 3), ("room-32-32-4", 12, 8),
        ("room-32-32-4", 16, 2), ("maze-32-32-2", 10, 239),
    ]

    rows = []
    print(f"{'instance':26s} {'mode':9s} {'cost':>6s} {'nodes':>7s} "
          f"{'time':>7s} {'compliance':>11s}")
    for idx, (mp, na, rs) in enumerate(instances):
        for mode, rec in (("baseline", True), ("prefer", False), ("prune", False)):
            m, agents = load_instance(mp, na, rs)
            dbg = args.debug_first and idx == 0
            if dbg:
                print(f"  --- debug: {mp}_{na}a_r{rs} / {mode} ---")
            sol, st = HCBS_directed(m, agents, use_pc=True, max_time=args.max_time,
                                    heuristic_function=manhattan_distance,
                                    predicate=pred, mode=mode, record_only=rec,
                                    debug=dbg)
            label = f"{mp}_{na}a_r{rs}"
            comp = st.get("compliance")
            print(f"{label:26s} {mode:9s} "
                  f"{st.get('cost', '-'):>6} {st.get('nodes_created', '-'):>7} "
                  f"{st.get('runtime', 0):>7.2f} "
                  f"{(f'{100*comp:.0f}%' if comp is not None else '-'):>11s}"
                  f"{'  TIMEOUT' if st.get('timed_out') else ''}"
                  f"{'  NO SOLUTION' if (sol is False and not st.get('timed_out')) else ''}")
            rows.append({"instance": label, "mode": mode,
                         "solved": sol is not False, **st})
        print()

    # aggregate
    def avg(mode, key):
        vals = [r[key] for r in rows if r["mode"] == mode and r.get(key) is not None]
        return sum(vals) / len(vals) if vals else None

    print("--- averages over solved instances ---")
    for mode in ("baseline", "prefer", "prune"):
        c = avg(mode, "compliance")
        print(f"  {mode:9s} cost={avg(mode,'cost'):.1f}  "
              f"nodes={avg(mode,'nodes_created'):.0f}  "
              f"compliance={100*c:.1f}%" if c is not None else f"  {mode}: n/a")

    os.makedirs("results/tables", exist_ok=True)
    with open("results/tables/directed_cbs.json", "w") as f:
        json.dump(rows, f, indent=2, default=str)
    print("\nsaved results/tables/directed_cbs.json")


if __name__ == "__main__":
    main()