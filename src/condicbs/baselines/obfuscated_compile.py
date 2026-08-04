"""
obfuscated_compile.py — is predicate compilation grounding, or lexical matching?

The paper currently concedes a threat to validity: state fields are named
descriptively (detour_from_optimal) and directives use the same words
("pushed off its route"), so the model may be pattern-matching rather than
reasoning about which quantity a directive refers to.

This tests it. Three conditions over the same oracles:

  NAMED       fields named descriptively, directive uses matching language
              (the paper's current setup)
  OBFUSCATED  fields renamed m1..m5, order shuffled; directive unchanged.
              The model must infer the mapping from the field DESCRIPTIONS.
  BLIND       fields renamed AND descriptions stripped to bare type info.
              Nothing but the values themselves. Expected to fail; included
              as a floor.

Also reports accuracy stratified by delay gap, since half of mined scenarios
are decided by a single unit of cost.

Run from repo root.
"""

import sys, os, json, re, random, argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from src.condicbs.grounding.llm_client import call_llm
from src.condicbs.grounding.multi_directive_eval import load_states

# canonical field -> (obfuscated name, description shown in prompt)
FIELDS = {
    "optimal_route_cost": ("m1",
        "cost of this robot's shortest possible path, ignoring all other robots"),
    "current_route_cost": ("m2",
        "cost of the path this robot is currently assigned"),
    "detour_from_optimal": ("m3",
        "m2 minus m1"),
    "constraints_on_this_robot": ("m4",
        "how many restrictions currently apply to this robot"),
    "alternative_routes_at_conflict": ("m5",
        "how many equally-short paths this robot has available here"),
}

BLIND_DESC = {k: "a non-negative number" for k in FIELDS}


def _pair(s):
    a, b = s["agents"]
    return a, b, s["per_agent"][a], s["per_agent"][b]


def o_delay(s):
    a, b, A, B = _pair(s)
    x, y = A["detour_from_optimal"], B["detour_from_optimal"]
    return None if x == y else (a if x > y else b)


def o_longroute(s):
    a, b, A, B = _pair(s)
    x, y = A["optimal_route_cost"], B["optimal_route_cost"]
    return None if x == y else (a if x > y else b)


def o_compound(s):
    """Delay wins, unless the other's optimal route is more than 2x as long."""
    a, b, A, B = _pair(s)
    if A["detour_from_optimal"] == B["detour_from_optimal"]:
        return None
    base, other = (a, b) if A["detour_from_optimal"] > B["detour_from_optimal"] else (b, a)
    Sb, So = s["per_agent"][base], s["per_agent"][other]
    return other if So["optimal_route_cost"] > 2 * Sb["optimal_route_cost"] else base


DIRECTIVES = {
    "D_delay": {
        "text": ("Give way to whichever robot has already been pushed furthest "
                 "off its original route."),
        "oracle": o_delay,
    },
    "D_longroute": {
        "text": ("Give way to whichever robot has the longer journey to make "
                 "in the first place."),
        "oracle": o_longroute,
    },
    "D_compound": {
        "text": ("Give way to whichever robot has been detoured more, unless "
                 "the other robot's original journey was more than twice as "
                 "long — in that case it takes priority instead."),
        "oracle": o_compound,
    },
}


def state_block(condition, rng):
    if condition == "named":
        lines = [
            "  optimal_route_cost          - cost of the shortest possible path, ignoring other robots",
            "  current_route_cost          - cost of the currently assigned path",
            "  detour_from_optimal         - current_route_cost minus optimal_route_cost",
            "  constraints_on_this_robot   - how many restrictions currently apply",
            "  alternative_routes_at_conflict - how many equally-short paths are available here",
        ]
        return "\n".join(lines), {k: k for k in FIELDS}

    keys = list(FIELDS)
    rng.shuffle(keys)
    desc = BLIND_DESC if condition == "blind" else {k: FIELDS[k][1] for k in FIELDS}
    mapping = {k: FIELDS[k][0] for k in FIELDS}
    lines = [f"  {mapping[k]:4s} - {desc[k]}" for k in keys]
    return "\n".join(lines), mapping


PROMPT = """You are compiling a natural-language mission directive into a Python predicate for a multi-agent path planning system.

Directive: "{directive}"

At each collision between two robots, the planner has this state for each robot:

{state}

Write a Python function that decides which robot keeps priority:

def priority(state_a, state_b, id_a, id_b):
    # state_a and state_b are dicts keyed by the names listed above
    # return id_a or id_b — whichever robot the directive says should be given way to
    ...

Return ONLY the function definition. No markdown fences, no explanation, no imports."""


def compile_predicate(directive_text, block):
    raw = call_llm(PROMPT.format(directive=directive_text, state=block),
                   max_tokens=600)
    code = raw.strip()
    code = re.sub(r'^```(?:python)?\s*', '', code)
    code = re.sub(r'\s*```$', '', code)
    if "def priority" not in code:
        raise ValueError("no function returned")
    code = code[code.find("def priority"):]
    ns = {}
    exec(code, ns)
    return ns["priority"], code


def remap(per_agent, mapping):
    return {mapping[k]: v for k, v in per_agent.items() if k in mapping}


def evaluate(pred, states, oracle, mapping):
    buckets = {"all": [0, 0], "gap1": [0, 0], "gap2plus": [0, 0]}
    errors = 0
    for s in states:
        truth = oracle(s)
        if truth is None:
            continue
        a, b = s["agents"]
        A, B = s["per_agent"][a], s["per_agent"][b]
        try:
            got = pred(remap(A, mapping), remap(B, mapping), a, b)
        except Exception:
            errors += 1
            continue
        ok = str(got) == str(truth)
        gap = abs(A["detour_from_optimal"] - B["detour_from_optimal"])
        for key in ("all", "gap1" if gap == 1 else "gap2plus"):
            buckets[key][0] += ok
            buckets[key][1] += 1
    return buckets, errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conditions", default="named,obfuscated,blind")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    states = load_states(limit_per_log=10000)
    print(f"node states: {len(states)}\n")

    out = {}
    for cond in args.conditions.split(","):
        block, mapping = state_block(cond, rng)
        print(f"=== condition: {cond} ===")
        print(block + "\n")
        for did, d in DIRECTIVES.items():
            try:
                pred, code = compile_predicate(d["text"], block)
            except Exception as e:
                print(f"  {did:14s} COMPILE FAILED: {e}")
                out[f"{cond}/{did}"] = {"error": str(e)}
                continue
            buckets, errors = evaluate(pred, states, d["oracle"], mapping)
            c, n = buckets["all"]
            g1c, g1n = buckets["gap1"]
            g2c, g2n = buckets["gap2plus"]
            print(f"  {did:14s} {100*c/n if n else 0:5.1f}%  "
                  f"(gap=1: {100*g1c/g1n if g1n else 0:5.1f}%, "
                  f"gap>=2: {100*g2c/g2n if g2n else 0:5.1f}%)  errs={errors}")
            out[f"{cond}/{did}"] = {
                "condition": cond, "directive": did, "code": code,
                "accuracy": 100*c/n if n else 0, "n": n,
                "gap1": {"acc": 100*g1c/g1n if g1n else 0, "n": g1n},
                "gap2plus": {"acc": 100*g2c/g2n if g2n else 0, "n": g2n},
                "runtime_errors": errors,
            }
        print()

    model = os.environ.get("CONDICBS_MODEL", "default").replace("/", "_")
    os.makedirs("results/tables", exist_ok=True)
    path = f"results/tables/obfuscated_{model}_seed{args.seed}.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    main()