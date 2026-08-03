import sys, os, json, random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../external/cbs_icbs"))

from src.condicbs.solver.instrumented_hcbs import HCBS_instrumented
from map_handler import Map, read_map, read_tasks
from low_level_policy import manhattan_distance
from agent import Agent

# --- config ---
MAP_FILE = "external/cbs_icbs/demo/room-32-32-4.map"
TASK_FILE = "external/cbs_icbs/demo/room-32-32-4-random-1.scen"
N_AGENTS = 8
RSEED = 42

# --- replicate movingai_test's setup, but call our instrumented solver ---
random.seed(RSEED)
tasks = random.sample(read_tasks(TASK_FILE), N_AGENTS)

mapstr = read_map(MAP_FILE)
Agent.id = 0
agents = []
for i in range(N_AGENTS):
    bucket, path, width, height, jStart, iStart, jGoal, iGoal, length = tasks[i]
    agents.append(Agent(iStart, jStart, iGoal, jGoal))

task_map = Map()
task_map.read_from_string(mapstr, width, height, diagonal_movements=False)

print(f"Map: {MAP_FILE}")
print(f"Agents: {N_AGENTS}, rseed: {RSEED}")
print("Running instrumented HCBS...")

solution, conflict_log = HCBS_instrumented(
    task_map, agents, use_pc=True,
    heuristic_function=manhattan_distance
)

print("Solution found:", solution is not False)
print("Number of conflicts logged:", len(conflict_log))

if conflict_log:
    print()
    print("--- First conflict ---")
    print(json.dumps(conflict_log[0], indent=2, default=str))
    print()
    print("--- Last conflict ---")
    print(json.dumps(conflict_log[-1], indent=2, default=str))

os.makedirs("results/logs", exist_ok=True)
out_path = f"results/logs/room32_{N_AGENTS}agents_rseed{RSEED}.json"
with open(out_path, "w") as f:
    json.dump(conflict_log, f, indent=2, default=str)
print(f"\nFull log saved to {out_path}")