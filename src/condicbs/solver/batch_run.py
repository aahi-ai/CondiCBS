import sys, os, json, random, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../external/cbs_icbs"))

from src.condicbs.solver.instrumented_hcbs import HCBS_instrumented
from map_handler import Map, read_map, read_tasks
from low_level_policy import manhattan_distance
from agent import Agent

# --- batch config: add/remove instances here ---
INSTANCES = [
    {"map": "empty-32-32", "n_agents": 10, "rseed": 1},
    {"map": "empty-32-32", "n_agents": 20, "rseed": 1},
    {"map": "empty-32-32", "n_agents": 30, "rseed": 2},   # new — more agents, more conflicts to test
    {"map": "room-32-32-4", "n_agents": 8,  "rseed": 42},
    {"map": "room-32-32-4", "n_agents": 12, "rseed": 1},
    {"map": "room-32-32-4", "n_agents": 12, "rseed": 42},
    {"map": "maze-32-32-2", "n_agents": 10, "rseed": 239},
    {"map": "maze-32-32-2", "n_agents": 25, "rseed": 7},
    {"map": "room-32-32-4", "n_agents": 12, "rseed": 3},
    {"map": "room-32-32-4", "n_agents": 12, "rseed": 8},
    {"map": "room-32-32-4", "n_agents": 16, "rseed": 2},
]

MAX_TIME_SECONDS = 60  # per-instance cutoff — tune this later once you know your real budget
DEMO_DIR = "external/cbs_icbs/demo"
OUT_DIR = "results/logs"


def run_one(map_name, n_agents, rseed):
    map_file = f"{DEMO_DIR}/{map_name}.map"
    task_file = f"{DEMO_DIR}/{map_name}-random-1.scen"

    random.seed(rseed)
    tasks = random.sample(read_tasks(task_file), n_agents)

    mapstr = read_map(map_file)
    Agent.id = 0
    agents = []
    for i in range(n_agents):
        bucket, path, width, height, jStart, iStart, jGoal, iGoal, length = tasks[i]
        agents.append(Agent(iStart, jStart, iGoal, jGoal))

    task_map = Map()
    task_map.read_from_string(mapstr, width, height, diagonal_movements=False)

    start = time.time()
    solution, conflict_log = HCBS_instrumented(
        task_map, agents, use_pc=True,
        max_time=MAX_TIME_SECONDS,
        heuristic_function=manhattan_distance
    )
    elapsed = time.time() - start

    timed_out = solution is False
    return {
        "map": map_name,
        "n_agents": n_agents,
        "rseed": rseed,
        "solved": not timed_out,
        "timed_out": timed_out,
        "runtime_seconds": round(elapsed, 3),
        "num_conflicts_logged": len(conflict_log),
    }, conflict_log


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    summary = []

    for cfg in INSTANCES:
        label = f"{cfg['map']}_{cfg['n_agents']}agents_rseed{cfg['rseed']}"
        print(f"Running {label} (timeout={MAX_TIME_SECONDS}s)...")

        try:
            result, conflict_log = run_one(cfg["map"], cfg["n_agents"], cfg["rseed"])
        except Exception as e:
            print(f"  ERROR: {e}")
            summary.append({
                "map": cfg["map"], "n_agents": cfg["n_agents"], "rseed": cfg["rseed"],
                "solved": False, "timed_out": False, "error": str(e),
                "runtime_seconds": None, "num_conflicts_logged": None,
            })
            continue

        status = "TIMED OUT" if result["timed_out"] else "solved"
        print(f"  {status} — {result['runtime_seconds']}s, "
              f"{result['num_conflicts_logged']} conflicts logged")

        with open(f"{OUT_DIR}/{label}.json", "w") as f:
            json.dump(conflict_log, f, indent=2, default=str)

        summary.append(result)

    summary_path = f"{OUT_DIR}/_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"\nDone. Summary saved to {summary_path}")
    print(f"{sum(r['solved'] for r in summary)}/{len(summary)} instances solved within {MAX_TIME_SECONDS}s")


if __name__ == "__main__":
    main()