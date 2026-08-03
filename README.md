# CondiCBS

Which properties of a search node can natural-language directives be grounded
against — and does that grounding have to happen during search?

Multi-agent path finding solvers take formal constraints. People give
instructions like *"give way to whichever robot has already been pushed
furthest off its original route."* Existing work (CaStL, AutoTAMP, VernaCopter)
compiles such instructions into a formal representation **before** search
begins. This project asks what that misses: some directives refer to quantities
that do not exist at the root of the constraint tree and only come into being
as search proceeds.

CondiCBS instruments Conflict-Based Search to record full branch state at every
conflict, characterises which of those state quantities can actually support
language grounding, and evaluates whether a language model can identify the
right one from the directive alone.

## Status

Research code, in progress. Measured results are in
[`paper/findings.md`](paper/findings.md), with the script that produced each
number named alongside it.

Established so far:

- **Accumulated detour** (`d_i` = branch cost − root cost) is the one viable
  branch-relative quantity found. Unequal between the conflicting pair in
  69.8% of 104,335 logged conflicts; agrees with optimal route length only
  48.6% of the time, so it is not a proxy for path length; identically zero
  for every agent at the root, so root-time compilation has no signal at all.
- **Per-agent constraint count** is redundant — 99.5% agreement with detour.
- **Alternative-route width** is degenerate inside search: 99.3% of 7,865
  valid observations equal 1, against a 1–3 spread when probed unconstrained.
  Constraints prune optimal paths, so multiplicity-based directives have no
  variance left to ground against by the time conflicts occur.
- A **deadline-slack** formulation was withdrawn: its root/branch divergence
  rate ranges from 21.4% to 0.2% depending on an arbitrary constant.

Open: whether a directive compiled **once** into a predicate over node state
(evaluated per conflict by the solver) matches per-conflict model querying. If
it does, the contribution concerns *where* grounding is evaluated rather than
how often a model is called.

## Layout

```
src/condicbs/
  solver/         instrumented CBS — logs branch state at each conflict
  directives/     directive schema and the mined scenario benchmark
  grounding/      prompt construction, model client, evaluation harnesses
  baselines/      root-frozen and compiled-predicate baselines
  benchmark/      oracle ground truth, aggregation
external/cbs_icbs/   vendored CBS+PC solver (see Attribution)
results/logs/        per-instance conflict logs
results/tables/      evaluation outputs
paper/               findings draft
```

## Setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY="..."     # or OPENROUTER_API_KEY
```

## Running

```bash
# generate conflict logs
python3 src/condicbs/solver/batch_run.py

# build the scenario benchmark from those logs
python3 src/condicbs/directives/library.py

# benchmark controls — no API calls
python3 src/condicbs/grounding/multi_directive_eval.py --dry-run

# grounding evaluation
python3 src/condicbs/grounding/multi_directive_eval.py --n 30 --seed 0

# compiled-predicate baseline (one call per directive)
python3 src/condicbs/baselines/predicate_baseline.py
```

`--dry-run` reports what each fixed-field strategy scores on the benchmark.
All of them sit at chance by construction; any accuracy above that band
reflects the model working out which quantity the directive refers to.

## Benchmark design

Evaluating grounding requires that reading a single fixed field cannot
succeed. Several directives are therefore run against the same node state,
each referring to a different quantity, with scenarios sampled per directive,
balanced so each robot wins half the time, and presentation order randomised.

Control accuracies (n=30 per directive, three directives): 47.8% / 53.3% /
46.7% for the three fixed-field strategies, 50.0% for always picking the
first-listed robot.

## Attribution

`external/cbs_icbs/` vendors the CBS and CBS+PC implementation by
Stepan Makarenko et al.
([Multi-agent-pathfinding-CBS-ICBS](https://github.com/Stepan-Makarenko/Multi-agent-pathfinding-CBS-ICBS),
MIT). It is included rather than referenced as a submodule so the repository
runs from a clean clone. Instrumentation lives in `src/condicbs/solver/` and
does not modify the solver's search behaviour.

Benchmark maps and scenarios are from the
[MovingAI MAPF benchmark set](https://www.movingai.com/benchmarks/mapf.html).

## License

MIT.