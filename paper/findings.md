# Grounding language directives against CBS search state

Draft findings. Every number is measured; the producing script is named in §7.

---

## Thesis

Natural-language mission directives for multi-agent path finding should be
compiled into **predicates over search-node state**, not resolved into answers
before search begins. Some directives refer to quantities that are identically
zero at the root of the constraint tree and only acquire value as search
proceeds — a compiler that emits an answer has nothing to work with, while one
that emits a rule resolves them perfectly.

Two contributions follow. First, a characterisation of which CBS node
quantities can support language grounding at all: of four candidates, one is
usable, one is redundant with it, and one is destroyed by the search itself.
Second, the demonstration that a single compilation call is sufficient — no
per-conflict model querying is required, and per-conflict querying should not
be presented as necessary.

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
numbers below come from a re-run with the corrected logger (12 instances,
7,865 valid observations). Cost-derived quantities — detour, route length,
constraint count — were never affected and use the full corpus.

---

## 2. The quantity that matters: accumulated detour

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

## 3. Which node quantities can directives ground against?

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
search generally, not from this implementation.

**Taxonomy:**

| quantity | branch-dependent | usable | why |
|---|---|---|---|
| accumulated detour | yes | **yes** | 69.8% asymmetric, independent of route length |
| constraint count | yes | no | 99.5% redundant with detour |
| alternative-route width | yes | no | 99.3% degenerate under constraints |
| optimal route length | no | yes, but static | available at root, no branch dependence |

---

## 4. Compilation to predicates resolves these directives completely

A single call asks the model to compile a directive into a Python function
over node state. The solver then evaluates that function at every conflict —
no further model calls.

Claude Sonnet 4.5, temperature 0, one call per directive:

| directive | referenced field | accuracy | n |
|---|---|---|---|
| *"…pushed furthest off its original route"* | `detour_from_optimal` | **100%** | 72,894 |
| *"…longer journey to make in the first place"* | `optimal_route_cost` | **100%** | 102,483 |
| *"…shorter journey, so it clears the area sooner"* | `optimal_route_cost` | **100%** | 102,483 |

278k evaluations, three API calls, zero runtime errors. Each compiled
predicate selected the correct field, handled the inverse pair correctly, and
included a deterministic tie-break the prompt did not request.

Two consequences.

**Per-conflict querying is unnecessary.** It adds latency and nondeterminism
at every node and, in pruning form, costs CBS its optimality and completeness
guarantees — for no accuracy gain over one upfront call. Systems proposing
per-conflict LLM invocation for directives of this kind should be measured
against this baseline.

**But compilation target matters.** The detour predicate is correct only
because it is *evaluated* per node. Compiling the same directive to an answer
at the root yields nothing, since every d_i = 0 there. The distinction is not
how often the model runs, but whether its output is a value or a rule.

---

## 5. Negative result: deadline-based slack is an artifact

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
in `d_i`, and the deadline construction only dilutes it with root cost.

---

## 6. Supporting: per-conflict querying under a grounding benchmark

Not load-bearing given §4, but it quantifies what per-conflict invocation
costs in reliability.

Evaluating grounding requires that reading a single fixed field cannot
succeed. Scenarios are sampled per directive, balanced so each robot wins half
the time, with presentation order randomised.

Controls (n=30 per directive, three directives):

| fixed strategy | accuracy |
|---|---|
| always read detour | 47.8% |
| always read longer-route | 53.3% |
| always read shorter-route | 46.7% |
| always pick first-listed robot | 50.0% |

No fixed field beats chance across the directive set; no positional bias.
Accuracy above this band reflects the model identifying which quantity the
directive refers to.

*(Replaces an earlier harness passing only the single pre-extracted field the
directive referred to; on that setup `min()` scores 100%.)*

**Open:** per-conflict accuracy on this benchmark, ≥2 models, ≥3 seeds,
stratified by detour gap (half of mined scenarios have gap 1).

---

## 7. Scripts

| result | script |
|---|---|
| §2 detour | `detour_oracle.py` |
| §3 agreement, §6 controls | `grounding/multi_directive_eval.py --dry-run` |
| §3 width (unconstrained) | `widths_probe.py` |
| §3 width (in search) | `widths_split_new.py` |
| §4 predicate compilation | `baselines/predicate_baseline.py` |
| §5 sensitivity | `divergence_rate.py` |
| benchmark construction | `directives/library.py` |