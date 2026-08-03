# CondiCBS — measured findings

Draft. Every number here is measured; the script that produced each is named
so results can be regenerated. Nothing in this file depends on an LLM.

---

## 1. Setup

Instrumented CBS+PC (Makarenko implementation, vendored at `external/cbs_icbs`)
logs full branch state at every conflict discovery: per-agent cost under the
current branch, accumulated constraints, alternative-route width at the
conflict timestep, node depth, and node entry index.

Maps: `room-32-32-4`, `maze-32-32-2`, `empty-32-32` (MovingAI). 8–30 agents.
Corpus: **104,335 two-agent conflicts**.

**Note on two logger versions.** An earlier logger recorded a missing width
lookup as `1` rather than as missing, conflating "no data" with "one route."
All width numbers below come from a re-run with the corrected logger
(12 instances, 7,865 valid width observations). Cost-derived quantities
(detour, route length, constraint count) were never affected and use the
full 104,335-conflict corpus.

---

## 2. The quantity that matters: accumulated detour

For agent *i* at a CBS node, define

```
d_i = cost_i(branch) − cost_i(root)
```

the cost the agent has accumulated from constraints on the current branch.

**At the root, d_i = 0 for every agent, by construction.** A grounding
approach that compiles a directive to an answer before search begins has no
signal to compile against — not incorrect signal, *no* signal, on every
conflict rather than a selected subset.

Measured (`detour_oracle.py`):

| quantity | value |
|---|---|
| two-agent conflicts | 104,335 |
| conflicts with unequal detour between the pair | 72,845 (**69.8%**) |
| of those, detour disagrees with shortest-optimal-route | 34,727 (**47.7%**) |
| median detour gap | 2 |
| branch depth at conflict (Q1/median/Q3, constraints) | 7 / 9 / 10 |

Two things follow. The asymmetry is the common case, not a mined subset. And
at ~48% agreement, detour is close to statistically independent of optimal
route length — it is not a proxy for "who has further to go."

---

## 3. Which node quantities can directives ground against?

Pairwise oracle agreement over a sample of 8,352 node states
(`multi_directive_eval.py --dry-run`):

| pair | agreement | n |
|---|---|---|
| detour vs longer-route | 48.6% | 4,647 |
| detour vs shorter-route | 51.4% | 4,647 |
| longer-route vs shorter-route | 0.0% | 8,156 |
| detour vs constraint-count | **99.5%** | 4,678 |

The 0.0% row is a wiring check: those two directives are inverses by
construction and must never agree.

**Constraint count is redundant.** At 99.5% agreement it is the same quantity
as detour in different units — more constraints on an agent means more forced
rerouting. It cannot serve as an independent directive family.

**Width is degenerate under constraints.** Probing `AStar` on unconstrained
instances (`widths_probe.py`) gives per-timestep widths spread over 1–3, with
94–99% timestep coverage. Inside CBS search, the same quantity collapses:

| | width 1 | width ≥2 |
|---|---|---|
| within-path observations (n=7,865) | **99.3%** | 0.7% |

A further 765 observations (~9%) had no width available and are recorded as
missing rather than imputed.

The mechanism is straightforward: each constraint prunes optimal paths, so by
the time conflicts occur (median depth 9) an agent's optimal route is
essentially unique. Any directive referring to path multiplicity — "don't
force the robot with fewer options into a detour" — has nothing left to
ground against. This is a property of constraint-based search generally, not
of this implementation.

**Taxonomy of branch-relative quantities in a CBS node:**

| quantity | branch-dependent | usable | why |
|---|---|---|---|
| accumulated detour | yes | **yes** | 69.8% asymmetric, independent of route length |
| constraint count | yes | no | 99.5% redundant with detour |
| alternative-route width | yes | no | 99.3% degenerate (=1) under constraints |
| optimal route length | no | yes, but static | available at root, no branch dependence |

Of four candidate quantities, one supports branch-relative grounding.

---

## 4. Negative result: deadline-based slack is an artifact

An earlier formulation defined slack against a deadline,
`slack_i = f · cost_i(root) − cost_i(branch)`, with `f = 1.5`.

Expanding, `slack_i = (f−1)·root_i − d_i`. At the root, `d_i = 0`, so root
ordering reduces to `argmin root_i` — *independent of f entirely*, and
equivalent to "shorter optimal path wins." Branch ordering depends on how
`(f−1)·root_i` trades off against `d_i`, so the divergence rate between root
and branch is a direct function of the arbitrary constant:

| f | divergent (% of usable) |
|---|---|
| 1.1 | 21.4% |
| 1.25 | 9.8% |
| 1.5 | 4.5% |
| 2.0 | 0.9% |
| 3.0 | 0.2% |

Two orders of magnitude across plausible values. The formulation is reported
here because the detour quantity in §2 is what remains after removing the
constant: all branch-relative content lives in `d_i`, and the deadline
construction only dilutes it with root cost in an arbitrary ratio.

---

## 5. Benchmark design

Evaluating whether a model can *ground* a directive requires that reading a
single fixed field cannot succeed. Scenarios are therefore sampled per
directive, balanced so each robot wins half the time, with presentation order
randomised.

Control accuracies (`multi_directive_eval.py --dry-run`, n=30 per directive,
three directives):

| fixed strategy | accuracy |
|---|---|
| always read detour | 47.8% |
| always read longer-route | 53.3% |
| always read shorter-route | 46.7% |
| always pick first-listed robot | 50.0% |

No fixed field beats chance across the directive set, and there is no
positional bias. An accuracy figure above this band reflects the model
identifying which quantity a directive refers to.

*(This replaces an earlier harness that passed the model only the single
pre-extracted field the directive referred to; on that setup `min()` scores
100% and the measurement is uninformative.)*

---

## 6. Open

- Predicate baseline: one compilation call producing a function over node
  state, evaluated per conflict by the solver. If this matches per-conflict
  querying, the contribution is about *where* grounding is evaluated, not how
  often a model is called.
- LLM accuracy on the §5 benchmark, temperature 0, multiple seeds, ≥2 models.
- Live grounding inside the search loop; runtime overhead measured rather
  than estimated.

---

## Scripts

| result | script |
|---|---|
| §2 detour | `detour_oracle.py` |
| §3 agreement, §5 controls | `src/condicbs/grounding/multi_directive_eval.py --dry-run` |
| §3 width (unconstrained) | `widths_probe.py` |
| §3 width (in search) | `widths_split_new.py` |
| §4 sensitivity | `divergence_rate.py` |