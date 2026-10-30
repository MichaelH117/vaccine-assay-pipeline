# Roadmap

Owner: Principal Engineer seat, 2026-10-30. Items link to the issue or risk they close. Synthetic data only.

## Now (finish v1, before demo sign-off)
| Item | Closes | Owner |
|---|---|---|
| Pinned requirements, GitHub Actions CI, `.gitignore`, README quickstart | BUG-009, R-09, KI-13 | devops-engineer |
| INJ-11 in the fast recall test and the hand-written answer key; required list read from config | BUG-010, KI-14 | analytics-engineer (LIA) |
| Exact header check on landing CSVs plus `not_null` tests on contract columns | BUG-011, R-05, KI-06 | data-engineer |
| `PLATE_REJECT_INGEST_ERROR` KPI row | BUG-012 | analytics-engineer (LIA) |
| Conclude the validation summary (GXP-07) with the final run's evidence | KI-15 | gxp-validation-engineer |
| Product-owner demo sign-off | | product-owner |

## Next (v1.1: make a run safe to repeat in a real lab)
- Build into a temp folder and swap it in on success; write results.json last (KI-02, R-04).
- Incremental, append-only loads keyed by file SHA-256, with no `_clean()` in production mode (KI-01, R-03).
- Lab times in UTC with the site's zone in the contract (KI-05).
- Single-well samples go on the re-assay list (KI-07, after the product call).
- Batch the audit hashing and move reportable selection into SQL (KI-12, R-12; SCALE_AND_COST.md).

## Later (v2: what a production lab system would need)
- PostgreSQL backend with triggers and `REVOKE UPDATE, DELETE`, keeping the same table contracts (ADR 001 option 2).
- Signed chain anchors sent to a separate system after each batch (R-02).
- Real identity and Part 11-style e-signature on plate release (KI-04, R-13).
- Second assay type (neutralization ID50 titers) behind the same plate contract (KI-09).
- A dashboard built from `docs/DASHBOARD_SPEC.md` on the exported marts.

## Won't do (explicit)
- Use or imitate real trial, patient, Pfizer or DOWC data.
- Claim GxP validation or Part 11 compliance.
- Add an LLM to the QC path. If an assistant is ever added, it runs on a local model and only explains flags; it
  never decides plate release.
