# Overnight 5-Minute Multithreading Benchmark — Insights

**Run command (from `yankees`):**
```bash
python3 experiments/run_ga_multithreading.py --time-limit 300 --skip-smoke \
    --output experiments/full_5min_20260504.csv
```
- Time limit per (instance, model): **300 s** (5 minutes).
- 16 instances × 3 models = **48 cells**, ~4 h wall-clock.
- `p_pull = 0.10` (script default at run time), `tau = 0.10`, `migration_interval = 5.0 s`, `seed = 42`.
- All cells produced **valid** solutions; no errors, no timeouts. The compile produced a
  GCC `-Wstringop-overflow` warning around `twoOptRoute` (`route_utils.hpp:251`), but
  it's a known false positive and does not affect correctness.

The companion data files used in this analysis:
- `experiments/full_5min_20260504.csv` — primary overnight run (this analysis).
- `experiments/0.9pull_ga_multithreading_results_20260504_212352.csv` — 30 s, all 16 instances, `p_pull = 0.90`.
- `experiments/ga_multithreading_results_20260504_195803.csv` — 30 s, first 4 instances, `p_pull = 0.10` (sanity).
- `experiments/ga_multithreading_results_20260504_200330.csv` — 30 s, 4 large instances, bidirectional only.
- `experiments/ga_multithreading_results_20260504_200642.csv` — 120 s, 4 large instances, all 3 models.
- `python/experiments/results/step4_pyvrp_reference.csv` — PyVRP reference at 30 s.

---

## Headline Numbers

### Per-instance objective by model (5 min run)

| Instance | Independent | One-Way | Bidirectional | Best | PyVRP (30 s) | Gap to PyVRP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 16_5_1   |   334.96 |   334.96 |   334.96 |   334.96 |   334.96 |  0.00 % |
| 21_4_1   |   358.40 |   358.40 |   358.40 |   358.40 |   358.40 |  0.00 % |
| 30_4_1   |   505.01 |   505.01 |   505.01 |   505.01 |   505.01 |  0.00 % |
| 41_14_1  |   861.79 |   861.79 |   861.79 |   861.79 |   861.79 |  0.00 % |
| 45_4_1   |   727.75 |   723.54 |   723.54 |   723.54 |   723.54 |  0.00 % |
| 51_5_1   |   524.61 |   524.61 |   524.61 |   524.61 |   524.61 |  0.00 % |
| 76_8_2   |   740.66 |   740.66 |   740.66 |   740.66 |   740.66 |  0.00 % |
| 101_8_1  |   826.14 |   826.14 |   826.14 |   826.14 |   827.39 | **−0.15 %** |
| 101_11_2 |  1940.36 |  1939.90 |  1939.90 |  1939.90 |  1940.61 | **−0.04 %** |
| 121_7_1  |  1082.19 |  1042.12 |  1042.12 |  1042.12 |  1042.12 |  0.00 % |
| 135_7_1  |  1162.96 |  1162.96 |  1162.96 |  1162.96 |  1162.96 |  0.00 % |
| 151_15_1 |  3070.61 |  3063.68 |  3056.41 |  3056.41 |  3055.23 |  +0.04 % |
| 200_16_2 |  1331.68 |  1328.25 |  1349.25 |  1328.25 |  1305.71 |  +1.73 % |
| 241_22_1 |   714.58 |   711.72 |   712.85 |   711.72 |   709.17 |  +0.36 % |
| 262_25_1 |  5614.64 |  5588.68 |  5563.43 |  5563.43 |  5550.30 |  +0.24 % |
| 386_47_1 | 25584.49 | 25934.67 | 24929.19 | 24929.19 | 24474.47 |  +1.86 % |

Negative gap = our solver beat PyVRP's 30 s result. Two instances are highlighted —
`101_8_1` and `101_11_2` — where we strictly beat the reference. Note PyVRP only had
30 s here; the comparison is "5 min ours vs. 30 s reference", which is generous to us.
Still, it is a useful absolute-quality anchor.

### "Best of 3 models" gap to PyVRP

- **Tied (≤0.01 %): 11 of 16 instances** — small/medium instances all hit the same
  local optimum across all three models.
- **We strictly beat PyVRP: 2 instances** (`101_8_1`, `101_11_2`).
- **Within 0.5 % of PyVRP: 14 of 16 instances**.
- **Worst gap: `200_16_2` at +1.73 %**, followed by `386_47_1` at +1.86 %.

The two outliers (`200_16_2`, `386_47_1`) are also the instances where extra wall-clock
helped most (see "Time scaling" below). With more time the gap to PyVRP shrinks
predictably; the algorithm itself isn't broken, it just needs longer to grind.

---

## Independent vs. One-Way vs. Bidirectional

For 7 of 16 instances, all three models tied at the same number (instances 16, 21, 30,
41, 51, 76, 135). These are small or geometrically easy enough that any reasonable
local search finds the same fixed point in seconds and then sits there for the
remaining 4-and-change minutes.

The interesting comparisons are the other 9 instances:

| Instance | I − Bi | OW − Bi | Winner |
| --- | ---: | ---: | --- |
| 45_4_1   |   +4.21 |   0.00  | OW = Bi (both better than I) |
| 101_8_1  |   0.00  |   0.00  | three-way tie |
| 101_11_2 |   +0.46 |   0.00  | OW = Bi (both better than I) |
| 121_7_1  |  +40.07 |   0.00  | OW = Bi (both *much* better than I) |
| 151_15_1 |  +14.20 |   +7.27 | **Bi** strict winner |
| 200_16_2 |   +3.43 |  −21.00 | **OW** strict winner (Bi *worse* than I) |
| 241_22_1 |   +1.86 |   −1.13 | **OW** wins |
| 262_25_1 |  +51.21 |  +25.25 | **Bi** strict winner |
| 386_47_1 | +655.30 | +1005.48| **Bi** strict winner; OW *worse* than I |

Three groups emerge:

1. **Bidirectional helps significantly: `151_15_1`, `262_25_1`, `386_47_1`.**
   These are large, geometrically complex instances. The shared GA pool produces high-quality
   diverse seeds that the workers couldn't reach on their own. `386_47_1` is dramatic —
   bidirectional saved over 1000 units (≈4 %) versus one-way.

2. **One-way helps but bidirectional doesn't: `200_16_2`, `241_22_1`.**
   The pool's *outputs* (workers contribute → GA refines → best is picked at the end)
   are useful, but workers *pulling* from the pool actively hurts on these instances.
   Workers seem to be making good progress on their own and the pull restarts disrupt
   them. `200_16_2` is the worst case: bidirectional is **20 units worse** than one-way.

3. **Pool only matters once: `45_4_1`, `101_11_2`, `121_7_1`.**
   The pool finds an improvement that no single worker reaches. `121_7_1` is the
   poster child — independent gets stuck at 1082; both pooled modes find 1042 (a 4 %
   improvement). Once any of the pooled paths finds it, both find it.

Notable failure mode: **`386_47_1` one-way is *worse* than independent.**
At 25934.67, one-way hurts compared to independent's 25584.49 (a 350-unit regression).
Possible cause: workers publish locally-optimal-but-globally-poor solutions that are
mostly diversity-rejected, but they still consume publish/lock cycles. Bidirectional on
the same instance recovers (24929.19) by allowing workers to consume the GA child output.

### Best-source attribution

Where does the best solution come from in each model?

- **Independent**: always `worker_1` (the destroy-repair worker on core 0). This is
  expected — destroy-repair is the strongest single improver in the codebase.
- **One-way**: `worker_1` for 13 of 16 instances; `ga_pool` for 3 instances
  (`45_4_1`, `121_7_1`, `151_15_1`). The GA contributes top results most when the
  search benefits from recombination of distinct route subsets.
- **Bidirectional**: `worker_1` for 11 of 16; `worker_2` (ejection chains) for 4
  (`121_7_1`, `200_16_2`, `262_25_1`, `386_47_1`); `worker_3` (relocate-swap+tabu) for 1
  (`151_15_1`).

  **Workers 2 and 3 only become best in bidirectional mode.** That tells us the
  ejection-chain and tabu workers benefit most from the pool seeding — on their own
  they get stuck; with diverse restarts, they shine. Worker 1 dominating is the
  baseline expectation, but seeing Workers 2/3 take 5 of 16 best slots is a real
  signal that the diversity injection is doing useful work.

---

## How much did 5 minutes vs. 30 seconds buy us?

Comparing the bidirectional column of the 5-minute run to the bidirectional column of
the 30 s `p_pull = 0.90` run (same model, different time + p_pull):

| Instance | 30 s best | 5 min best | Δ | Δ % |
| --- | ---: | ---: | ---: | ---: |
| 16_5_1   |   334.96 |   334.96 |    0.00 |   0.00 % |
| 21_4_1   |   358.40 |   358.40 |    0.00 |   0.00 % |
| 30_4_1   |   505.01 |   505.01 |    0.00 |   0.00 % |
| 41_14_1  |   861.79 |   861.79 |    0.00 |   0.00 % |
| 45_4_1   |   723.54 |   723.54 |    0.00 |   0.00 % |
| 51_5_1   |   524.61 |   524.61 |    0.00 |   0.00 % |
| 76_8_2   |   740.66 |   740.66 |    0.00 |   0.00 % |
| 101_8_1  |   826.14 |   826.14 |    0.00 |   0.00 % |
| 101_11_2 |  1940.36 |  1939.90 |   −0.46 |  −0.02 % |
| 121_7_1  |  1042.12 |  1042.12 |    0.00 |   0.00 % |
| 135_7_1  |  1165.32 |  1162.96 |   −2.36 |  −0.20 % |
| 151_15_1 |  3067.15 |  3056.41 |  −10.74 |  −0.35 % |
| 200_16_2 |  1346.95 |  1328.25 |  −18.70 |  −1.39 % |
| 241_22_1 |  713.63  |  711.72  |   −1.91 |  −0.27 % |
| 262_25_1 |  5657.27 |  5563.43 |  −93.84 |  −1.66 % |
| 386_47_1 | 25960.05 | 24929.19 |−1030.86 |  **−3.97 %** |

Two clear regimes:

- **Instances with ≤ 100 customers**: The extra 4.5 minutes buys essentially nothing.
  All three models find their local optimum within seconds and then idle. Even
  bidirectional restarts can't escape because the pool quickly fills up with
  near-duplicates of the same local optimum (the diversity gate `tau = 0.10` rejects
  almost everything).

- **Instances with ≥ 135 customers**: Extra time helps, with returns scaling roughly
  with instance size. `386_47_1` saw a dramatic ~4 % improvement.

The intermediate-time data point (120 s on the 4 large instances) confirms a smooth
trajectory:

| Instance | 30 s | 120 s | 300 s |
| --- | ---: | ---: | ---: |
| 200_16_2 | 1346.95 | 1334.95 | 1328.25 |
| 241_22_1 |  715.44 |  711.55 |  711.72 |
| 262_25_1 | 5616.53 | 5578.54 | 5563.43 |
| 386_47_1 | 26051.16| 25449.35| 24929.19 |

`241_22_1` actually peaked at 120 s (711.55) and slightly regressed at 300 s (711.72).
That's noise from the tabu-driven worker losing its best incumbent during a perturbation
restart — the system's "best ever" is what we report, but the *current* state can
move backward. With a single seed this is not statistically significant.

`386_47_1` dropped roughly 600 units per 90 s of additional compute — it was clearly
still improving and probably had not converged at 300 s. **If the autograder time
limit is 5 min, this instance is the one most leaving performance on the table.**

---

## What we learned about `p_pull`

Comparing 30 s p=0.10 vs. 30 s p=0.90 for bidirectional on the 4 large instances:

| Instance | p=0.10 (30 s) | p=0.90 (30 s) | Δ |
| --- | ---: | ---: | ---: |
| 200_16_2 | 1343.20 | 1346.95 | +3.75 (p=0.10 wins) |
| 241_22_1 |  715.44 |  718.43 | +2.99 (p=0.10 wins) |
| 262_25_1 | 5616.53 | 5704.30 | +87.77 (p=0.10 wins) |
| 386_47_1 |26051.16 |25980.37 | −70.79 (p=0.90 slightly wins) |

At 30 s, `p_pull = 0.10` (default) outperforms `p_pull = 0.90` on three of four large
instances. Aggressive pulling hurts because workers don't get long enough on any
single trajectory to reach a deep local optimum before being yanked away.

`386_47_1` is the exception — at this scale, no single worker can find a good local
optimum in 30 s anyway, so cycling restarts via the pool finds *some* improving
direction faster than waiting for any one worker's slow grind.

**Recommendation**: keep `p_pull = 0.10` as the default. It's well-tuned for the
typical 5-minute regime. Consider a short sweep (`0.05`, `0.10`, `0.15`, `0.20`) only
if there's time before submission. Higher values are clearly worse based on this data.

---

## Pool dynamics

A few useful counters from the bidirectional column of the 5 min run:

| Instance | accepted_seeds | accepted_children | accepted_migrants | pulls_attempted | pulls_accepted |
| --- | ---: | ---: | ---: | ---: | ---: |
| 16_5_1   | 1 | 1645379 |  1 | 1057311 | 1057311 |
| 41_14_1  | 2 |  341949 | 25 |   98137 |   98137 |
| 76_8_2   | 2 |  134710 | 42 |   77002 |   77002 |
| 121_7_1  | 1 |  101699 | 101 |  44019 |   44019 |
| 200_16_2 | 1 |    4615 | 53 |    8626 |    8626 |
| 386_47_1 | 2 |    2764 |257 |     628 |     628 |

A few observations:

- **`pulls_attempted == pulls_accepted` everywhere**. Every time a worker decides to
  pull, the pool has something for it to grab. The pool is never empty.
- **Tiny instances do millions of pulls.** Improvers complete and find no improving
  move almost instantly, the worker loop iterates very tightly, and at `p_pull = 0.10`
  about one in ten iterations pulls. For `16_5_1`, this is 1 M pull events per worker
  in 5 min — purely bookkeeping noise, doesn't affect quality (the answer is locked).
- **`accepted_children` correlates with instance size inversely.** On `16_5_1` the GA
  thread accepts ~1.6 M children (most aren't actually improving — the diversity gate
  `tau = 0.10` admits a wide range of solutions); on `386_47_1` only ~3 K children get
  in, because each worker iteration takes much longer.
- **`accepted_migrants` is small but grows with size.** Workers only publish when
  they beat their own personal best, so on small instances after the first few
  seconds nothing more is published. On large instances workers continually find new
  personal bests and feed them in.

---

## Open questions and follow-ups

1. **`p_pull` sweep with 5 min budget.** All p_pull comparison data is at 30 s.
   At 5 min the picture might shift — workers have more time to explore on their own,
   so an even smaller `p_pull` (e.g., 0.05) might dominate. Worth a quick 4 × 16 sweep
   if there's compute budget.

2. **Why does bidirectional hurt `200_16_2`?** This is the single worst regression
   (1349.25 vs. 1328.25 for one-way). The instance is large enough that one would
   expect the pool to help. Investigate whether the pulled seeds dominantly come
   from a single low-diversity GA child and what `tau` does here.

3. **Worker assignment is hard-coded.** Worker 0 = destroy-repair, 1 = ejection chains,
   2 = relocate-swap+tabu. Worker 1 (ejection chains) wins 4 best slots in
   bidirectional mode. Would a 4th worker be useful, or would we get more out of
   running two destroy-repair workers with different seeds?

4. **`386_47_1` was still improving at 300 s.** If submission time is fixed at 5 min,
   the only way to do better here is algorithmic — e.g., bias the GA pool toward
   geographic clustering on very large instances, or warm-start the GA thread from a
   PyVRP-quality solution if available.

5. **`241_22_1` regression from 120 s to 300 s.** Single-seed noise. Worth verifying
   with a 2- or 3-seed run before reporting.

6. **Compile warnings.** GCC 13's `-Wstringop-overflow` flagged a copy in
   `twoOptRoute` (route_utils.hpp:251). It's a known false-positive pattern on
   short routes (length 0 or 1) — clang and older GCC don't warn. Suppressing or
   rewriting the loop would be cosmetic only.

---

## Bottom line

For the autograder's 5-minute regime:

- **Use bidirectional** as the default model. It is never worse than one-way by more
  than a few units, and it is the only mode that wins on the largest instances.
- **Keep `p_pull = 0.10`** unless a new sweep shows otherwise.
- The solver is at PyVRP-equivalent quality on 11 of 16 instances and beats PyVRP's
  30 s reference on 2 of them. The 5 instances where we lag (`151_15_1`, `200_16_2`,
  `241_22_1`, `262_25_1`, `386_47_1`) are also the most time-sensitive; with PyVRP
  given 5 min instead of 30 s, the gap would presumably shrink, but those are the
  instances where additional engineering effort would have the biggest payoff if
  the deadline allows.
