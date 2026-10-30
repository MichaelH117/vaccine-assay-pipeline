# Scale and cost

Owner: Principal Engineer seat, 2026-10-30. **Measured** numbers come from `tools/scale_probe.py` on the build laptop
(16 GB RAM, often under 2 GB free), clean synthetic builds (no planted problems, because the generator's planting
logic assumes the 1x plate layout), no pytest. Raw outputs: [evidence/scale_1x.json](evidence/scale_1x.json),
[evidence/scale_10x.json](evidence/scale_10x.json), [evidence/scale_100x.json](evidence/scale_100x.json) (run log: [evidence/scale_100x.log](evidence/scale_100x.log)).
**Everything marked "estimate" is an estimate**, not a measurement or a quote.

## What a "unit" of data is
1x is the demo: 2 groups x 60 subjects x 3 visits = 360 serum samples on 10 first-run plates (13 with the planted
repeats). 10x = 3,600 samples (a mid-size Phase 2 serology load). 100x = 36,000 samples (a large Phase 3
immunogenicity subset). Plate count grows with samples (37 samples per plate).

## Measured
| | 1x | 10x | 100x |
|---|---|---|---|
| Samples / plates | 360 / 10 | 3,600 / 98 | 36,000 / 973 |
| Well reads | 960 | 9,408 | 93,408 |
| Audit rows | 5,771 | 57,382 | 573,017 |
| DuckDB file | 16.0 MB | 32.0 MB | 131.9 MB |
| dbt build | 137 of 137 passed | 137 of 137 passed | 137 of 137 passed |
| **Total build time** | **14.9 s** | **50.9 s** | **528.2 s (8 min 48 s)** |

Step times (seconds), 1x -> 10x -> 100x: generate 0.5 -> 6.5 -> 111.8; load LIMS (audited) 0.3 -> 4.2 -> 35.2;
ingest plates 0.2 -> 5.2 -> 42.3; 4PL fits 0.2 -> 3.4 -> 32.9; QC 0.1 -> 0.2 -> 1.4;
**reportable selection 0.4 -> 9.7 -> 221.1**; integrity checks 0.4 -> 7.6 -> 65.6; dbt build + tests 12.8 -> 14.1 -> 17.9.
(A first 100x attempt had stdout buffered and was stopped at 560 s; the second, unbuffered run finished in 528.2 s.
The log is kept as evidence.) Chart: [img/scale_profile.png](img/scale_profile.png).

**Reading it.** At 1x, dbt's fixed start-up cost is 85% of the run (12.8 of 14.9 s). At 10x the Python steps grew from 2.1 s to
36.8 s for 10x the data (about 17.5x), and to 510.3 s at 100x: they grow faster than linearly. dbt barely moved
(12.8 s -> 17.9 s across 100x). At 100x, reportable selection alone is 41% of the run (221.1 of 528.2 s).

## Where it breaks first
1. **Reportable selection** (`pipeline/reportable.py::choose`): 24x slower for 10x data, then another 22x for the
   next 10x (9.7 s -> 221.1 s). It filters the whole runs
   table once per sample (`runs[runs.sample_id == sid]`), so the work grows with samples x runs: quadratic. The write
   is already one batched audited insert. Fix: `groupby('sample_id')`, or one SQL window query
   (`row_number() over (partition by sample_id order by ...)`) with the same tie-break rules as ADR 006.
2. **Audited writes and integrity checks** (LIMS load 14x, integrity 19x). Every insert computes a SHA-256 over the
   previous row's hash, which is serial by design, and reconciliation re-serialises every live row to canonical JSON
   in Python. Fix: hash in batches inside one transaction; reconcile in SQL by comparing `to_json(row)` with the
   stored payload.
3. **The synthetic generator** (13x), which is test tooling, not product: per-plate list scans and per-well pandas
   `.loc` writes. Fix: vectorise, or generate once and cache.
4. **Not a bottleneck yet:** dbt (17.9 s at 100x), QC (1.4 s), 4PL fits (32.9 s for 973 plates, about 33 ms each, linear),
   DuckDB storage (131.9 MB at 100x).

**Verdict.** 100x builds on a laptop in under 9 minutes, so it does not break; it gets slow, and the slowness is in
two fixable Python steps, not in the data model or dbt. Fixing step 1 alone would remove about 220 s.

## Cloud cost if moved (all estimates)
The data is small: even 100x is tens of thousands of samples and about a thousand plate files of a few KB each.
Compute and storage cost are therefore negligible next to people and validation cost.

| Item | Shape | Monthly cost (estimate) |
|---|---|---|
| Batch compute for the daily run | one small general-purpose VM (2 vCPU, 8 GB) running about 1 hour per day | about $3-5 on-demand; $0 extra if it shares an existing lab server (estimate from typical public list prices, not checked today) |
| Database with real append-only controls | managed PostgreSQL, smallest production tier with backups | about $50-150 (estimate) |
| Object storage for raw plate files and anchors (WORM / object lock) | well under 10 GB per year | under $1 (estimate) |
| Logs, monitoring, CI minutes | | about $0-20 (estimate) |
| **Total infrastructure** | | **roughly $55-175 per month (estimate)** |

**The real costs** are the ones the demo does not carry: computer-system validation of each release, an identity
provider with e-signatures, audit-trail review time, and a LIMS integration. Those are people-weeks, not dollars of
compute, and they are why the roadmap puts PostgreSQL and signed anchors before any performance work.
