# ADR-001: Storage Architecture and Hot-Path Isolation

**Status:** Accepted  
**Date:** 2026-08-15  
**Context:** Dagaar Technology Fiscal-Year Data Archive Requirements v1.0

## Decision

Use **same-MariaDB shadow tables** plus a compact **opening-state layer**.

Active (current-period) queries must read **only** live transactional tables and
opening-state snapshots. They must **never** scan archive transaction tables.
Archive tables are joined only for archive-only or cross-year date ranges, or
when a user explicitly retrieves archived years in their session.

## Options considered

| Option | Pros | Cons |
|--------|------|------|
| A. Same-DB shadow tables (`tabX Archive`) | Lowest ops cost; works with existing backups; fast to ship from current codebase | Archive tables share buffer pool / backup size with live DB |
| B. Native table partitioning by fiscal year | Partition pruning in EXPLAIN | ERPNext schema ownership risk; hard upgrades; limited MariaDB partition flexibility for DocType graphs |
| C. Separate archive database | Strong physical isolation; optional exclude from hot backups | Cross-DB joins, connection management, dual backup/DR complexity |

## Choice: Option A + opening-state

1. **Hot-path isolation** is enforced in the query-routing layer, not by physical
   DB separation: active-only mode never rewrites SQL to archive tables.
2. **Opening-state** (GL, party, stock, FIFO queue) carries continuity into the
   active period so Balance Sheet / Trial Balance / Stock Balance do not need
   to `UNION ALL` historical GL Entry / SLE rows for current-year work.
3. Same-DB keeps restore, schema sync (`CREATE TABLE LIKE`), and site backups
   operationally simple for multi-company ERPNext sites.

## Backup / DR impact

- Full site DB backups include archive shadow tables (history retained).
- Active operational size shrinks; backup wall-clock may still grow with archives.
- Optional future enhancement: dump archive tables to separate files / cold storage
  (out of scope for this ADR).
- Preflight requires a verified backup identifier before any live-row deletion.

## Consequences

- Report wrappers must be **date-range aware** (active / archive / combined).
- Always-`UNION ALL` for balance reports is forbidden (violates ARCH-001 / PERF-001).
- Production acceptance still requires SQL traces proving zero archive reads on
  the approved hot-path suite (GATE 3) on a live site clone.
