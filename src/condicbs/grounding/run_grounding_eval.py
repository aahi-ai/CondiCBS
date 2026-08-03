import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from src.condicbs.directives.library import SCENARIOS
from src.condicbs.grounding.conflict_grounder import ground_scenario

class_b_scenarios = [s for s in SCENARIOS if s.directive_class == "B"]

results = []
for s in class_b_scenarios:
    print(f"Grounding {s.id}...")
    r = ground_scenario(s)
    results.append(r)
    status = "✓" if r.get("correct") else "✗"
    print(f"  {status} LLM said {r.get('llm_priority_agent')}, "
          f"oracle says {r.get('oracle_priority_agent')}")

n_correct = sum(1 for r in results if r.get("correct"))
print(f"\nAccuracy: {n_correct}/{len(results)}")

os.makedirs("results/tables", exist_ok=True)
with open("results/tables/grounding_eval_v1.json", "w") as f:
    json.dump(results, f, indent=2)
print("Saved to results/tables/grounding_eval_v1.json")