"""
groundedness_check.py — can the compiler tell when a directive has no referent?

Section 4.1 shows that directives referring to absent state get answered
anyway, via silently substituted fields, differently by different models.
This asks whether that is recoverable: if the prompt explicitly permits
refusal, does the compiler use it — and does it start refusing directives it
could actually have handled?

Design is 2x2:

                    original prompt      refusal-permitted prompt
  groundable        (baseline: 100%)     false-refusal rate?
  ungroundable      silent substitution  detection rate?

Five groundable and five ungroundable directives, so each cell has n=5 rather
than n=1. Run from repo root.
"""

import sys, os, json, re, argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from src.condicbs.grounding.llm_client import call_llm
from src.condicbs.grounding.multi_directive_eval import load_states

STATE_BLOCK = """  optimal_route_cost          - cost of that robot's shortest path, ignoring all conflicts
  current_route_cost          - cost of its path under the constraints accumulated so far
  detour_from_optimal         - current_route_cost minus optimal_route_cost
  constraints_on_this_robot   - how many constraints currently apply to it
  alternative_routes_at_conflict - number of equally-optimal alternative routes (may be None)"""

PROMPT_ORIGINAL = """You are compiling a natural-language mission directive into a Python predicate for a multi-agent path planning system.

Directive: "{directive}"

At each collision between two robots, the planner has this state available for each robot:

{state}

Write a Python function that decides which robot keeps priority:

def priority(state_a, state_b, id_a, id_b):
    # state_a and state_b are dicts with the keys listed above
    # return id_a or id_b — whichever robot the directive says should be given way to
    ...

Return ONLY the function definition. No markdown fences, no explanation, no imports."""

PROMPT_REFUSAL = """You are compiling a natural-language mission directive into a Python predicate for a multi-agent path planning system.

Directive: "{directive}"

At each collision between two robots, the planner has this state available for each robot:

{state}

This is the complete state. No other information about the robots exists.

If the directive can be decided from this state, write:

def priority(state_a, state_b, id_a, id_b):
    # state_a and state_b are dicts with the keys listed above
    # return id_a or id_b — whichever robot the directive says should be given way to
    ...

If the directive refers to information that is NOT in the state above, do not
guess or substitute a proxy. Instead return exactly this single line and nothing else:

UNGROUNDABLE: <the information the directive needs that is missing>

Return ONLY the function definition or the UNGROUNDABLE line. No markdown fences, no explanation."""


GROUNDABLE = {
    "G1_detour": "Give way to whichever robot has already been pushed furthest off its original route.",
    "G2_longroute": "Give way to whichever robot has the longer journey to make in the first place.",
    "G3_threshold": ("Give way to any robot that has been detoured by more than 2. If both or "
                     "neither have, give way to the one with the shorter original journey."),
    "G4_constrained": "Give way to whichever robot is already operating under more restrictions.",
    "G5_compound": ("Give way to whichever robot has been detoured more, unless the other robot's "
                    "original journey was more than twice as long — in that case it takes priority."),
}

UNGROUNDABLE = {
    "X1_load": "Give way to whichever robot is carrying the heavier load.",
    "X2_battery": "Give way to whichever robot has less battery remaining.",
    "X3_fragile": "Give way to whichever robot is carrying fragile cargo.",
    "X4_deadline": "Give way to whichever robot has the earlier delivery deadline.",
    "X5_human": "Give way to whichever robot is escorting a human.",
}


def classify(raw):
    """-> ('refused', reason) | ('compiled', code) | ('unparseable', raw)"""
    text = raw.strip()
    text = re.sub(r'^```(?:python)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)

    if text.upper().startswith("UNGROUNDABLE"):
        return "refused", text.split(":", 1)[-1].strip()
    if "def priority" in text:
        idx = text.find("def priority")
        return "compiled", text[idx:]
    return "unparseable", text


def try_exec(code):
    ns = {}
    try:
        exec(code, ns)
    except Exception as e:
        return None, f"exec failed: {e}"
    if "priority" not in ns:
        return None, "no priority() defined"
    return ns["priority"], None


def smoke(pred, states, n=500):
    """Does it run? Returns (ran_ok, errors)."""
    errs = 0
    for s in states[:n]:
        a, b = s["agents"]
        try:
            pred(s["per_agent"][a], s["per_agent"][b], a, b)
        except Exception:
            errs += 1
    return errs == 0, errs


def run_condition(prompt_tmpl, directives, states, label):
    rows = []
    for did, text in directives.items():
        raw = call_llm(prompt_tmpl.format(directive=text, state=STATE_BLOCK),
                       max_tokens=600)
        kind, payload = classify(raw)

        row = {"id": did, "condition": label, "directive": text, "outcome": kind}
        if kind == "compiled":
            pred, err = try_exec(payload)
            if pred is None:
                row["outcome"] = "compile_error"
                row["error"] = err
            else:
                ok, errs = smoke(pred, states)
                row["runs_clean"] = ok
                row["smoke_errors"] = errs
                row["fields"] = sorted(
                    f for f in ["optimal_route_cost", "current_route_cost",
                                "detour_from_optimal", "constraints_on_this_robot",
                                "alternative_routes_at_conflict"] if f in payload)
            row["code"] = payload
        elif kind == "refused":
            row["stated_missing"] = payload
        else:
            row["raw"] = payload[:300]

        mark = {"refused": "REFUSED ", "compiled": "compiled",
                "compile_error": "ERROR   ", "unparseable": "UNPARSED"}[row["outcome"]]
        extra = row.get("stated_missing") or ", ".join(row.get("fields", []))
        print(f"  {did:16s} {mark}  {extra[:70]}")
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conditions", default="original,refusal")
    args = ap.parse_args()

    states = load_states(limit_per_log=2000)
    print(f"node states: {len(states)}\n")

    out = []
    conds = args.conditions.split(",")

    for cond in conds:
        tmpl = PROMPT_ORIGINAL if cond == "original" else PROMPT_REFUSAL
        print(f"=== condition: {cond} | GROUNDABLE (expect: compiled) ===")
        out += run_condition(tmpl, GROUNDABLE, states, cond)
        print(f"\n=== condition: {cond} | UNGROUNDABLE (expect: refused) ===")
        out += run_condition(tmpl, UNGROUNDABLE, states, cond)
        print()

    model = os.environ.get("CONDICBS_MODEL", "default").replace("/", "_")
    os.makedirs("results/tables", exist_ok=True)
    path = f"results/tables/groundedness_{model}.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"saved {path}\n")

    print("--- summary ---")
    for cond in conds:
        g = [r for r in out if r["condition"] == cond and r["id"].startswith("G")]
        x = [r for r in out if r["condition"] == cond and r["id"].startswith("X")]
        g_ref = sum(r["outcome"] == "refused" for r in g)
        x_ref = sum(r["outcome"] == "refused" for r in x)
        print(f"  {cond:9s}  groundable refused (false alarms): {g_ref}/{len(g)}"
              f"   ungroundable refused (detections): {x_ref}/{len(x)}")


if __name__ == "__main__":
    main()