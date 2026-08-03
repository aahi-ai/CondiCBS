"""
Runs many instances automatically across a range of rseeds, at agent
counts already shown to produce B02 divergence (12, 16), to scale up
the confirmed-divergent scenario pool beyond n=3.
"""

import sys, os, json, random, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../external/cbs_icbs"))

from src.condicbs.solver.instrumented_hcbs import HCBS_instrumented
from map_handler import Map, read_map, read_tasks
from low_level_policy import manhattan_distance
from agent import Agent

DEMO_DIR = "external/cbs_icbs/demo"
OUT_DIR = "results/logs"
MAX_TIME_SECONDS = 30  # kept tight — we want MANY instances, not a few slow ones

SWEEP = (
    [{"map": "room-32-32-4", "n_agents": 12, "rseed": r} for r in range(30, 100)] +
    [{"map": "room-32-32-4", "n_agents": 16, "rseed": r} for r in range(20, 70)] +
    [{"map": "room-32-32-4", "n_agents": 20, "rseed": r} for r in range(0, 40)] +
    [{"map": "maze-32-32-2", "n_agents": 15, "rseed": r} for r in range(0, 30)] +
    [{"map": "maze-32-32-2", "n_agents": 20, "rseed": r} for r in range(0, 30)]
)


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
    return solution is not False, elapsed, conflict_log


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    summary = []

    for cfg in SWEEP:
        label = f"{cfg['map']}_{cfg['n_agents']}agents_rseed{cfg['rseed']}"
        out_path = f"{OUT_DIR}/{label}.json"

        if os.path.exists(out_path):
            print(f"Skipping {label} (already exists)")
            continue

        print(f"Running {label}...", end=" ")
        try:
            solved, elapsed, conflict_log = run_one(cfg["map"], cfg["n_agents"], cfg["rseed"])
        except Exception as e:
            print(f"ERROR: {e}")
            continue

        status = "solved" if solved else "TIMED OUT"
        print(f"{status} — {elapsed:.2f}s, {len(conflict_log)} conflicts")

        with open(out_path, "w") as f:
            json.dump(conflict_log, f, indent=2, default=str)

        summary.append({
            "label": label, "solved": solved,
            "runtime": round(elapsed, 2), "n_conflicts": len(conflict_log)
        })

    with open(f"{OUT_DIR}/_sweep_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nDone. {len(summary)} new instances run.")


if __name__ == "__main__":
    main()