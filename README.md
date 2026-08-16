# ERPNext Data Archiver (Dagaar)

Fiscal-year data archiving for **ERPNext v14 – v16** (MariaDB/MySQL).

After completed fiscal years are archived, the active site must behave like a
site whose first operational transaction was entered in the **current fiscal
year**: normal current-period work reads **only** live tables plus compact
**opening-state** snapshots — never archived GL/SLE/invoice rows. Historical
and cross-year ranges are served by explicit date-range query routing (or
session retrieve). Balances and reports must remain mathematically identical
to an unarchived reference database.

See [docs/ADR-001-storage-and-hot-path.md](docs/ADR-001-storage-and-hot-path.md)
and [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md).

## How it works

### 1. Opening state (hot-path continuity)

Before rows are deleted from live tables, the engine writes opening-state
records (GL, party outstanding, stock qty/value, FIFO/MA queue). Current-year
lists, transactions and active-only reports use live data + these snapshots —
**zero archive-table reads** on the hot path.

### 2. Physical archive (shadow tables)

Eligible rows older than the cutoff (default: start of current FY) are copied
into `tab{DocType} Archive` tables with metadata (`archived_on`, `archive_run`,
`fiscal_year_archived`), verified (count + checksum), then deleted from live —
in journaled batches. Open/unpaid documents stay live. Parent–child graphs move
together.

### 3. Query routing (active / archive / combined)

| Mode | When | Data sources |
|------|------|----------------|
| Active | Date range entirely on/after cutoff | Live + opening state (no archive UNION) |
| Archive | Date range entirely before cutoff | Matching archive partitions |
| Combined | Range spans cutoff | Live + scoped archive; openings not double-counted |
| Session retrieve | User opt-in on Desk | Selected archived years UNION into SELECTs |

### 4. Safety

Preflight (FY closed, drafts/repost, capacity, backup reference, exclusive lock)
must pass. Archive Run state machine: Validating → Snapshotting → Moving →
Reconciling → Completed (or Failed / Recovering). Reconciliation must pass
before Completed. Restore supports dry-run collision checks (no silent overwrite).

## Installation

```bash
bench get-app /path/to/erpnext_data_archiver
bench --site your.site install-app erpnext_data_archiver
bench --site your.site migrate
```

Configure **Archive Settings** (enable, backup reference, DocType rules), run
**Preview**, then confirm archive. Prefer a verified DB backup first.

## Usage

| Task | Where |
|------|--------|
| Configure / backup ref / rules | **Archive Settings** |
| Preview / run archive | Archive Settings or API (`preview_archive` / `confirm_archive`) |
| Browse archived years (session) | **Retrieve Archived Data** |
| Restore a fiscal year | Retrieval page / `restore_year` (managers) |
| Audit trail | **Archive Audit Log** |
| Run journal / reconciliation | **Archive Run** |

Role **Archive Manager** is created on install.

## Documentation (customer deliverables)

| Document | Path |
|----------|------|
| Product Documentation | [docs/manual/PRODUCT_DOCUMENTATION.md](docs/manual/PRODUCT_DOCUMENTATION.md) (+ PDF) |
| Testing Documentation | [docs/manual/TESTING_DOCUMENTATION.md](docs/manual/TESTING_DOCUMENTATION.md) (+ PDF) |
| Operator quick guide | [docs/manual/OPERATOR_MANUAL.md](docs/manual/OPERATOR_MANUAL.md) |
| Runbook | [docs/RUNBOOK.md](docs/RUNBOOK.md) |
| Known limitations | [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) |

Build PDFs:

```bash
python scripts/build_docs_pdf.py
```

## Development

```bash
# unit tests (helpers)
python -m unittest erpnext_data_archiver.tests.test_routing_and_manifest -v

# site E2E (MariaDB site required)
bench --site your.site execute erpnext_data_archiver.tests.e2e_verify.run
```
