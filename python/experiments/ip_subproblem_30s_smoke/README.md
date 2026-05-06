# regret_bidding+ip_subproblem 30s Benchmark

This run benchmarks `regret_bidding+ip_subproblem` on all selected input instances and
compares it against the cached Step 3 finalist results.

## Configuration

- Constructor: `regret_bidding`
- Improver: `ip_subproblem`
- Granular: `False`
- Tabu: `False`
- Time limit: `0.2` seconds per instance
- Seed: `0`

## Summary

| Mode | Valid | Avg Objective | Avg Improvement vs Baseline | Wins |
|---|---:|---:|---:|---:|
| `regret_bidding+destroy_repair` | 1 | 1945.90 | 19.62% | 1 |
| `regret_bidding+destroy_repair+granular+tabu` | 1 | 1949.23 | 19.48% | 0 |
| `regret_bidding+destroy_repair+granular` | 1 | 1972.61 | 18.51% | 0 |
| `regret_bidding+ip_subproblem` | 1 | 2729.06 | -12.74% | 0 |

## Head-to-Head

| Opponent | New Mode Wins | Ties | Opponent Wins |
|---|---:|---:|---:|
| `regret_bidding+destroy_repair` | 0 | 0 | 1 |
| `regret_bidding+destroy_repair+granular` | 0 | 0 | 1 |
| `regret_bidding+destroy_repair+granular+tabu` | 0 | 0 | 1 |

## Files

- `run_results.csv`: new run only.
- `comparison_vs_finalists.csv`: cached finalists plus the new run.

Valid rows for new mode: 1/1.
