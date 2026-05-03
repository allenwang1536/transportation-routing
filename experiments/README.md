# VRP Experiment Results

Selection note: winners/finalists are ranked by average percent improvement over
the original `farthest_nearest` baseline, with raw average objective and wins
reported as supporting context. Raw averages are useful, but they are dominated
by the largest instances.

## Methods

- Constructors: `farthest_nearest`, `sweep`, `regret_bidding`.
- Improvers: `relocate_swap`, `destroy_repair`, `ejection_chains`.
- Guidance: `granular` nearest-neighbor filtering and `tabu` move memory.
- PyVRP is used only as an external reference for the final winner.

## Step 1: Constructor Selection

Best constructor selected: `regret_bidding`.

| Mode | Valid | Avg Objective | Avg Improvement vs Baseline | Wins |
|---|---:|---:|---:|---:|
| `regret_bidding` | 16 | 3946.14 | 2.74% | 6 |
| `farthest_nearest` | 16 | 3375.59 | 0.00% | 5 |
| `sweep` | 16 | 6109.90 | -27.37% | 5 |

## Step 2: Improver Screening

Screened 9 improver/guidance modes on the 5 hard instances for the configured
screening time.

Selected finalists: `regret_bidding+destroy_repair+granular`, `regret_bidding+destroy_repair+granular+tabu`, `regret_bidding+destroy_repair`.

| Mode | Valid | Avg Objective | Avg Improvement vs Baseline | Wins |
|---|---:|---:|---:|---:|
| `regret_bidding+destroy_repair+granular` | 5 | 9339.81 | 9.03% | 1 |
| `regret_bidding+destroy_repair+granular+tabu` | 5 | 9389.23 | 8.32% | 1 |
| `regret_bidding+destroy_repair` | 5 | 9441.97 | 6.75% | 1 |
| `regret_bidding+ejection_chains+granular` | 5 | 8713.13 | 4.91% | 1 |
| `regret_bidding+ejection_chains+granular+tabu` | 5 | 8794.20 | 4.66% | 0 |
| `regret_bidding+relocate_swap` | 5 | 9060.45 | 4.52% | 1 |
| `regret_bidding+ejection_chains` | 5 | 9259.52 | 3.83% | 0 |
| `regret_bidding+relocate_swap+granular` | 5 | 9298.85 | 3.64% | 0 |
| `regret_bidding+relocate_swap+granular+tabu` | 5 | 9310.07 | 3.48% | 0 |

## Step 3: Finalist Benchmark

Final winner: `regret_bidding+destroy_repair+granular`.

Note: `regret_bidding+destroy_repair` has the lowest raw average
objective and the most per-instance wins, while
`regret_bidding+destroy_repair+granular` has the best normalized improvement
over the baseline. The normalized metric was used for the final selection.

| Mode | Valid | Avg Objective | Avg Improvement vs Baseline | Wins |
|---|---:|---:|---:|---:|
| `regret_bidding+destroy_repair+granular` | 16 | 3610.04 | 18.75% | 7 |
| `regret_bidding+destroy_repair+granular+tabu` | 16 | 3633.84 | 18.36% | 0 |
| `regret_bidding+destroy_repair` | 16 | 3517.80 | 18.27% | 9 |

## Step 4: PyVRP Reference

See `step4_pyvrp_reference.csv` for objective gaps between PyVRP and the final
homemade winner on each input instance.
