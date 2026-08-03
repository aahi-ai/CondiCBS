"""
multi_directive_eval.py — the grounding experiment, rebuilt.

1. The model receives the FULL node state with no semantic pre-labeling.
   It has to work out which quantity a directive refers to. The old harness
   read oracle_ground_truth["branch_slacks"] and passed only that, reducing
   the task to argmin over two floats.

2. Several directives run against the SAME node state, each referring to a
   different quantity. A fixed-column heuristic scores ~1/k instead of 100%,
   which is the control that makes the accuracy number mean something.
"""

import sys, os, json, glob, re, random, argparse
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from src.condicbs.grounding.llm_client import call_llm


def per_agent_constraint_counts(entry, agents):
    counts = {a: 0 for a in agents}
    for c in entry.get("branch_constraints", []):
        aid = str(c[0])
        if aid in counts:
            counts[aid] += 1
    return counts


def build_node_state(entry, root_costs):
    """Every branch-local quantity we have, for both conflicting agents."""
    ag = entry["conflicting_agents"]
    if len(ag) != 2:
        return None
    a0, a1 = str(ag[0]), str(ag[1])
    bc = entry["agent_costs_under_branch"]
    if not all(a in root_costs and a in bc for a in (a0, a1)):
        return None

    ccounts = per_agent_constraint_counts(entry, (a0, a1))
    widths = entry.get("agent_widths_at_conflict") or {}

    state = {}
    for a in (a0, a1):
        state[a] = {
            "optimal_route_cost": round(root_costs[a], 3),
            "current_route_cost": round(bc[a], 3),
            "detour_from_optimal": round(bc[a] - root_costs[a], 3),
            "constraints_on_this_robot": ccounts[a],
            "alternative_routes_at_conflict": widths.get(a),
        }
    return {
        "agents": [a0, a1],
        "per_agent": state,
        "conflict_type": entry["conflict_type"],
        "timestep": (entry["vertex_and_time"][-1]
                     if entry["conflict_type"] == "v"
                     else entry["vertex_and_time"][0][-1]),
        "branch_depth": entry["branch_num_constraints"],
        "branch_node_entry": entry["branch_node_entry"],
    }


def _argmax(state, field):
    a0, a1 = state["agents"]
    v0 = state["per_agent"][a0][field]
    v1 = state["per_agent"][a1][field]
    if v0 is None or v1 is None or v0 == v1:
        return None
    return a0 if v0 > v1 else a1


def _argmin(state, field):
    a0, a1 = state["agents"]
    v0 = state["per_agent"][a0][field]
    v1 = state["per_agent"][a1][field]
    if v0 is None or v1 is None or v0 == v1:
        return None
    return a0 if v0 < v1 else a1


DIRECTIVES = {
    "D_detour": {
        "text": ("Give way to whichever robot has already been pushed furthest "
                 "off its original route."),
        "field": "detour_from_optimal",
        "oracle": lambda s: _argmax(s, "detour_from_optimal"),
    },
    "D_longroute": {
        "text": ("Give way to whichever robot has the longer journey to make "
                 "in the first place."),
        "field": "optimal_route_cost",
        "oracle": lambda s: _argmax(s, "optimal_route_cost"),
    },
    "D_constrained": {
        "text": ("Give way to whichever robot is already operating under more "
                 "restrictions."),
        "field": "constraints_on_this_robot",
        "oracle": lambda s: _argmax(s, "constraints_on_this_robot"),
    },
    "D_shortroute": {
        "text": ("Give way to whichever robot has the shorter journey, so it "
                 "clears the area sooner."),
        "field": "optimal_route_cost",
        "oracle": lambda s: _argmin(s, "optimal_route_cost"),
    },
}


def build_prompt(directive_text, state):
    lines = []
    for a in state["agents"]:
        f = state["per_agent"][a]
        parts = [f"{k} = {v}" for k, v in f.items() if v is not None]
        lines.append(f"  Robot {a}: " + "; ".join(parts))
    block = "\n".join(lines)

    return f"""Two robots in a warehouse are about to collide and one must give way.

Mission directive: "{directive_text}"

Current situation at the moment of the conflict (search depth {state['branch_depth']}, timestep {state['timestep']}):
{block}

Work out what the directive is referring to, then decide which robot keeps
priority (holds its current route) and which gives way (is rerouted).

Respond with ONLY a JSON object and nothing else:
{{"priority_robot": "<id>", "give_way_robot": "<id>", "reasoning": "<one sentence>"}}"""


def norm(v):
    if v is None:
        return None
    d = re.sub(r'\D', '', str(v))
    return d if d else str(v).strip().lower()


def query(directive_text, state):
    raw = call_llm(build_prompt(directive_text, state))
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if not m:
        return None, raw
    try:
        return json.loads(m.group()), raw
    except json.JSONDecodeError:
        return None, raw


def load_states(limit_per_log=40):
    states = []
    for path in glob.glob("results/logs/*.json"):
        if os.path.basename(path).startswith("_"):
            continue
        try:
            log = json.load(open(path))
        except Exception:
            continue
        if not isinstance(log, list) or not log:
            continue
        root = next((c for c in log if c["branch_num_constraints"] == 0), None)
        if root is None:
            continue
        rc = root["agent_costs_under_branch"]
        n = 0
        for e in log:
            s = build_node_state(e, rc)
            if s is None:
                continue
            states.append(s)
            n += 1
            if n >= limit_per_log:
                break
    return states


def agreement_matrix(states, dids):
    """How often do two directives' oracles give the same answer?"""
    print("Oracle agreement between directives:")
    for i, d1 in enumerate(dids):
        for d2 in dids[i+1:]:
            same = tot = 0
            for s in states:
                a, b = DIRECTIVES[d1]["oracle"](s), DIRECTIVES[d2]["oracle"](s)
                if a is None or b is None:
                    continue
                tot += 1
                same += (a == b)
            if tot:
                print(f"  {d1:15s} vs {d2:15s}: {100*same/tot:5.1f}% agree ({tot} cases)")
    print()


def sample_for(states, did, n, rng):
    """Scenarios where this directive has an answer, balanced across which
    robot wins so 'always pick the first one' can't score."""
    first, second = [], []
    for s in states:
        ans = DIRECTIVES[did]["oracle"](s)
        if ans is None:
            continue
        (first if ans == s["agents"][0] else second).append((s, ans))
    rng.shuffle(first)
    rng.shuffle(second)
    half = n // 2
    out = first[:half] + second[:half]
    rng.shuffle(out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30, help="scenarios per directive")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--directives",
                    default="D_detour,D_longroute,D_shortroute,D_constrained")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    dids = args.directives.split(",")
    rng = random.Random(args.seed)

    states = load_states()
    print(f"node states: {len(states)}\n")
    agreement_matrix(states, dids)

    samples = {d: sample_for(states, d, args.n, rng) for d in dids}
    for d in dids:
        print(f"  {d:15s}: {len(samples[d])} scenarios")
    print()

    print("CONTROL — accuracy if you always read one fixed column:")
    for fixed in dids:
        hits = tot = 0
        for d in dids:
            for s, ans in samples[d]:
                g = DIRECTIVES[fixed]["oracle"](s)
                tot += 1
                hits += (g == ans)
        print(f"  always use {fixed:15s}: {hits}/{tot} ({100*hits/tot:.1f}%)")

    pos = tot = 0
    for d in dids:
        for s, ans in samples[d]:
            tot += 1
            pos += (ans == s["agents"][0])
    print(f"  always pick first robot   : {pos}/{tot} ({100*pos/tot:.1f}%)")
    print()

    if args.dry_run:
        return

    results = []
    per_directive = defaultdict(lambda: [0, 0])
    done = 0
    total_calls = sum(len(v) for v in samples.values())
    for d in dids:
        for s, ans in samples[d]:
            shown = dict(s)
            shown["agents"] = list(s["agents"])
            if rng.random() < 0.5:
                shown["agents"].reverse()
            parsed, raw = query(DIRECTIVES[d]["text"], shown)
            ok = parsed is not None and norm(parsed.get("priority_robot")) == norm(ans)
            per_directive[d][0] += int(ok)
            per_directive[d][1] += 1
            results.append({
                "directive": d,
                "branch_node_entry": s["branch_node_entry"],
                "branch_depth": s["branch_depth"],
                "state": s["per_agent"],
                "oracle": ans,
                "llm": parsed.get("priority_robot") if parsed else None,
                "reasoning": parsed.get("reasoning") if parsed else None,
                "correct": ok,
                "parse_failed": parsed is None,
            })
            done += 1
            print(f"  {done}/{total_calls}", end="\r", flush=True)

    print("\nLLM accuracy by directive:")
    tot_ok = tot_n = 0
    for d in dids:
        ok, n = per_directive[d]
        tot_ok += ok
        tot_n += n
        print(f"  {d:15s}: {ok}/{n} ({100*ok/n:.1f}%)")
    print(f"  {'OVERALL':15s}: {tot_ok}/{tot_n} ({100*tot_ok/tot_n:.1f}%)")

    os.makedirs("results/tables", exist_ok=True)
    out = f"results/tables/multi_directive_seed{args.seed}.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nsaved {out}")


if __name__ == "__main__":
    main()