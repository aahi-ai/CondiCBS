import sys, os, random
sys.path.insert(0, "external/cbs_icbs")

from map_handler import Map, read_map, read_tasks
from low_level_policy import AStar, manhattan_distance
from agent import Agent

for map_name in ["room-32-32-4", "maze-32-32-2"]:
    mapstr = read_map(f"external/cbs_icbs/demo/{map_name}.map")
    tasks = read_tasks(f"external/cbs_icbs/demo/{map_name}-random-1.scen")
    random.seed(0)
    picked = random.sample(tasks, 3)

    print(f"\n=== {map_name} ===")
    for t in picked:
        bucket, path, width, height, jS, iS, jG, iG, length = t
        Agent.id = 0
        a = Agent(iS, jS, iG, jG)
        m = Map()
        m.read_from_string(mapstr, width, height, diagonal_movements=False)
        res = AStar(m, a, use_pc=True, heuristic_function=manhattan_distance)
        if len(res) < 3 or res[2] is None:
            print("  no widths returned")
            continue
        p, cost, widths = res
        plen = len(p)
        keys = sorted(widths.keys())
        vals = [widths[k] for k in keys]
        print(f"  path len {plen}, cost {cost}")
        print(f"  widths: {len(keys)} timesteps covered, "
              f"range t={keys[0] if keys else '-'}..{keys[-1] if keys else '-'}")
        print(f"  values: {vals[:15]}{' ...' if len(vals) > 15 else ''}")
        print(f"  coverage: {100*len(keys)/max(plen,1):.0f}% of path timesteps")
