# Memory Destroy-Repair 30s Benchmark

This run benchmarks `regret_bidding+memory_destroy_repair+granular+tabu` on all input instances and compares it
against the cached Step 3 finalist results.

## Configuration

- Constructor: `regret_bidding`
- Improver: `memory_destroy_repair`
- Granular: `True`
- Tabu: `True`
- Time limit: `30.0` seconds per instance
- Seed: `0`

## Summary

| Mode | Valid | Avg Objective | Avg Improvement vs Baseline | Wins |
|---|---:|---:|---:|---:|
| `regret_bidding+destroy_repair+granular` | 16 | 3610.04 | 18.75% | 7 |
| `regret_bidding+memory_destroy_repair+granular+tabu` | 16 | 3500.79 | 18.70% | 0 |
| `regret_bidding+destroy_repair+granular+tabu` | 16 | 3633.84 | 18.36% | 0 |
| `regret_bidding+destroy_repair` | 16 | 3517.80 | 18.27% | 9 |

## Memory Head-to-Head

| Opponent | Memory Wins | Ties | Opponent Wins |
|---|---:|---:|---:|
| `regret_bidding+destroy_repair` | 5 | 5 | 6 |
| `regret_bidding+destroy_repair+granular` | 5 | 4 | 7 |
| `regret_bidding+destroy_repair+granular+tabu` | 7 | 4 | 5 |

## Files

- `memory_results.csv`: new memory run only.
- `comparison_vs_finalists.csv`: cached finalists plus the new memory run.

Memory valid rows: 16/16.
