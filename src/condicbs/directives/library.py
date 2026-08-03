"""
The actual directive benchmark — hand-picked scenarios with real oracle
ground truth, pulled from logged CBS runs.

B01 (route-count/width-based directive) was tested and dropped: empirically,
grid-based MAPF instances show a structural tradeoff where high pair-
reconflict density (needed to observe branch drift at all) coincides with
near-universal width ties (which eliminate usable ground truth). Reported
as a negative result, not silently omitted.

B02 (schedule slack) is the primary Class B directive. Scenarios below are
drawn specifically from confirmed divergent cases mined by
benchmark/find_divergent_cases.py — instances where a static/root-only
compiler would get the WRONG answer, and only branch-aware grounding gets
it right. Tied cases are filtered out at the mining stage (no defensible
ground truth exists for a tie); this file applies a second safety-net
filter for the same reason.
"""

import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from src.condicbs.directives.schema import DirectiveScenario

SCENARIOS = []

# --- B02: schedule slack — scenarios drawn from CONFIRMED DIVERGENT cases ---
with open("results/logs/_divergent_b02.json") as f:
    divergent_b02 = json.load(f)

# safety-net filter: only entries with a real (non-None) answer count
divergent_b02 = [d for d in divergent_b02 if d.get("actual_correct_answer") is not None]

seen_pairs = set()
diverse_divergent = []
for d in divergent_b02:
    if "toy_conflict_log" in d["log_path"]:
        continue
    pair = tuple(sorted(str(a) for a in d["conflict_agents"]))
    if pair not in seen_pairs:
        seen_pairs.add(pair)
        diverse_divergent.append(d)

for i, d in enumerate(diverse_divergent[:150]):
    fname = os.path.basename(d["log_path"]).replace(".json", "")

    SCENARIOS.append(DirectiveScenario(
        id=f"B02_{i:02d}",
        directive_class="B",
        directive_text=(
            "When two robots would collide, give way to whichever robot "
            "has less remaining schedule slack."
        ),
        map_name=fname,
        n_agents=-1,
        rseed=-1,
        target_conflict_index=d["branch_node_entry"],
        oracle_ground_truth={
            "priority_agent": d["actual_correct_answer"],
            "give_way_agent": [a for a in d["conflict_agents"]
                                if str(a) != d["actual_correct_answer"]][0],
            "branch_slacks": d["branch_slacks"],
            "root_slacks": d["root_slacks"],
            "static_would_incorrectly_say": d["static_would_say"],
        },
        oracle_method=(
            "deadline = 1.5x root unconstrained cost; slack = deadline - "
            "cost_under_current_branch; lower slack = priority. This scenario "
            "was selected specifically because root_slacks and branch_slacks "
            "disagree on which agent has priority — a confirmed divergent "
            "case with no tie at either the root or the branch level."
        ),
        not_cost_reducible_because=(
            "Slack requires an externally-defined deadline (documented "
            "assumption: 1.5x unconstrained cost); this isn't part of vanilla "
            "MAPF's cost function. More importantly, THIS SPECIFIC scenario "
            "was selected because the correct answer depends on branch-"
            "accumulated constraints that don't exist at the root — a static "
            "compiler provably gets this one wrong (see "
            "static_would_incorrectly_say in ground truth)."
        ),
    ))

# --- A01: fixed priority (control — statically groundable, PBS/static compiler territory) ---
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
        "N/A — this is a Class A control, included specifically because it "
        "IS resolvable by a static rule (PBS or upfront compilation), to "
        "confirm CondiCBS doesn't regress or add unnecessary overhead here."
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
        "Fixed rule, no branch-state dependency — this is a literal "
        "vertex/time constraint that can be compiled directly into CBS's "
        "existing constraint format before search begins, exactly like "
        "CaStL-style upfront compilers already do."
    ),
    not_cost_reducible_because=(
        "N/A — Class A control, included to show CondiCBS handles the "
        "already-solved case correctly rather than only working on Class B cases."
    ),
))


if __name__ == "__main__":
    class_b = [s for s in SCENARIOS if s.directive_class == "B"]
    class_a = [s for s in SCENARIOS if s.directive_class == "A"]

    print(f"Total scenarios: {len(SCENARIOS)} ({len(class_b)} Class B, {len(class_a)} Class A)\n")

    print("--- Class B (branch-relative, CONFIRMED DIVERGENT, no ties) ---")
    for s in class_b:
        gt = s.oracle_ground_truth
        assert gt["priority_agent"] is not None, f"{s.id} has a None answer — filter failed!"
        print(f"  {s.id} [{s.map_name}]: correct={gt['priority_agent']}, "
              f"static wrongly says={gt['static_would_incorrectly_say']}")

    print("\n--- Class A (statically groundable, controls) ---")
    for s in class_a:
        print(f"  {s.id} [{s.map_name}]: {s.directive_text[:50]}...")
        print(f"    ground truth: {s.oracle_ground_truth}")