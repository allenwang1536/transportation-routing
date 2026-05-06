# VRP Experiment Insights Log

This log captures the methodology and observations from building and benchmarking
the homemade VRP solver. It is intentionally written as a project storyline:
what we tried, what worked, what did not, and what changed as evidence came in.

## Starting Point

- The first homemade solver was a simple baseline:
  - build routes with farthest-first nearest-neighbor construction,
  - fall back to best-fit insertion if customers were stranded,
  - run 2-opt inside each vehicle route.
- This gave valid solutions on all provided input instances, which made it a
useful reference point for later experiments.
- The baseline was mostly a constructor, with only a small local-search piece:
2-opt changes customer order inside a route but does not move customers
between vehicles.

## External Benchmarking

- OR-Tools was added first as an independent validation/reference solver.
- OR-Tools confirmed the homemade solutions were feasible and gave a useful
comparison objective, but short OR-Tools runs were not always stronger than
the homemade baseline.
- This showed an important benchmark lesson: an external solver result under a
time limit is not necessarily optimal. It is just another time-limited
heuristic/reference.
- PyVRP was then chosen as the stronger final reference because it is more
specialized for VRP-style problems.

## Experiment Design

- We split the experiment into stages to avoid testing every possible
combination blindly.
- Step 1 isolates constructors:
  - `farthest_nearest`
  - `sweep`
  - `regret_bidding`
- Step 2 tests improvers with guidance layers on a hard subset:
  - `relocate_swap`
  - `destroy_repair`
  - `ejection_chains`
  - each with plain, granular, and granular+tabu variants.
- Step 3 benchmarks the top 3 modes on all 16 instances.
- Step 4 compares the final homemade winner against PyVRP.
- This staged design lets us answer:
  - which constructor gives the best launch point,
  - which improver family helps most,
  - whether granular filtering and tabu memory actually help,
  - whether the final homemade mode is close to a specialized solver.

## Constructor Insights

- `farthest_nearest` is fast and surprisingly strong on large geographically
structured instances.
- `sweep` is intuitive and visual, but it can be brittle: it does well on some
geometric instances and very poorly on others.
- `regret_bidding` is more expensive than the baseline constructor, but it often
creates better starting solutions on tight-capacity instances.
- We originally ranked constructors by raw average objective, but raw averages
are dominated by the largest instance. We switched to normalized improvement
over the baseline plus win count, which is fairer across mixed instance sizes.

## Improver Insights From Early Testing

- `relocate_swap` is a reliable improver:
  - it quickly fixes obvious bad assignments,
  - it often improves every hard screening instance,
  - but it can get stuck because it only makes small local moves.
- `destroy_repair` is more powerful on several tight/medium instances:
  - it can break bad route structures and rebuild them,
  - it finds improvements that simple relocate/swap may miss,
  - but it can be weaker on very large instances if it does not have enough time
  to repair meaningfully.
- `ejection_chains` are technically interesting but mixed:
  - plain ejection chains were often modest,
  - granular ejection chains were much better on the largest instance,
  - but ejection chains were weaker on several medium/tight cases.
- This suggests ejection chains may be a specialized large-instance tool rather
than a universal improver.

## Guidance-Layer Insights

- Granular neighborhoods are not automatically better.
- For relocate/swap, granular filtering sometimes hurt the largest instance by
excluding moves that plain relocate/swap could find.
- For destroy-repair, granular filtering often helped by focusing repair
insertions on geographically plausible routes.
- Tabu memory helped some tight instances, especially where destroy-repair could
otherwise recreate recently undone assignments.
- Tabu did not help everywhere. In some cases it slightly hurt because it blocked
a useful reversal or pushed the search into weaker repairs.
- Overall lesson: guidance layers should be treated as experimental controls,
not assumed upgrades.

## Timing And Methodology Correction

- During the first full benchmark attempt, we noticed a timing issue:
constructor time was not fully counted against the improver time limit.
- This mattered because `regret_bidding` construction was expensive on the
largest instance.
- We fixed the methodology by making the configured time limit include both
construction and improvement.
- We also optimized insertion-cost evaluation so regret/bidding could run inside
realistic benchmark budgets.
- This was an important experimental correction: fair solver comparisons need
the same total time budget, not just the same improvement-loop time.

## Corrected Benchmark Observations So Far

- After optimization, the corrected benchmark selected `regret_bidding` as the
constructor for Step 2.
- In the corrected 10-second hard-instance screening:
  - relocate/swap improved all hard instances,
  - granular relocate/swap still hurt the largest instance relative to plain
  relocate/swap,
  - destroy-repair was strong on tight medium instances,
  - granular destroy-repair was especially strong on `262_25_1.vrp`,
  - granular ejection chains were strongest on the largest `386_47_1.vrp`.
- The current evidence suggests:
  - destroy-repair is the best general improver family,
  - ejection chains may be useful later as a targeted add-on for very large
  instances,
  - granular guidance is most promising with destroy-repair, not relocate/swap.

## Current Full-Benchmark Status

- The corrected Step 3 finalist benchmark is currently running.
- The first finalist being benchmarked is `regret_bidding+destroy_repair`.
- Early full-benchmark results show this mode strongly improves several
medium-sized instances, including the 101-, 121-, 135-, and 151-customer cases.
- It did not improve `200_16_2.vrp` beyond the regret-constructor solution in
this corrected full run, which reinforces that destroy-repair is not uniformly
effective across every large/tight instance.
- `241_22_1.vrp` also showed little benefit from plain destroy-repair in this
pass. Some instances appear to need either a different improver or a more
targeted destroy strategy.
- Plain destroy-repair did improve `262_25_1.vrp`, but earlier screening showed
granular destroy-repair doing even better there. This makes `262_25_1.vrp` a
useful test case for whether granular repair guidance is actually adding value.
- Plain destroy-repair also improved `386_47_1.vrp` in the corrected full run,
but screening still showed granular ejection chains as unusually strong on
that largest instance. This supports a future hybrid idea: use destroy-repair
as the general engine, then selectively use ejection chains for very large
instances.
- On the smaller tail of the full benchmark, plain destroy-repair continues to
perform well. This makes it a strong candidate for the first-stage improver in
any later combination solver.
- The second finalist is `regret_bidding+destroy_repair+granular`. The key
question is whether granular filtering improves destroy-repair enough to make
it the default destroy-repair component in future combination tests.
- Early full results for granular destroy-repair are mixed relative to plain
destroy-repair: it improves some cases but not all. The combination phase
should therefore use the empirically best configuration, not automatically the
most complex one.
- Granular destroy-repair produced a strong corrected full-run result on
`200_16_2.vrp`, beating plain destroy-repair on an instance where plain
destroy-repair had previously stalled. This is evidence that granular repair
can sometimes make destroy-repair meaningfully more effective, not merely
faster.
- `241_22_1.vrp` also improved with granular destroy-repair. At this point,
the best destroy-repair configuration for the combination phase is likely to
include granular guidance unless later instances reverse the trend.
- `262_25_1.vrp` strongly confirms this pattern: granular destroy-repair is
substantially better than plain destroy-repair there. This points toward
granular destroy-repair as the strongest general-purpose improver component
so far.
- The largest instance, `386_47_1.vrp`, is the exception: granular
destroy-repair did not improve it in the corrected full run, while granular
ejection chains were strong on that same instance during screening. This is
useful evidence for future work, but the combination step is intentionally
deferred for now.
- The third finalist is `regret_bidding+destroy_repair+granular+tabu`. This
tests whether memory adds value on top of granular repair or whether the
simpler granular destroy-repair variant is enough.
- Tabu gives a small benefit on `121_7_1.vrp`, suggesting memory can help in
tight-capacity cases where destroy-repair might otherwise cycle through
similar assignments.
- On `200_16_2.vrp`, the tabu version improves over the constructor and plain
destroy-repair, but it does not beat the non-tabu granular variant from this
run. This again shows that tabu is situational rather than universally best.
- `262_25_1.vrp` shows a similar pattern: tabu+granular beats plain
destroy-repair, but non-tabu granular was better. The geography filter appears
to be the main source of improvement there; memory is secondary.
- The tabu+granular destroy-repair variant also does not improve
`386_47_1.vrp`, matching the non-tabu granular behavior. The largest instance
remains the clearest case where ejection-chain behavior may be worth revisiting
later.
- After the corrected Step 3 benchmark, the selected homemade winner is
`regret_bidding+destroy_repair+granular`. The tabu variant helped on some
instances, but not enough overall to beat the simpler granular destroy-repair
configuration.
- There is an important ranking nuance: `regret_bidding+destroy_repair` has the
lowest raw average objective and the most per-instance wins in Step 3, while
`regret_bidding+destroy_repair+granular` has the best average normalized
improvement over the original baseline. We selected the latter because
normalized improvement avoids letting the largest instances dominate the
benchmark summary, but both conclusions should be reported honestly.

## PyVRP Reference Insights

- PyVRP found valid solutions for all 16 instances in the final reference pass.
- The final homemade winner matches PyVRP on several smaller/tighter cases:
`16_5_1.vrp`, `21_4_1.vrp`, `30_4_1.vrp`, and `41_14_1.vrp`.
- The homemade winner is close to PyVRP on many medium cases, often within
roughly 0-6%.
- The biggest gap is `386_47_1.vrp`, where PyVRP is much stronger. This lines
up with earlier evidence that the largest instance needs a different large-
scale improvement mechanism, such as revisiting granular ejection chains or a
future combination solver.
- PyVRP emitted a penalty warning during the reference run, but every PyVRP row
still validated successfully in the final CSV.

## Open Questions For Later Analysis

- Should ejection chains be combined with destroy-repair only for the largest
instances?
- Should the final solver choose different improvers based on instance size or
capacity tightness?
- Should regret/bidding be used only for tight instances and farthest-nearest for
very large geographically structured instances?
- Should future benchmarks report both normalized improvement and per-instance
wins, since these sometimes tell different stories?
- The top-combination benchmark was discussed but intentionally paused. The
current run should stop after Step 3 finalists and Step 4 PyVRP reference.

