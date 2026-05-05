# Memory Destroy-Repair 30s Benchmark

This run benchmarks `regret_bidding+memory_destroy_repair+granular+tabu` on all input instances and compares it
against the cached Step 3 finalist results.

## Configuration

- Constructor: `regret_bidding`
- Improver: `memory_destroy_repair`
- Granular: `True`
- Tabu: `True`
- Time limit: `0.2` seconds per instance
- Seed: `0`

## Summary

| Mode | Valid | Avg Objective | Avg Improvement vs Baseline | Wins |
|---|---:|---:|---:|---:|
| `regret_bidding+destroy_repair` | 1 | 1945.90 | 19.62% | 1 |
| `regret_bidding+destroy_repair+granular+tabu` | 1 | 1949.23 | 19.48% | 0 |
| `regret_bidding+destroy_repair+granular` | 1 | 1972.61 | 18.51% | 0 |
| `regret_bidding+memory_destroy_repair+granular+tabu` | 1 | 2212.84 | 8.59% | 0 |

## Memory Head-to-Head

| Opponent | Memory Wins | Ties | Opponent Wins |
|---|---:|---:|---:|
| `regret_bidding+destroy_repair` | 0 | 0 | 1 |
| `regret_bidding+destroy_repair+granular` | 0 | 0 | 1 |
| `regret_bidding+destroy_repair+granular+tabu` | 0 | 0 | 1 |

## Files

- `memory_results.csv`: new memory run only.
- `comparison_vs_finalists.csv`: cached finalists plus the new memory run.

Memory valid rows: 1/1.
