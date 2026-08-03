"""
Schema for CondiCBS directive scenarios.

A directive scenario pairs:
- a natural-language mission directive
- the map/agent instance it applies to
- an oracle-defined ground truth resolution (NOT subjective judgment —
  computed via full-information lookahead over the relevant branches)
- a class label: "A" (statically groundable) or "B" (branch-relative)

Class B directives are the actual research contribution. Class A directives
are controls, included to show the method doesn't regress where static
approaches already work (PBS, static compilers).
"""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class DirectiveScenario:
    id: str                          # e.g. "B01_less_slack"
    directive_class: Literal["A", "B"]
    directive_text: str              # the natural-language directive, verbatim
    map_name: str                    # e.g. "room-32-32-4"
    n_agents: int
    rseed: int

    # which conflict (by index into the conflict_log) this directive applies to.
    # None = applies to first conflict matching some condition (defined per-scenario).
    target_conflict_index: int | None = None

    # oracle ground truth: which agent should be given way / which resolution
    # is correct, expressed as agent_id or a short structured answer.
    # Computed by a full-information lookahead, not by us "just deciding."
    oracle_ground_truth: dict = field(default_factory=dict)

    # free-text note on HOW the oracle ground truth was computed —
    # required for every scenario, this is what makes ground truth defensible
    oracle_method: str = ""

    # sanity check note: why this ISN'T reducible to a plain cost comparison
    # (i.e., why PBS/static cost-branching alone wouldn't already solve it)
    not_cost_reducible_because: str = ""