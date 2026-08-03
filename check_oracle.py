import sys
sys.path.insert(0, ".")
from src.condicbs.grounding.multi_directive_eval import load_states
from src.condicbs.baselines.predicate_stress import o_compound, o_simple_detour

states = load_states(limit_per_log=10000)

def argmax_route(s):
    a, b = s["agents"]
    A, B = s["per_agent"][a], s["per_agent"][b]
    if A["optimal_route_cost"] == B["optimal_route_cost"]:
        return None
    return a if A["optimal_route_cost"] > B["optimal_route_cost"] else b

scored = d_hits = r_hits = flips = 0
for s in states:
    t = o_compound(s)
    if t is None:
        continue
    scored += 1
    d = o_simple_detour(s)
    r = argmax_route(s)
    d_hits += (str(d) == str(t))
    r_hits += (str(r) == str(t))
    flips += (str(t) != str(d))

print(f"scored: {scored}")
print(f"argmax-detour matches oracle: {100*d_hits/scored:.1f}%")
print(f"argmax-route  matches oracle: {100*r_hits/scored:.1f}%")
print(f"override actually fires:      {flips} ({100*flips/scored:.1f}%)")