# Known Limitations

Aligned with Dagaar Requirements v1.0 §17.1 — gaps are explicit, not hidden.

## Supported platform

- **MariaDB / MySQL only.** Postgres raises `UnsupportedDatabase`.
- Target ERPNext lines: **v14, v15, v16** (defensive imports; check Archive Settings → Diagnostics).

## Architecture

- Archive storage is **same-database shadow tables**, not a separate archive DB
  and not native partitions (see [ADR-001](ADR-001-storage-and-hot-path.md)).
- Compression / encryption of separate archive storage: **not implemented**.
- Schema version is tracked per Archive Run (`schema_version`); per-partition
  cold-storage migration tools are not included.

## Modules and DocTypes

Default rules cover core accounting/stock/trading DocTypes. The following are
**not auto-enabled** until installed and configured in Archive Settings:

- Healthcare, Payroll, Manufacturing (beyond Stock Entry), Asset depreciation
  deep graphs, Loan Management, Subscription edge cases
- Custom DocTypes require validated rule entries (no raw SQL filters)

Serial No / Batch / Serial and Batch Bundle: archived when enabled via rules;
active serial/batch operational state relies on opening stock + retained open docs.

## Reports

Date-range routing covers the wrapped financial / AR-AP / stock balance suite.
**Not fully date-routed yet** (remain live-only unless session retrieve is on):

- Some analytics, custom Query/Script Reports, number cards, print formats
  discovered only on a customer site

List in Archive Settings → Diagnostics for wrap status.

## Evidence still required on a live site (GATE evidence)

This repository implements structural controls. The following acceptance evidence
must be produced on a production-scale ERPNext clone:

| Gate | Evidence |
|------|----------|
| GATE 3 | SQL trace: zero archive-table reads on active hot paths |
| GATE 4 | p50/p95/p99 before/after benchmarks |
| GATE 7 | Backup + full restore DR drill |
| Finance sign-off | Golden report parity package |

## Uninstall

Uninstall is blocked while `Archived Fiscal Year` rows exist, or while any
`* Archive` shadow table still has rows, unless an explicit force flag is used
after export/restore approval (see runbook).

## Multi-company and openings

- Global cutoff uses the **latest** company FY start; rows with a `company`
  column are further limited to that company's current FY start.
- Stock hot-path continuity uses synthetic `Stock Ledger Entry` rows
  (`voucher_type = Archive Opening`).
- FIFO queue openings are reconstructed from SLE as-of cutoff (with consumption),
  not from live Bin state.

## Tests

Unit tests cover routing, checksums, opening keys, and preflight helpers.
Full ERPNext integration / failure-injection against MariaDB requires `bench`
and a site fixture (see `docs/RUNBOOK.md`).
