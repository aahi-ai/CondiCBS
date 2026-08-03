"""
predicate_baseline.py — the strong static baseline.

CaStL/AutoTAMP-style: ONE LLM call, before search. The model compiles the
directive into a Python predicate over node state. CBS then evaluates that
predicate at every conflict — no further LLM calls.

If this matches per-conflict querying, the per-conflict architecture is
unnecessary and the paper's claim has to be about WHERE grounding is
evaluated (branch state vs root-frozen answer), not how often a model runs.
"""

import sys, os, json, glob, re, argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from src.condicbs.grounding.llm_client import call_llm
from src.condicbs.grounding.multi_directive_eval import (
    DIRECTIVES, build_node_state, load_states,
)

COMPILE_PROMPT = """You are compiling a natural-language mission directive into a Python predicate for a multi-agent path planning system.

Directive: "{directive}"

At each collision between two robots, the planner has this state available for each robot:

  optimal_route_cost          - cost of that robot's shortest path, ignoring all conflicts
  current_route_cost          - cost of its path under the constraints accumulated so far
  detour_from_optimal         - current_route_cost minus optimal_route_cost
  constraints_on_this_robot   - how many constraints currently apply to it
  alternative_routes_at_conflict - number of equally-optimal alternative routes (may be None)

Write a Python function that decides which robot keeps priority:

def priority(state_a, state_b, id_a, id_b):
    # state_a and state_b are dicts with the keys listed above
    # return id_a or id_b — whichever robot the directive says should be given way to
    ...

Return ONLY the function definition. No markdown fences, no explanation, no imports."""


def compile_predicate(directive_text, verbose=True):
    raw = call_llm(COMPILE_PROMPT.format(directive=directive_text), max_tokens=500)
    code = raw.strip()
    code = re.sub(r'^```(?:python)?\s*', '', code)
    code = re.sub(r'\s*```$', '', code)
    if verbose:
        print("--- compiled predicate ---")
        print(code)
        print("--------------------------\n")
    ns = {}
    exec(code, ns)
    if "priority" not in ns:
        raise ValueError("model did not define priority()")
    return ns["priority"], code


def evaluate(pred, states, directive_id):
    oracle = DIRECTIVES[directive_id]["oracle"]
    correct = total = errors = 0
    for s in states:
        truth = oracle(s)
        if truth is None:
            continue
        a, b = s["agents"]
        try:
            got = pred(s["per_agent"][a], s["per_agent"][b], a, b)
        except Exception:
            errors += 1
            total += 1
            continue
        total += 1
        correct += (str(got) == str(truth))
    return correct, total, errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--directives",
                    default="D_detour,D_longroute,D_shortroute")
    args = ap.parse_args()

    states = load_states(limit_per_log=10000)
    print(f"node states: {len(states)}\n")

    out = {}
    for did in args.directives.split(","):
        print(f"=== {did} ===")
        print(f'directive: "{DIRECTIVES[did]["text"]}"\n')
        try:
            pred, code = compile_predicate(DIRECTIVES[did]["text"])
        except Exception as e:
            print(f"compilation failed: {e}\n")
            out[did] = {"error": str(e)}
            continue
        c, t, e = evaluate(pred, states, did)
        print(f"accuracy: {c}/{t} ({100*c/t:.1f}%)   runtime errors: {e}\n")
        out[did] = {"code": code, "correct": c, "total": t,
                    "accuracy": 100*c/t, "errors": e}

    os.makedirs("results/tables", exist_ok=True)
    model = os.environ.get("CONDICBS_MODEL", "default").replace("/", "_")
    path = f"results/tables/predicate_baseline_{model}.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    main()