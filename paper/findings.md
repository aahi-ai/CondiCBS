# Which search-node properties can language directives be grounded against?

Draft findings, CondiCBS. Every number is measured; producing scripts in §8.

---

## Thesis

Natural-language mission directives for multi-agent path finding must be
compiled into **predicates over search-node state**, not resolved into answers
before search begins — and only a subset of the quantities available in a node
can support that grounding at all.

Of four candidate quantities in a Conflict-Based Search node, one supports
branch-relative directives, one is 99.5% redundant with it, one is destroyed
by the search process itself, and one carries no branch dependence. This is
the paper's contribution: a measured characterisation of the grounding surface
that constraint-based solvers actually expose, plus the demonstration that a
single compilation call is sufficient to exploit it.

---

## 1. Setup

Instrumented CBS+PC (Makarenko implementation, vendored at
`external/cbs_icbs`) logs full branch state at every conflict discovery:
per-agent cost under the current branch, accumulated constraints,
alternative-route width at the conflict timestep, node depth, node entry index.

Maps: `room-32-32-4`, `maze-32-32-2`, `empty-32-32` (MovingAI). 8–30 agents.
Corpus: **104,335 two-agent conflicts**.

**Two logger versions.** An earlier logger recorded a missing width lookup as
`1` rather than as missing, conflating "no data" with "one route." All width
numbers come from a re-run with the corrected logger (12 instances, 7,865
valid observations). Cost-derived quantities — detour, route length,
constraint count — were unaffected and use the full corpus.

---

## 2. Accumulated detour is the branch-relative quantity

For agent *i* at a CBS node,

```
d_i = cost_i(branch) − cost_i(root)
```

the cost accumulated from constraints on the current branch.

**At the root, d_i = 0 for every agent, by construction.** A directive
referring to this quantity cannot be resolved before search: there is no
signal to resolve it against — not incorrect signal, none, on every conflict
rather than a selected subset.

| quantity | value |
|---|---|
| two-agent conflicts | 104,335 |
| unequal detour between the pair | 72,845 (**69.8%**) |
| of those, disagrees with shortest-optimal-route | 34,727 (**47.7%**) |
| median detour gap | 2 |
| branch depth at conflict (Q1/med/Q3) | 7 / 9 / 10 |

The asymmetry is the common case, not a mined subset. At ~48% agreement with
optimal route length, detour is close to statistically independent of it — not
a proxy for "who has further to go."

---

## 3. The grounding surface

Pairwise oracle agreement over 8,352 sampled node states:

| pair | agreement | n |
|---|---|---|
| detour vs longer-route | 48.6% | 4,647 |
| detour vs shorter-route | 51.4% | 4,647 |
| longer-route vs shorter-route | 0.0% | 8,156 |
| detour vs constraint-count | **99.5%** | 4,678 |

The 0.0% row is a wiring check: those directives are inverses by construction.

**Constraint count is redundant.** At 99.5% agreement it is detour in
different units — more constraints means more forced rerouting. It cannot
serve as an independent directive family.

**Width is degenerate under constraints.** Probing `AStar` unconstrained gives
per-timestep widths spread over 1–3 at 94–99% timestep coverage. Inside
search:

| | width 1 | width ≥2 |
|---|---|---|
| within-path observations (n=7,865) | **99.3%** | 0.7% |

A further 765 observations (~9%) had no width available, recorded as missing
rather than imputed.

Each constraint prunes optimal paths, so by median conflict depth (9) an
agent's optimal route is effectively unique. Directives referring to path
multiplicity — *"don't force the robot with fewer options into a detour"* —
have no variance left to ground against. This follows from constraint-based
search generally, not from this implementation, and it is the more surprising
of the two negative results: path multiplicity is a property that exists at
the root and is destroyed precisely by the process that creates the branch
state other directives depend on.

**Summary:**

| quantity | branch-dependent | usable | why |
|---|---|---|---|
| accumulated detour | yes | **yes** | 69.8% asymmetric, independent of route length |
| constraint count | yes | no | 99.5% redundant with detour |
| alternative-route width | yes | no | 99.3% degenerate under constraints |
| optimal route length | no | yes, but static | available at root, no branch dependence |

---

## 4. Deadline-based slack is an artifact of its constant

An earlier formulation defined `slack_i = f · cost_i(root) − cost_i(branch)`
with `f = 1.5`. Expanding gives `slack_i = (f−1)·root_i − d_i`. At the root
`d_i = 0`, so root ordering reduces to `argmin root_i` — independent of *f*,
and equivalent to "shorter optimal path wins." Branch ordering depends on how
`(f−1)·root_i` trades against `d_i`, so root/branch divergence is a direct
function of the constant:

| f | divergent (% of usable) |
|---|---|
| 1.1 | 21.4% |
| 1.25 | 9.8% |
| 1.5 | 4.5% |
| 2.0 | 0.9% |
| 3.0 | 0.2% |

Two orders of magnitude across plausible values. The detour quantity in §2 is
what remains once the constant is removed: all branch-relative content lives
in `d_i`, and the deadline construction only dilutes it with root cost. This
is reported because it is the natural first formulation of "urgency" and
because its failure mode — a free parameter silently determining the headline
result — is not visible from a single-value evaluation.

---

## 5. One compilation call is sufficient

A single call asks the model to compile a directive into a Python function
over node state. The solver evaluates that function at every conflict — no
further model calls. Temperature 0, evaluated over 104,384 node states.

| directive form | Sonnet 4.5 | Haiku 4.5 | scored n |
|---|---|---|---|
| SIMPLE — one field, one comparison | 100% | 100% | 72,894 |
| COMPOUND — conditional override (2× route length) | 100% | 100% | 72,894 |
| THRESHOLD — absolute cutoff plus fallback | 100% | 100% | 102,734 |

Zero runtime errors. The COMPOUND case is the informative one: no single field
exceeds 82.8% on that oracle, so the override must be scoped correctly to
score at all. Both models placed the 2× check before the detour comparison
rather than demoting it to a tie-break.

Both models also emitted deterministic tie-breaks the prompt did not request.
Ties in `detour_from_optimal` occur in 30% of conflicts, and an unspecified
tie-break makes CBS branching nondeterministic across runs — a correctness
issue neither the prompt nor the directive raised.

**Consequences.**

*Per-conflict querying is not justified.* It adds latency and nondeterminism
at every node and, in pruning form, costs CBS optimality and completeness —
for no accuracy gain over one upfront call on any groundable directive tested.

*Compilation target matters.* The detour predicate is correct only because it
is *evaluated* per node. Compiling the same directive to an answer at the root
yields nothing, since every d_i = 0 there. The distinction is not how often
the model runs, but whether its output is a value or a rule.

---

## 6. Discussion: directives outside the grounding surface

Directives referring to state the solver does not represent — payload weight,
battery, cargo fragility, delivery deadline, human escort — are compiled and
answered rather than declined. Across five such directives and two models,
none was refused under a prompt that did not offer refusal (0/10). Failure
took three forms: substitution of a plausible field (`optimal_route_cost` for
"heavier load"), invention of a multi-field cascade, and hallucination of a
non-existent key read via `.get()`, whose `None` return combined with the
model's own defensive check to produce a constant output on all 104,384
conflicts with zero runtime errors.

Adding an explicit refusal option to the prompt fixed this completely: 10/10
detection across both models, 0/10 false refusals on groundable directives,
with refusals naming the specific missing information.

This replicates known results in a solver-in-the-loop setting rather than
establishing new ones. Over-answering of unanswerable and underspecified
queries is documented by AbstentionBench (Kirichenko et al., 2025) and
Hallucination Tax (Song et al., 2025); refusal with clarification identifying
the missing information is the subject of Abstain-R1. API hallucination in
generated code is separately well studied (De-Hallucinator, Eghbali & Pradel
2024; MARIN 2025). The distinction worth noting is that those mitigations are
retrieval-based — the API exists and must be surfaced — whereas here there is
nothing to retrieve, and refusal is the only correct output.

---

## 7. Limitations

- One solver (CBS+PC), one implementation. Whether the width-degeneracy result
  holds for PBS, ECBS, or LNS-based solvers is untested.
- Grid MAPF only. Continuous or kinodynamic settings may expose different
  node quantities.
- Directive set is authored, not elicited from operators. Whether real
  instructions concentrate on the groundable quantity is unknown.
- Predicate compilation tested on three directive forms; nested or
  multi-clause directives beyond a single override are untested.
- Two models, same family. Cross-lab replication outstanding.

---

## 8. Scripts

| result | script |
|---|---|
| §2 detour | `analysis/detour_oracle.py` |
| §3 agreement | `grounding/multi_directive_eval.py --dry-run` |
| §3 width (unconstrained) | `analysis/widths_probe.py` |
| §3 width (in search) | `analysis/widths_split_new.py` |
| §4 sensitivity | `analysis/divergence_rate.py` |
| §5 compilation | `baselines/predicate_stress.py` |
| §6 abstention | `baselines/groundedness_check.py` |
| benchmark construction | `directives/library.py` |