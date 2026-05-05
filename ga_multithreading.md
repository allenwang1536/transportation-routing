# GA Multithreaded Solver

## Architecture

The final design lives in the C++ solver path and builds a new executable:

```bash
bash cpp/compile.sh
```

The executable is `cpp/ga_multithreaded_solver`. It supports three models:

- `independent`: three worker threads only, no GA thread, no shared pool.
- `one_way`: three worker threads plus one GA thread; workers publish improved incumbents into the GA pool, but never pull from it.
- `bidirectional`: same as `one_way`, plus worker pull restarts from the GA pool with probability `p_pull`.

Thread roles are fixed:

| Core | Role | Configuration |
| --- | --- | --- |
| 0 | Worker 1 | `regret_bidding + destroy_repair + granular` |
| 1 | Worker 2 | `regret_bidding + ejection_chains + granular` |
| 2 | Worker 3 | `regret_bidding + relocate_swap + granular + tabu` |
| 3 | GA | HGS-style crossover, local search, and population maintenance |

Linux uses `pthread_setaffinity_np` for hard pinning. macOS uses Mach thread affinity tags, which are scheduler hints rather than hard binding.

## Diversity Rule

The GA pool uses the same insertion path for worker migrants, GA children, and GA seed individuals. A candidate is rejected when its nearest-neighbor normalized broken-pair distance to the current pool is below `tau`.

Default:

```text
tau = 0.10
```

The normalized broken-pair distance is the fraction of non-depot customers whose route successor differs between two solutions. Identical solutions have distance `0`; highly different solutions approach `1`.

This makes diversity relative to the current pool: a solution is accepted only if it is not too close to its nearest existing pool member.

## Worker and GA Flow

Workers maintain personal incumbents. When a worker finds a new personal best, it publishes that solution to the GA pool if it has improved since the worker's last push. The pool applies the diversity gate; workers do not directly read or adopt other workers' incumbents.

In `bidirectional` mode, workers check at migration/restart checkpoints. With probability `p_pull`, default `0.10`, a worker samples a solution from the GA pool using the population's quality-diversity biased fitness, then applies a small perturbation before resuming local improvement. This avoids always restarting from the single global best.

The GA thread continuously samples parents from the same pool, creates children with route-subset crossover, applies a short relocate/swap local search, and inserts children through the exact same diversity-gated pool method used by worker migrants.

## Benchmark Stages

The benchmark script is:

```bash
python3 experiments/run_ga_multithreading.py
```

Defaults:

- `--time-limit 120`
- `--seed 42`
- `--tau 0.10`
- `--p-pull 0.10`
- all `input/*.vrp` instances
- all models: `independent`, `one_way`, `bidirectional`

For the full default benchmark, expected runtime is roughly:

```text
16 instances x 3 models x 120 seconds = about 96 minutes
```

CSV results are written to:

```text
experiments/ga_multithreading_results_<timestamp>.csv
```

The CSV includes instance/model metadata, objective, validity, best source, pool size, accepted/rejected GA children, accepted/rejected worker migrants, pull attempts, accepted pulls, solution, and any error.

## Useful Commands

Smoke-test only, without launching the full benchmark:

```bash
python3 experiments/run_ga_multithreading.py --smoke-only
```

Run one instance for all models:

```bash
python3 experiments/run_ga_multithreading.py --instances 16_5_1.vrp
```

Run only the final bidirectional design:

```bash
python3 experiments/run_ga_multithreading.py --models bidirectional
```

Run a shorter development benchmark:

```bash
python3 experiments/run_ga_multithreading.py --time-limit 10 --instances 16_5_1.vrp 51_5_1.vrp
```

The existing `experiments/INSIGHTS.md` file is not modified by this benchmark.

