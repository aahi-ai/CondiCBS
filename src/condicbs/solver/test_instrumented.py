import sys, os, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../external/cbs_icbs"))

from src.condicbs.solver.instrumented_hcbs import HCBS_instrumented
from map_handler import Map, read_map, read_tasks
from low_level_policy import manhattan_distance

# small toy map, same one from explore_test.py
mapstr = '''
# . . # 
. . . .  
. . . . 
# . . # 
'''
from agent import Agent
agent1 = Agent(0, 1, 3, 2)
agent2 = Agent(1, 0, 2, 3)

m = Map()
m.read_from_string(mapstr, width=4, height=4)

solution, conflict_log = HCBS_instrumented(
    m, [agent1, agent2],
    use_pc=True,
    heuristic_function=manhattan_distance
)

print("Solution found:", solution is not False)
print("Number of conflicts logged:", len(conflict_log))
print()
print("--- First logged conflict (branch state) ---")
if conflict_log:
    print(json.dumps(conflict_log[0], indent=2, default=str))

# save full log
os.makedirs("results/logs", exist_ok=True)
with open("results/logs/toy_conflict_log.json", "w") as f:
    json.dump(conflict_log, f, indent=2, default=str)
print("\nFull log saved to results/logs/toy_conflict_log.json")