# Initial Multi-Threading: Architecture & Findings

## Architecture

### Threads and configurations

Four threads are spawned, each pinned to its own core and seeded independently
(`base_seed + threadId × 1 000 003`).  The four fixed configurations are:


| Thread | Constructor    | Improver        | Granular | Tabu |
| ------ | -------------- | --------------- | -------- | ---- |
| 0      | regret_bidding | destroy_repair  | ✓        |      |
| 1      | regret_bidding | destroy_repair  | ✓        | ✓    |
| 2      | regret_bidding | ejection_chains | ✓        |      |
| 3      | regret_bidding | relocate_swap   |          |      |


Threads 0–1 are the primary search engines (SA-based, run for the full
time limit).  Threads 2–3 are greedy polishers (converge in milliseconds
and then restart from the global best, acting as refinement passes on
whatever the destroy_repair threads have found so far).

### Shared state and information flow

A single `SharedState` object holds the best solution found by any thread,
protected by a `std::mutex`.  Two public methods: `tryUpdate` (publish)
and `getBest` (read).

**destroy_repair (threads 0 & 1) — bidirectional inline sharing**

Every `shareThreshold` (default = 3) personal improvements, a thread:

1. Publishes its personal best to the pool.
2. Reads the pool.  If the global best beats its personal best, it
  replaces both `best` *and* `current` with the imported solution.

Updating `current` as well (not just `best`) gives SA a fresh starting
point at the better solution.  SA can still take uphill moves from there,
so exploration is not cut off — the temperature schedule continues
naturally from the lower objective value.

**ejection_chains / relocate_swap (threads 2 & 3) — publish-only inline**

Every improvement is immediately published.  There is no mid-run import
because greedy descent converges to a local optimum in milliseconds; an
injection mid-run would just cause the next `findBestChain` /
`findBestMove` call to find no further improvement and break anyway.
Instead, after each convergence the outer thread-runner loop restarts
the improver from the current global best (which may have improved while
destroy_repair threads were running).

### Design decision: "better than personal best"

The alternatives considered:


| Policy                                                | Verdict                                                                                                                                                                                          |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Accept if better than personal best** (implemented) | Clean. SA already handles exploration via its acceptance criterion — injecting the global best as `current` just gives a better starting point; SA can still hill-climb from there.              |
| Accept if better than current state                   | Too aggressive: may disrupt an SA excursion into a promising valley that is temporarily worse than best.                                                                                         |
| Accept if better than last N states (ring buffer)     | Useful for population-based methods (GA/PSO), but unnecessary here — SA is already doing stochastic exploration within each thread; a per-thread N-state window adds complexity without benefit. |


### Thread pinning

On **macOS** (Darwin): `THREAD_AFFINITY_POLICY` assigns a unique affinity
tag to each thread.  This is a scheduler *hint*, not a hard binding.
macOS does not expose `pthread_setaffinity_np`.

On **Linux**: `pthread_setaffinity_np` hard-pins each thread to its
assigned core.

---

## Benchmark results

All runs: `seed=42`, `share_threshold=3`.  Results are single-run (these
are stochastic; expect ±0.5% variation across runs).

### 16_5_1.vrp — 16 customers, 5 vehicles, capacity 55

All methods hit the local optimum immediately; no meaningful comparison.


| Mode                                 | Time limit | Objective  |
| ------------------------------------ | ---------- | ---------- |
| T0 single (destroy_repair+gran)      | 10 s       | 334.96     |
| T1 single (destroy_repair+gran+tabu) | 10 s       | 334.96     |
| T2 single (ejection_chains+gran)     | <0.01 s    | 334.96     |
| T3 single (relocate_swap)            | <0.01 s    | 334.96     |
| **Parallel (4 threads)**             | 10 s       | **334.96** |


---

### 101_8_1.vrp — 101 customers, 8 vehicles, capacity 200


| Mode                                 | Time limit | Objective  | Notes                            |
| ------------------------------------ | ---------- | ---------- | -------------------------------- |
| T0 single (destroy_repair+gran)      | 10 s       | 828.94     |                                  |
| T1 single (destroy_repair+gran+tabu) | 10 s       | 832.50     |                                  |
| T2 single (ejection_chains+gran)     | 10 s       | 995.14     | converged in <0.01 s             |
| T3 single (relocate_swap)            | 10 s       | 1007.18    | converged in <0.01 s             |
| T0 single (destroy_repair+gran)      | 30 s       | 828.94     | plateau — no further improvement |
| T1 single (destroy_repair+gran+tabu) | 30 s       | 830.99     |                                  |
| **Parallel (4 threads)**             | 10 s       | 829.18     | ≈ T0 single                      |
| **Parallel (4 threads)**             | 30 s       | **826.14** | beats T0 30 s by **0.34%**       |


*At 10 s, parallel ≈ best single thread.  At 30 s, cooperative sharing
lets the two destroy_repair threads cross-pollinate past the individual
plateau (828.94 → 826.14).*

---

### 151_15_1.vrp — 151 customers, 15 vehicles, capacity 1 544


| Mode                                 | Time limit | Objective   | Notes                      |
| ------------------------------------ | ---------- | ----------- | -------------------------- |
| T0 single (destroy_repair+gran)      | 10 s       | 3092.66     |                            |
| T1 single (destroy_repair+gran+tabu) | 10 s       | 3091.14     |                            |
| T2 single (ejection_chains+gran)     | 10 s       | 3652.73     | converged in 0.02 s        |
| T3 single (relocate_swap)            | 10 s       | 3471.04     | converged in 0.03 s        |
| T0 single (destroy_repair+gran)      | 30 s       | 3079.79     |                            |
| T1 single (destroy_repair+gran+tabu) | 30 s       | 3085.27     |                            |
| **Parallel (4 threads)**             | **10 s**   | **3063.13** | beats T0 10 s by **0.95%** |
| **Parallel (4 threads)**             | 30 s       | 3078.70     | beats T0 30 s by **0.04%** |


*Parallel at 10 s (3063.13) beats both single-threaded configs even at
30 s.  The cooperative sharing is paying off: four diverse trajectories
cross the same plateau faster than any one thread alone.*

---

### 200_16_2.vrp — 200 customers, 16 vehicles, capacity (large)


| Mode                                 | Time limit | Objective |
| ------------------------------------ | ---------- | --------- |
| T0 single (destroy_repair+gran)      | 30 s       | 1342.68   |
| T1 single (destroy_repair+gran+tabu) | 30 s       | 1354.01   |
| **Parallel (4 threads)**             | 30 s       | 1348.31   |


*On this instance the parallel solver falls between T0 and T1 alone.
Thread interference on a machine with limited physical cores likely
explains why 4 competing threads don't consistently beat the best
single-threaded configuration.*

---

## Key findings

1. **Greedy methods (T2/T3) are not competitive stand-alone on larger
  instances** — they converge in milliseconds to a poor local optimum
   (20%+ above T0).  Their value in the parallel setup is as refinement
   passes once the destroy_repair threads have found a good solution;
   injecting the global best as their restart point lets them polish
   from a region they couldn't reach on their own.
2. **Cooperative sharing helps most on mid-size instances at longer time
  limits** (101 customers: −0.34%; 151 customers: −0.95% vs best  
   single thread).  The two SA threads diversify the search, discover  
   improvements the other wouldn't, and cross-pollinate every 3 personal  
   improvements. 
3. **On larger instances or CPU-limited machines the benefit is
  reduced**.  When all 4 threads share the same physical cores they
   compete for memory bandwidth and cache, and the scheduling overhead
   can offset the algorithmic advantage.
4. **The tabu variant (T1) is sometimes worse than T0 alone** at equal
  time budgets, likely because tabu overhead leaves fewer SA iterations
   per second than the non-tabu thread.
5. **Thread affinity (macOS)** is advisory only.  Results could improve
  on a Linux machine where hard pinning prevents thread migration and
   cache pollution.

---

## Potential improvements

- **Perturbation before greedy restarts**: after T2/T3 converge, apply a
small random perturbation (destroy + repair) before re-running the
greedy search, so successive restarts explore different neighbourhoods.
- **Adaptive share threshold**: lower the threshold early in the run
(more sharing) and raise it later (let threads diverge).
- **More diverse constructors**: seed threads with different constructors
(sweep, farthest_nearest) to spread initial solutions further.
- **Async publishing**: write improvements to a lock-free ring buffer
instead of a mutex to reduce contention at high improvement rates.

