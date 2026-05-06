# regret_bidding+ip_subproblem 30s Benchmark

This run benchmarks `regret_bidding+ip_subproblem` on all selected input instances and
compares it against the cached Step 3 finalist results.

## Configuration

- Constructor: `regret_bidding`
- Improver: `ip_subproblem`
- Granular: `False`
- Tabu: `False`
- Time limit: `30.0` seconds per instance
- Seed: `0`

## Summary

| Mode | Valid | Avg Objective | Avg Improvement vs Baseline | Wins |
|---|---:|---:|---:|---:|
| `regret_bidding+destroy_repair+granular` | 16 | 3610.04 | 18.75% | 7 |
| `regret_bidding+destroy_repair+granular+tabu` | 16 | 3633.84 | 18.36% | 0 |
| `regret_bidding+destroy_repair` | 16 | 3517.80 | 18.27% | 9 |
| `regret_bidding+ip_subproblem` | 16 | 3758.09 | 8.23% | 0 |

## Head-to-Head

| Opponent | New Mode Wins | Ties | Opponent Wins |
|---|---:|---:|---:|
| `regret_bidding+destroy_repair` | 0 | 2 | 14 |
| `regret_bidding+destroy_repair+granular` | 1 | 1 | 14 |
| `regret_bidding+destroy_repair+granular+tabu` | 1 | 1 | 14 |

## Files

- `run_results.csv`: new run only.
- `comparison_vs_finalists.csv`: cached finalists plus the new run.

Valid rows for new mode: 16/16.
