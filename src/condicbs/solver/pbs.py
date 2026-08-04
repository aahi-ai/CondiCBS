"""
pbs.py — Priority-Based Search with the same instrumentation as our CBS.

Why: every result in the paper is measured on CBS+PC. PBS coordinates without
a constraint tree — nodes are partial priority orderings, and a lower-priority
agent plans around higher-priority agents' whole paths rather than around
timestep-specific vertex/edge constraints. If delay asymmetry and width
degeneracy behave the same way here, they are properties of priority-based
coordination generally; if width does NOT collapse, then Section 4.3 is
specifically about constraint-tree accumulation, which is a sharper claim.

Depth-first search over a priority tree. At each node, find a collision
between two agents with no priority relation between them, and branch on the
two possible orderings. Plan agents in topological order; each agent avoids
the paths of all higher-priority agents, encoded as vertex and edge
constraints for the low-level A*.

Instrumented at every collision with: per-agent cost under the current
ordering, individually-optimal cost (hence delay), number of higher-priority
agents, and alternative-route width at the collision timestep.

Place at src/condicbs/solver/pbs.py, run from repo root.
"""

import sys, os, time, json, random, argparse
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../external/cbs_icbs"))

from low_level_policy import AStar, manhattan_distance
from map_handler import Map, read_map, read_tasks
from agent import Agent


# ---------------------------------------------------------------------------
# path helpers
# ---------------------------------------------------------------------------

def pos_at(path, t):
    """Where the agent is at time t; agents rest at their goal after arrival."""
    if not path:
        return None
    if t < len(path):
        return (path[t].i, path[t].j)
    return (path[-1].i, path[-1].j)


def constraints_from_paths(low_id, higher_paths, horizon):
    """
    Encode 'avoid every higher-priority agent's path' as constraints for
    agent low_id, in the format the low-level A* expects:
      vertex: (agent, i, j, t)
      edge:   (agent, i1, j1, i2, j2, t)   -- forbids moving i1,j1 -> i2,j2 at t
    A higher-priority agent parked on its goal is handled by extending its
    occupancy to the horizon.
    """
    cons = set()
    for hp in higher_paths:
        if not hp:
            continue
        for t in range(horizon + 1):
            i, j = pos_at(hp, t)
            cons.add((low_id, i, j, t))
            if t < horizon:
                ni, nj = pos_at(hp, t + 1)
                if (ni, nj) != (i, j):
                    # forbid the swap: low agent moving (ni,nj) -> (i,j) at t+1
                    cons.add((low_id, ni, nj, i, j, t + 1))
    return cons


def first_collision(solution, agent_ids, horizon):
    """Earliest (t, a, b, kind) collision. kind in {'v','e'}."""
    for t in range(horizon + 1):
        occupied = {}
        for a in agent_ids:
            pa = pos_at(solution[a][0], t)
            if pa is None:
                continue
            if pa in occupied:
                return t, occupied[pa], a, 'v'
            occupied[pa] = a
        for idx, a in enumerate(agent_ids):
            pa_t = pos_at(solution[a][0], t)
            pa_n = pos_at(solution[a][0], t + 1)
            if pa_t is None or pa_n is None or pa_t == pa_n:
                continue
            for b in agent_ids[idx + 1:]:
                pb_t = pos_at(solution[b][0], t)
                pb_n = pos_at(solution[b][0], t + 1)
                if pb_t is None or pb_n is None:
                    continue
                if pa_t == pb_n and pa_n == pb_t:
                    return t, a, b, 'e'
    return None


def topological_order(agent_ids, pairs):
    """pairs is a set of (high, low). Returns an order, or None if cyclic."""
    succ = defaultdict(set)
    indeg = {a: 0 for a in agent_ids}
    for hi, lo in pairs:
        if lo not in succ[hi]:
            succ[hi].add(lo)
            indeg[lo] += 1
    ready = [a for a in agent_ids if indeg[a] == 0]
    order = []
    while ready:
        a = ready.pop()
        order.append(a)
        for b in succ[a]:
            indeg[b] -= 1
            if indeg[b] == 0:
                ready.append(b)
    return order if len(order) == len(agent_ids) else None


def higher_than(a, pairs):
    """All agents that must be planned before a (transitively)."""
    out, stack = set(), [a]
    while stack:
        cur = stack.pop()
        for hi, lo in pairs:
            if lo == cur and hi not in out:
                out.add(hi)
                stack.append(hi)
    return out


# ---------------------------------------------------------------------------
# PBS
# ---------------------------------------------------------------------------

def PBS(MAPF_instance, agents, max_time=60, use_pc=True, horizon_mult=3,
        conflict_log=None, **kwargs):
    """
    :return: (solution|False, stats). conflict_log, if given, receives one
             dict per collision encountered, mirroring the CBS instrumentation.
    """
    if conflict_log is None:
        conflict_log = []

    ids = [a.id for a in agents]
    id_to_agent = {a.id: a for a in agents}
    start = time.time()

    def plan(aid, pairs, horizon, known_paths):
        """Plan aid around the paths of every higher-priority agent."""
        hi = higher_than(aid, pairs)
        higher_paths = [known_paths[h][0] for h in hi
                        if h in known_paths and known_paths[h]]
        cons = constraints_from_paths(aid, higher_paths, horizon)
        return AStar(MAPF_instance, id_to_agent[aid], use_pc=use_pc,
                     constraints=cons, **kwargs)

    # root: everyone on their individually optimal path
    root_solution = {}
    for aid in ids:
        r = AStar(MAPF_instance, id_to_agent[aid], use_pc=use_pc,
                  constraints=set(), **kwargs)
        if r is None or r[1] == float('inf'):
            return False, {"error": "no individual path", "conflicts": 0}
        root_solution[aid] = r
    root_costs = {str(aid): root_solution[aid][1] for aid in ids}
    horizon = int(horizon_mult * max(root_solution[a][1] for a in ids)) + len(ids)

    stats = {"nodes": 0, "conflicts": 0, "max_depth": 0, "cycles": 0,
             "replan_failures": 0}

    def widths_of(res, t):
        if res is None or len(res) < 3 or not res[2]:
            return None
        w = res[2]
        if not w:
            return None
        return w.get(min(t, max(w.keys())))

    def log_collision(t, a, b, kind, solution, pairs, depth):
        conflict_log.append({
            "conflict_type": kind,
            "conflicting_agents": [a, b],
            "timestep": t,
            "branch_depth": depth,
            "n_priority_pairs": len(pairs),
            "agent_costs_under_branch": {str(x): solution[x][1] for x in solution},
            "root_costs": root_costs,
            "higher_priority_count": {str(x): len(higher_than(x, pairs)) for x in (a, b)},
            "agent_widths_at_conflict": {str(x): widths_of(solution[x], t) for x in (a, b)},
        })

    def search(pairs, solution, depth):
        stats["nodes"] += 1
        stats["max_depth"] = max(stats["max_depth"], depth)
        if time.time() - start > max_time:
            return None                      # timeout sentinel

        col = first_collision(solution, ids, horizon)
        if col is None:
            return solution
        t, a, b, kind = col
        stats["conflicts"] += 1
        log_collision(t, a, b, kind, solution, pairs, depth)

        children = []
        for hi, lo in ((a, b), (b, a)):
            new_pairs = set(pairs) | {(hi, lo)}
            order = topological_order(ids, new_pairs)
            if order is None:
                stats["cycles"] += 1
                continue
            built, ok = {}, True
            for aid in order:
                r = plan(aid, new_pairs, horizon, built)
                if r is None or r[1] == float('inf'):
                    stats["replan_failures"] += 1
                    ok = False
                    break
                built[aid] = r
            if ok:
                children.append((sum(built[x][1] for x in ids), new_pairs, built))

        children.sort(key=lambda c: c[0])     # greedy: cheaper child first
        for _, np_, ns in children:
            res = search(np_, ns, depth + 1)
            if res is None:                   # timeout propagates
                return None
            if res is not False:
                return res
        return False

    sys.setrecursionlimit(10000)
    out = search(set(), root_solution, 0)
    runtime = time.time() - start
    stats.update(runtime=runtime, timed_out=(out is None))
    if out is None or out is False:
        return False, stats
    stats["cost"] = sum(out[a][1] for a in ids)
    return out, stats


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--maps", default="room-32-32-4,maze-32-32-2,empty-32-32")
    ap.add_argument("--agents", default="8,12,16")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--max-time", type=float, default=60)
    ap.add_argument("--horizon-mult", type=float, default=3)
    ap.add_argument("--outdir", default="results/pbs_logs")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    summary = []
    for mp in args.maps.split(","):
        for na in [int(x) for x in args.agents.split(",")]:
            for rs in range(args.seeds):
                m, agents = load_instance(mp, na, rs)
                log = []
                sol, st = PBS(m, agents, max_time=args.max_time,
                              horizon_mult=args.horizon_mult,
                              heuristic_function=manhattan_distance,
                              conflict_log=log)
                tag = f"{mp}_{na}agents_rseed{rs}"
                status = ("solved" if sol is not False
                          else ("TIMEOUT" if st.get("timed_out") else "FAILED"))
                print(f"  {tag:34s} {status:8s} "
                      f"cost={st.get('cost','-'):>6} nodes={st.get('nodes',0):>5} "
                      f"conflicts={st.get('conflicts',0):>5} "
                      f"{st.get('runtime',0):>6.1f}s")
                if log:
                    with open(f"{args.outdir}/{tag}.json", "w") as f:
                        json.dump(log, f)
                summary.append({"instance": tag, "status": status, **st})

    with open(f"{args.outdir}/_summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)
    solved = sum(1 for s in summary if s["status"] == "solved")
    print(f"\n{solved}/{len(summary)} solved. logs in {args.outdir}/")


if __name__ == "__main__":
    main()