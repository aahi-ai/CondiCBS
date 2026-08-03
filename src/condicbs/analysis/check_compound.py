import sys, json
sys.path.insert(0, ".")

from src.condicbs.grounding.multi_directive_eval import load_states
from src.condicbs.baselines.predicate_stress import o_compound, o_simple_detour

code = json.load(open("results/tables/predicate_stress_default.json"))
ns = {}
exec(code["C_detour_unless_longer"]["code"], ns)
pred = ns["priority"]

states = load_states(limit_per_log=10000)

agree_with_detour = 0
agree_with_oracle = 0
scored = 0
shown = 0

for s in states:
    truth = o_compound(s)
    if truth is None:
        continue
    a, b = s["agents"]
    A, B = s["per_agent"][a], s["per_agent"][b]
    got = str(pred(A, B, a, b))
    detour_pick = str(o_simple_detour(s))
    scored += 1
    agree_with_oracle += (got == str(truth))
    agree_with_detour += (got == detour_pick)

    # show a few cases where the two readings diverge
    if shown < 5 and str(truth) != detour_pick:
        print(f"conflict: {a} detour={A['detour_from_optimal']} route={A['optimal_route_cost']} | "
              f"{b} detour={B['detour_from_optimal']} route={B['optimal_route_cost']}")
        print(f"  override reading (oracle): {truth}")
        print(f"  argmax-detour:             {detour_pick}")
        print(f"  predicate returned:        {got}\n")
        shown += 1

print(f"scored: {scored}")
print(f"predicate matches override reading: {agree_with_oracle} ({100*agree_with_oracle/scored:.1f}%)")
print(f"predicate matches argmax-detour:    {agree_with_detour} ({100*agree_with_detour/scored:.1f}%)")