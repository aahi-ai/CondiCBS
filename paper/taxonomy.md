# Taxonomy and Necessity Argument

## Definitions

**Definition 1 (Statically groundable directive).** A directive D is
statically groundable if its correct constraint resolution is a function
f(D, I) of the natural-language directive text and the static problem
instance I alone — the map, agent start/goal pairs, and any fixed
zones/time-windows named in D — evaluable before search begins, in time
independent of the search process.

**Definition 2 (Branch-relative directive).** A directive D is
branch-relative if its correct resolution is a function g(D, N) of
quantities whose values are functions of the accumulated search
constraints at a specific constraint-tree node N, and are therefore
undefined prior to N being reached during search.

## Proposition 1 (Information-dependence, revised)

There exist directives whose semantic interpretation depends on
search-state-dependent quantities that are undefined before search
begins.

**Proof (by construction).** Let D = "give way to whichever robot has
less remaining schedule slack," with slack(agent, N) = deadline(agent) -
cost(agent | N.constraints). The quantity cost(agent | N.constraints) is
defined only relative to a specific constraint-tree node N — it does not
exist as a well-defined value prior to N being reached during search.
Therefore, resolving D requires either (a) deferring grounding until N is
reached during search, or (b) computing, in advance, information
equivalent to what N would produce for every node the search might reach.
Neither option is "pre-search" in the sense of Definition 1 — the first
defers computation into the search itself; the second requires
constraint-dependent information that is exactly what a live,
search-coupled grounder like CondiCBS obtains at zero marginal cost as a
byproduct of normal execution. ∎

This is an information-availability claim, not a complexity-theoretic
impossibility claim — we do not claim no equivalent-cost precomputation
scheme could exist, only that resolving D requires access to
constraint-dependent quantities that a directive-compilation step
occurring strictly before search cannot possess.

## Scope: what this does NOT claim

**Not all directives referencing "priority" or "conflict" are
branch-relative.** Fixed rules — "the medical robot always has priority,"
"avoid this zone during this time window" — are Class A by Definition 1,
already handled by existing methods (Priority-Based Search branches
algorithmically on fixed orderings; static NL-to-PDDL/STL compilers such
as CaStL handle fixed zones/windows). These are included as controls
(A01, A02), not as motivating examples for CondiCBS.

**B01 (route-alternative-count directive) was tested and dropped.**
Empirically, on grid-based MAPF maps, high pair-reconflict density (needed
to observe branch drift at all) coincides with near-universal ties in
alternative-route counts (needed for a defensible ground truth) — e.g.
room-32-32-4 at 16 agents: 766 conflicts, 0.5% usable; at dense settings,
0.0% usable across multiple instances. Reported as a structural negative
result: route-count-based directives may require different map topologies
or a different formalization to demonstrate branch-relativity on standard
benchmarks.

## Empirical confirmation

We mined conflict logs across 46+ CBS runs on standard MovingAI benchmark
maps (primarily room-32-32-4, plus maze-32-32-2 and empty-32-32), varying
agent count (8–16) and random seed, and searched for cases where static
(root-only) resolution of D disagrees with the branch-correct resolution:

- **15 confirmed unique agent-pair divergences**, drawn from **595 total
  divergent conflict instances**, across 6+ distinct problem instances
  (see `results/logs/_divergent_b02.json`).
- Example: agents 4 and 8, room-32-32-4, 12 agents, seed 42 — root slack
  favors agent 4 (9.5 < 12.0), but by the time this pair actually
  conflicts (4 constraints deep into the branch), agent 8's slack has
  dropped to 9.0, flipping the correct priority to agent 8.
- Divergence is **real but rare relative to total conflicts mined** —
  most conflicts in a given instance do not exhibit root/branch
  disagreement. Stated plainly, not minimized.

  ## Frequency analysis (aggregate, across full dataset)

Across 262 CBS instances (varying map, agent count 8-20, and random seed):

- **131/262 instances (50.0%) contain at least one divergent conflict**
  — the phenomenon is not rare at the instance level.
- **6,099 of 104,335 total 2-agent conflicts (5.85%) were divergent**
  — a measurable, consistent minority of conflicts, not a hand-picked
  anomaly.
- **98 unique agent-pair divergences** were identified across the full
  dataset (up from 15 in an earlier, smaller pilot), confirming the
  phenomenon generalizes rather than being an artifact of a small
  number of instances.

## Comparison table (pilot, n=10)

On 10 confirmed divergent B02 scenarios, drawn diversely across the 15
unique agent pairs found:

| Approach | Correct | Notes |
|---|---|---|
| Static compiler (root-only) | 0/10 | Fails by construction — scenarios selected specifically because root and branch facts disagree |
| PBS-style (cost-based) | 0/10 (analytical) | PBS prefers lower cost (= higher slack under fixed deadline) — structurally opposite objective to the directive, which wants lower slack to win. Derived analytically from the fixed-deadline relationship, not from a live PBS implementation — validating against a real running PBS is left as a next step. |
| CondiCBS (LLM grounding) | 9/10 | See failure analysis below. |

## Failure analysis

Of 6 failures on the raw structured-output metric, 5 share an identical,
now well-confirmed signature across two evaluation rounds (n=10 and n=86):
the model's stated natural-language reasoning correctly names the agent
with lower slack, but the structured output field names the other agent
— contradicting its own reasoning. This is a reasoning-to-output binding
error, not a directive-comprehension failure.

The remaining 1 failure (B02_64) shows a genuine reasoning error: the
model's own stated logic is internally inconsistent, not merely
mis-transcribed into the output field.

**Reasoning-correct accuracy: 85/86 (98.8%).** **Raw structured-output
accuracy: 80/86 (93.0%).** The gap between these two numbers isolates a
specific, addressable output-formatting robustness issue, separate from
the core grounding capability being evaluated.

## Honest status (pilot, not final)

- n=10 is a meaningful improvement over the initial n=3 pilot but is
  still a pilot, not a full evaluation. More scenarios are needed before
  reporting a headline accuracy figure with confidence.
- PBS comparison is analytical, not from a live running implementation.
- Class A (statically groundable) directives have oracle ground truth
  defined but have not yet been run through the LLM grounding evaluation.

A closer look at the 9 "correct" cases reveals one (B02_05) involved a
genuine tie in slack values (11.0 vs 11.0) — the model's reasoning
invented an unstated tie-breaking rule (lower agent ID) rather than
applying the directive itself, and happened to match the oracle by
coincidence rather than by correctly grounding the directive. Treating
this as a non-genuine success, the corrected breakdown is: 8/10 solid,
1/10 reasoning-answer formatting failure, 1/10 lucky/non-applicable.

## Empirical confirmation

We mined conflict logs across 260+ CBS instances on standard MovingAI
benchmark maps (room-32-32-4, maze-32-32-2, empty-32-32), varying agent
count (8-20) and random seed. After filtering out tied cases (which have
no defensible ground truth) at both the branch level and the root level,
we identified 86 unique confirmed divergent agent-pair cases — instances
where static (root-only) resolution disagrees with the branch-correct
resolution.

## Frequency analysis (aggregate, across full dataset)

Across 262 CBS instances:
- 131/262 instances (50.0%) contain at least one divergent conflict.
- 6,099 of 104,335 total 2-agent conflicts (5.85%) were divergent before
  tie-filtering; 86 unique agent-pair cases survive as genuinely
  tie-free, confirmed divergent scenarios.

## Comparison table (n=86)

| Approach | Correct | Notes |
|---|---|---|
| Static compiler (root-only) | 0/86 | Fails by construction |
| CondiCBS (LLM grounding) | 80/86 (93.0%) | See failure analysis below |

## Failure analysis

Of 6 failures on the raw structured-output metric, 5 share an identical,
now well-confirmed signature across two evaluation rounds (n=10 and n=86):
the model's stated natural-language reasoning correctly names the agent
with lower slack, but the structured output field names the other agent
— contradicting its own reasoning. This is a reasoning-to-output binding

## Class A validation (control)

CondiCBS was also evaluated on the two Class A (statically groundable)
control directives, to confirm it does not regress on cases that don't
require branch-relative grounding:

- A01 (fixed priority): tested against 3 different conflict pairs — 3/3
  correct, confirming the LLM correctly applies a fixed rule regardless
  of which agents are involved.
- A02 (fixed zone/time-window): 1/1 correct constraint extraction,
  confirming accurate translation of a static directive into a formal
  constraint.

**Class A accuracy: 4/4 (100%).** CondiCBS handles the already-solved
case correctly; the reactive grounding mechanism does not add error on
directives that don't need it.