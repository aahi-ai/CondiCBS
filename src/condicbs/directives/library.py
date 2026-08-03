"""
Directive scenarios for CondiCBS.

Scenarios are built from logged CBS conflicts, each pairing a natural-language
directive with the branch state it must be grounded against and an oracle
answer computed from that state.

Class A directives are statically groundable (fixed rules, no branch
dependence) and serve as controls. Class B directives are branch-relative —
their correct resolution depends on quantities that only exist once search is
underway.

Two earlier directive families were tested and are retained as negative
results:

B01 (alternative-route width). Ungroundable in a CBS tree. Unconstrained
A* shows per-timestep widths spread over 1-3, but within search, 99.3% of
7,865 valid observations are width 1 (median conflict depth: 9 constraints).
Each constraint prunes optimal paths, so by the time conflicts occur an
agent's optimal route is effectively unique and multiplicity-based language
has no variance to ground against. This follows from constraint-based search
generally, not from this implementation.

B02 (deadline slack). Withdrawn. Defined slack_i = f*root_i - branch_i with
f=1.5; expanding gives (f-1)*root_i - d_i, where d_i is accumulated detour.
Root-vs-branch divergence therefore varies from 21.4% (f=1.1) to 0.2%
(f=3.0) — the result was a function of an arbitrary constant. See
paper/findings.md section 4.

B03 (accumulated detour) is the surviving Class B family: d_i = branch cost
minus root cost, zero for all agents at the root by construction, unequal
between the conflicting pair in 69.8% of 104,335 conflicts, and in agreement
with optimal route length only 48.6% of the time.
"""

import sys, os, json, glob, random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from src.condicbs.directives.schema import DirectiveScenario

SCENARIOS = []

MAX_B03 = 150
PER_LOG_CAP = 20
MIN_DEPTH = 3          # shallow conflicts have 0-vs-1 detours: too thin to ground against
SAMPLE_SEED = 0

B03_TEXT = ("Give way to whichever robot has already been pushed furthest "
            "off its original route.")


def _mine_detour_scenarios():
    """
    Build Class B (detour) scenarios directly from logged conflicts.

    d_i = cost_i(branch) - cost_i(root). Priority goes to the agent with the
    LARGER detour — it has already absorbed more disruption, so the other
    robot yields.

    Ties are excluded: equal detour has no defensible ground truth. Conflicts
    shallower than MIN_DEPTH are excluded because their detour gaps are 0-vs-1,
    which is a thin margin. Sampling within each log is randomised, since logs
    are written in search order and taking a prefix biases toward the top of
    the constraint tree.
    """
    rng = random.Random(SAMPLE_SEED)
    out = []

    for path in sorted(glob.glob("results/logs/*.json")):
        if os.path.basename(path).startswith("_"):
            continue
        try:
            with open(path) as f:
                log = json.load(f)
        except Exception:
            continue
        if not isinstance(log, list) or not log:
            continue

        root = next((c for c in log if c["branch_num_constraints"] == 0), None)
        if root is None:
            continue
        root_costs = root["agent_costs_under_branch"]

        candidates = []
        for e in log:
            ag = e["conflicting_agents"]
            if len(ag) != 2:
                continue
            if e["branch_num_constraints"] < MIN_DEPTH:
                continue
            a0, a1 = str(ag[0]), str(ag[1])
            bc = e["agent_costs_under_branch"]
            if not all(a in root_costs and a in bc for a in (a0, a1)):
                continue

            d = {a: bc[a] - root_costs[a] for a in (a0, a1)}
            if d[a0] == d[a1]:
                continue

            priority = a0 if d[a0] > d[a1] else a1
            give_way = a1 if priority == a0 else a0

            candidates.append({
                "log_path": path,
                "map_name": os.path.basename(path).replace(".json", ""),
                "branch_node_entry": e["branch_node_entry"],
                "branch_depth": e["branch_num_constraints"],
                "agents": [a0, a1],
                "detours": d,
                "root_costs": {a: root_costs[a] for a in (a0, a1)},
                "branch_costs": {a: bc[a] for a in (a0, a1)},
                "priority_agent": priority,
                "give_way_agent": give_way,
            })

        rng.shuffle(candidates)
        out.extend(candidates[:PER_LOG_CAP])

    return out


_mined = _mine_detour_scenarios()

# one scenario per distinct (map, agent pair), for variety across the benchmark
_seen_pairs = set()
_diverse = []
for m in _mined:
    key = (m["map_name"], tuple(sorted(m["agents"])))
    if key in _seen_pairs:
        continue
    _seen_pairs.add(key)
    _diverse.append(m)

random.Random(SAMPLE_SEED).shuffle(_diverse)

for i, m in enumerate(_diverse[:MAX_B03]):
    SCENARIOS.append(DirectiveScenario(
        id=f"B03_{i:03d}",
        directive_class="B",
        directive_text=B03_TEXT,
        map_name=m["map_name"],
        n_agents=-1,
        rseed=-1,
        target_conflict_index=m["branch_node_entry"],
        oracle_ground_truth={
            "priority_agent": m["priority_agent"],
            "give_way_agent": m["give_way_agent"],
            "detours": m["detours"],
            "root_costs": m["root_costs"],
            "branch_costs": m["branch_costs"],
            "branch_depth": m["branch_depth"],
        },
        oracle_method=(
            "d_i = cost_i(branch) - cost_i(root); larger detour takes "
            "priority. No free parameters. Ties excluded (no defensible "
            "ground truth). Every d_i = 0 at the root, so a root-time "
            "compiler has no signal on any conflict in this family."
        ),
        not_cost_reducible_because=(
            "Detour is not a function of the MAPF cost objective: it measures "
            "displacement from an agent's own unconstrained optimum, which "
            "vanishes at the root. Across 104,335 conflicts it agrees with "
            "optimal route length only 48.6% of the time, so it is not a "
            "proxy for path length, and PBS-style static priority orderings "
            "cannot express it."
        ),
    ))


# --- A01: fixed priority (control — statically groundable) ---
SCENARIOS.append(DirectiveScenario(
    id="A01_00",
    directive_class="A",
    directive_text="The medical robot (agent 0) always has priority over all other robots.",
    map_name="room-32-32-4_8agents_rseed42",
    n_agents=8,
    rseed=42,
    target_conflict_index=None,
    oracle_ground_truth={
        "rule": "agent 0 always wins any conflict it's party to",
        "priority_agent": "0",
    },
    oracle_method=(
        "Fixed rule, no branch-state dependency — ground truth is the "
        "directive's literal rule, applicable identically to any conflict "
        "involving agent 0 regardless of which branch or timestep it occurs at."
    ),
    not_cost_reducible_because=(
        "N/A — Class A control, included specifically because it IS resolvable "
        "by a static rule (PBS or upfront compilation), to confirm CondiCBS "
        "doesn't regress or add unnecessary overhead here."
    ),
))

# --- A02: fixed time-window constraint (control — statically groundable) ---
SCENARIOS.append(DirectiveScenario(
    id="A02_00",
    directive_class="A",
    directive_text="All robots must avoid cell (16, 16) between timesteps 10 and 20.",
    map_name="room-32-32-4_8agents_rseed42",
    n_agents=8,
    rseed=42,
    target_conflict_index=None,
    oracle_ground_truth={
        "rule": "vertex constraint on (16, 16) for t in [10, 20], applies to all agents",
        "forbidden_cell": [16, 16],
        "time_window": [10, 20],
    },
    oracle_method=(
        "Fixed rule, no branch-state dependency — a literal vertex/time "
        "constraint compilable directly into CBS's constraint format before "
        "search begins, exactly like CaStL-style upfront compilers already do."
    ),
    not_cost_reducible_because=(
        "N/A — Class A control, included to show CondiCBS handles the "
        "already-solved case correctly rather than only working on Class B cases."
    ),
))


if __name__ == "__main__":
    class_b = [s for s in SCENARIOS if s.directive_class == "B"]
    class_a = [s for s in SCENARIOS if s.directive_class == "A"]

    print(f"Total: {len(SCENARIOS)} ({len(class_b)} Class B, {len(class_a)} Class A)")
    print(f"mined {len(_mined)} candidate conflicts, "
          f"{len(_diverse)} distinct (map, pair) combinations\n")

    print("--- Class B (B03: accumulated detour) ---")
    for s in class_b[:10]:
        gt = s.oracle_ground_truth
        assert gt["priority_agent"] is not None, f"{s.id}: None answer"
        print(f"  {s.id} [{s.map_name}] depth={gt['branch_depth']}: "
              f"detours={gt['detours']} -> priority={gt['priority_agent']}")

    depths = sorted(s.oracle_ground_truth["branch_depth"] for s in class_b)
    gaps = sorted(abs(list(s.oracle_ground_truth["detours"].values())[0]
                      - list(s.oracle_ground_truth["detours"].values())[1])
                  for s in class_b)
    if depths:
        print(f"  ... ({len(class_b)} total)")
        print(f"  branch depth  Q1/med/Q3: {depths[len(depths)//4]}/"
              f"{depths[len(depths)//2]}/{depths[3*len(depths)//4]}")
        print(f"  detour gap    Q1/med/Q3: {gaps[len(gaps)//4]}/"
              f"{gaps[len(gaps)//2]}/{gaps[3*len(gaps)//4]}")

    maps = {}
    for s in class_b:
        maps[s.map_name.split("_")[0]] = maps.get(s.map_name.split("_")[0], 0) + 1
    print(f"  by map: {maps}")

    print("\n--- Class A (controls) ---")
    for s in class_a:
        print(f"  {s.id}: {s.directive_text[:60]}...")