# explore_test.py
# Converted from external/cbs_icbs/Explore.ipynb
# Changes made: dropped notebook-only imports/calls (IPython.display.HTML,
# tqdm.notebook), set draw_anim=False everywhere to run headless, and fixed
# the return-value unpacking — movingai_test only returns (solution, anim)
# when draw_anim=True; otherwise it returns solution alone.

from visualization import draw
from tqdm import tqdm  # was tqdm.notebook — notebook-only widget, swapped for plain tqdm

from agent import Agent
from high_level_policy import HCBS
from map_handler import Map, read_map, read_tasks
from node import GridNode
from low_level_policy import manhattan_distance
from tests import test, movingai_test

# --- Cell 3: toy map + agents ---
height = 15
width = 30
mapstr = '''
# . . # 
. . . .  
. . . . 
# . . # 
'''
agent1 = Agent(0, 1, 3, 2)
agent2 = Agent(1, 0, 2, 3)

# --- Sanity check of CBS (no priority conflicts) ---
print("=== CBS sanity check (use_pc=False) ===")
solution, anim = test(HCBS, 4, 4, mapstr, [agent1, agent2],
                       heuristic_function=manhattan_distance,
                       use_pc=False, draw_anim=False)

ctnodes, t = test(HCBS, 4, 4, mapstr, [agent1, agent2],
                   heuristic_function=manhattan_distance,
                   use_pc=False, experiment_mode=True)
print("ctnodes, time:", ctnodes, t)

# --- Sanity check of CBS + PC (priority conflicts) ---
print("=== CBS+PC sanity check (use_pc=True) ===")
solution, anim = test(HCBS, 4, 4, mapstr, [agent1, agent2],
                       heuristic_function=manhattan_distance,
                       use_pc=True, draw_anim=False)

ctnodes, t = test(HCBS, 4, 4, mapstr, [agent1, agent2],
                   heuristic_function=manhattan_distance,
                   use_pc=True, experiment_mode=True)
print("ctnodes, time:", ctnodes, t)

# --- MovingAI demonstration ---
print("=== MovingAI: empty-32-32, 21 agents ===")
ctnodes, t = movingai_test(map_file='demo/empty-32-32.map',
                            task_file='demo/empty-32-32-random-1.scen',
                            n_agents=21, rseed=42, SearchFunction=HCBS,
                            experiment_mode=True, draw_anim=False,
                            heuristic_function=manhattan_distance)
print("ctnodes, time:", ctnodes, t)

print("=== MovingAI: room-32-32-4, 8 agents ===")
solution = movingai_test(map_file='demo/room-32-32-4.map',
                          task_file='demo/room-32-32-4-random-1.scen',
                          n_agents=8, draw_anim=False, rseed=42,
                          use_pc=True, SearchFunction=HCBS,
                          heuristic_function=manhattan_distance)

print("=== MovingAI: room-32-32-4, 12 agents, start_task=2 ===")
solution = movingai_test(map_file='demo/room-32-32-4.map',
                          task_file='demo/room-32-32-4-random-1.scen',
                          n_agents=12, random_choice=False, start_task=2,
                          draw_anim=False, use_pc=True, SearchFunction=HCBS,
                          heuristic_function=manhattan_distance)
total_cost = sum([solution[k][1] for k in solution.keys()])
print("Total cost:", total_cost)

print("=== MovingAI: room-32-32-4, 12 agents, rseed=42 ===")
solution = movingai_test(map_file='demo/room-32-32-4.map',
                          task_file='demo/room-32-32-4-random-1.scen',
                          n_agents=12, draw_anim=False, rseed=42,
                          use_pc=True, SearchFunction=HCBS,
                          heuristic_function=manhattan_distance)

print("=== MovingAI: maze-32-32-2, 10 agents ===")
solution = movingai_test(map_file='demo/maze-32-32-2.map',
                          task_file='demo/maze-32-32-2-random-1.scen',
                          n_agents=10, random_choice=True, draw_anim=False,
                          rseed=239, use_pc=True, SearchFunction=HCBS,
                          heuristic_function=manhattan_distance)

print("Done — CBS solver ran successfully on all test cases.")