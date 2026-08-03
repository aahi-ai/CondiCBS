"""
predicate_stress.py — where does predicate compilation break?

Section 4 shows 100% on three directives that each map onto a single state
field. That is a narrow result. This script probes the boundary with four
harder directive forms:

  SIMPLE        one field, one comparison            (control — expect 100%)
  COMPOUND      two fields, conditional override
  THRESHOLD     absolute cutoff plus a fallback rule
  UNDERSPECIFIED  no single field is obviously correct
  UNGROUNDABLE  refers to something absent from node state

The last two have no oracle. What is measured there is behaviour: does the
model compile something, which fields does it reach for, and does the result
run without error. A compiler that silently invents state['payload_weight']
and crashes at every conflict is a real failure mode.

Run from repo root.
"""

import sys, os, json, re, argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from src.condicbs.grounding.llm_client import call_llm
from src.condicbs.grounding.multi_directive_eval import load_states
from src.condicbs.baselines.predicate_baseline import COMPILE_PROMPT, compile_predicate

STATE_FIELDS = [
    "optimal_route_cost",
    "current_route_cost",
    "detour_from_optimal",
    "constraints_on_this_robot",
    "alternative_routes_at_conflict",
]


# ---------------------------------------------------------------------------
# Oracles. Written by hand; each is the literal reading of its directive.
# ---------------------------------------------------------------------------

def _pair(s):
    a, b = s["agents"]
    return a, b, s["per_agent"][a], s["per_agent"][b]


def o_simple_detour(s):
    a, b, A, B = _pair(s)
    if A["detour_from_optimal"] == B["detour_from_optimal"]:
        return None
    return a if A["detour_from_optimal"] > B["detour_from_optimal"] else b


def o_compound(s):
    """More detour wins, unless the other robot's original journey is more
    than twice as long — then that robot takes priority instead."""
    a, b, A, B = _pair(s)
    if A["detour_from_optimal"] == B["detour_from_optimal"]:
        return None
    base, other = (a, b) if A["detour_from_optimal"] > B["detour_from_optimal"] else (b, a)
    Sb, So = s["per_agent"][base], s["per_agent"][other]
    return other if So["optimal_route_cost"] > 2 * Sb["optimal_route_cost"] else base


def o_threshold(s):
    """Detoured by more than 2 wins; if both or neither, shorter journey wins."""
    a, b, A, B = _pair(s)
    oa = A["detour_from_optimal"] > 2
    ob = B["detour_from_optimal"] > 2
    if oa != ob:
        return a if oa else b
    if A["optimal_route_cost"] == B["optimal_route_cost"]:
        return None
    return a if A["optimal_route_cost"] < B["optimal_route_cost"] else b


DIRECTIVES = {
    "S_detour": {
        "form": "SIMPLE",
        "text": ("Give way to whichever robot has already been pushed furthest "
                 "off its original route."),
        "oracle": o_simple_detour,
    },
    "C_detour_unless_longer": {
        "form": "COMPOUND",
        "text": ("Give way to whichever robot has been detoured more, unless "
                 "the other robot's original journey was longer to begin with."),
        "oracle": o_compound,
    },
    "T_detour_cutoff": {
        "form": "THRESHOLD",
        "text": ("Give way to any robot that has been detoured by more than 2. "
                 "If both or neither have, give way to the one with the shorter "
                 "original journey."),
        "oracle": o_threshold,
    },
    "U_worse_time": {
        "form": "UNDERSPECIFIED",
        "text": "Prioritise whichever robot is having a worse time of it.",
        "oracle": None,
    },
    "X_heavier_load": {
        "form": "UNGROUNDABLE",
        "text": "Give way to whichever robot is carrying the heavier load.",
        "oracle": None,
    },
    "C_detour_unless_longer": {
        "form": "COMPOUND",
        "text": ("Give way to whichever robot has been detoured more, unless "
                 "the other robot's original journey was more than twice as "
                 "long — in that case it takes priority instead."),
        "oracle": o_compound,
    },
}


def fields_referenced(code):
    return sorted({f for f in STATE_FIELDS if f in code})


def evaluate(pred, states, oracle):
    correct = scored = errors = skipped = 0
    for s in states:
        truth = oracle(s) if oracle else None
        if oracle and truth is None:
            skipped += 1
            continue
        a, b = s["agents"]
        try:
            got = pred(s["per_agent"][a], s["per_agent"][b], a, b)
        except Exception:
            errors += 1
            continue
        if oracle:
            scored += 1
            correct += (str(got) == str(truth))
    return correct, scored, errors, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="comma-separated directive ids")
    args = ap.parse_args()

    ids = args.only.split(",") if args.only else list(DIRECTIVES)
    states = load_states(limit_per_log=10000)
    print(f"node states: {len(states)}\n")

    out = {}
    for did in ids:
        d = DIRECTIVES[did]
        print(f"=== {did}  [{d['form']}] ===")
        print(f'  "{d["text"]}"\n')

        try:
            pred, code = compile_predicate(d["text"], verbose=True)
        except Exception as e:
            print(f"  COMPILATION FAILED: {e}\n")
            out[did] = {"form": d["form"], "compiled": False, "error": str(e)}
            continue

        refs = fields_referenced(code)
        correct, scored, errors, skipped = evaluate(pred, states, d["oracle"])

        rec = {
            "form": d["form"],
            "text": d["text"],
            "compiled": True,
            "code": code,
            "fields_referenced": refs,
            "runtime_errors": errors,
            "eval_total": len(states),
        }
        print(f"  fields referenced: {refs}")
        print(f"  runtime errors:    {errors}/{len(states)}")
        if d["oracle"]:
            acc = 100 * correct / scored if scored else 0.0
            rec.update({"correct": correct, "scored": scored,
                        "accuracy": acc, "ties_skipped": skipped})
            print(f"  accuracy:          {correct}/{scored} ({acc:.1f}%)"
                  f"   [{skipped} ties skipped]")
        else:
            print(f"  no oracle — behaviour only")
        print()
        out[did] = rec

    os.makedirs("results/tables", exist_ok=True)
    model = os.environ.get("CONDICBS_MODEL", "default").replace("/", "_")
    path = f"results/tables/predicate_stress_{model}.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"saved {path}")

    print("\n--- summary ---")
    for did, r in out.items():
        if not r.get("compiled"):
            print(f"  {did:24s} {r['form']:14s} FAILED TO COMPILE")
            continue
        acc = f"{r['accuracy']:.1f}%" if "accuracy" in r else "n/a"
        print(f"  {did:24s} {r['form']:14s} acc={acc:>6s}  "
              f"errs={r['runtime_errors']:<6d} fields={r['fields_referenced']}")


if __name__ == "__main__":
    main()