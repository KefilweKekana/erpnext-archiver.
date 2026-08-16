# ERPNext Data Archiver — Product Documentation

**App:** erpnext_data_archiver  
**Version:** 1.1.0  
**Platform:** ERPNext v14–v16, MariaDB/MySQL  
**Date:** 2026-08-16  

---

## 1. Purpose

ERPNext Data Archiver moves completed fiscal-year transactional data out of live
tables into same-database shadow tables so the active site stays fast, while
preserving:

- Correct current-year balances (via opening-state / synthetic ledger rows)
- On-demand historical browsing (session retrieve)
- Controlled restore of a fiscal year
- Audit trail and fail-closed reconciliation

After archive, day-to-day work should behave like a site that started in the
**current fiscal year**. Historical ranges are served only when explicitly
requested (report date range or Retrieve page).

---

## 2. Architecture (summary)

| Layer | Behaviour |
|-------|-----------|
| Opening state | Before delete: snapshot GL, party, stock, FIFO queue; write synthetic live GL/SLE (`voucher_type = Archive Opening`) |
| Shadow tables | `tab{DocType} Archive` with `archived_on`, `archive_run`, `fiscal_year_archived` |
| Move | Copy → checksum verify → delete (journaled batches) |
| Routing | Active (no archive reads) / Archive / Combined / Session retrieve |
| Safety | Preflight, exclusive lock, backup reference, reconciliation before Completed |

Standard ERPNext Desk after login:

![Desk home](images/01-desk-home.png)

---

## 3. Installation

```bash
# From frappe-bench
bench get-app /path/to/erpnext_data_archiver
# or: copy app into apps/erpnext_data_archiver
bench --site your.site install-app erpnext_data_archiver
bench --site your.site migrate
bench build --app erpnext_data_archiver
bench --site your.site clear-cache
```

**Role created on install:** Archive Manager  

**Uninstall:** Blocked while Archived Fiscal Year rows or non-empty `* Archive`
shadow tables remain (unless `eda_force_uninstall` is set in site_config after
retention approval).

---

## 4. Roles and permissions

| Role | Can do |
|------|--------|
| System Manager | Full configure, archive, restore, uninstall policy |
| Archive Manager | Configure, preview, archive, restore, retrieve |
| Accounts Manager / Stock Manager | Browse retrieve / session years (no archive run) |

---

## 5. Configure Archive Settings

Open **Archive Settings** (Desk search).

![Archive Settings](images/02-archive-settings.png)

| Field | Required for production | Notes |
|-------|-------------------------|-------|
| Enabled | Yes | Master switch |
| Auto Archive Daily | Optional | Uses settings cutoff / current FY start |
| Require Backup Reference | Yes | Blocks run until backup ID + checksum set |
| Last Backup ID | Yes | Evidence of verified backup |
| Last Backup Checksum | Yes | Checksum or restore-test note |
| Confirmation Phrase | Yes | Default `ARCHIVE` |
| Archive Through Fiscal Year | Recommended | Sets cutoff to day after that year ends |
| Archive Cutoff Date | Auto if year set | Rows with date **before** this are eligible |
| Batch Size | Default 2000 | Lower on busy sites |
| DocType Rules | Seeded | GL, SLE, invoices, orders, stock docs, … |

**Important:** You archive **through a fiscal year** (or via cutoff date). You do
**not** pick years on the Retrieve page to archive — that list is for reading
already-archived years.

---

## 6. Run an archive

### From Archive Settings

1. Set backup ID + checksum  
2. Set **Archive Through Fiscal Year** (e.g. `2025`)  
3. **Preview Archive** — must show Preflight OK  

![Archive Preview](images/03-preview-archive.png)

4. **Run Archive Now** — type confirmation phrase  
5. Open **Archive Run** — wait until **Completed**

![Completed Archive Run](images/04-archive-run-completed.png)

### From Retrieve Archived Data (managers)

1. **Run archive**  
2. Select **Archive through fiscal year**  
3. Confirm phrase → queue  

### Preflight codes (common)

| Code | Meaning | Action |
|------|---------|--------|
| PRE-002 | Drafts before cutoff | Clear or submit drafts |
| PRE-003 | Pending reposts | Finish/cancel Repost Item Valuation etc. |
| PRE-004 | Conflicting run / lock | Mark stuck run Failed; clear Redis lock if needed |
| PRE-006 | Backup missing | Set Last Backup ID + Checksum |

### Success criteria

- Archive Run status = **Completed**  
- Reconciliation report OK  
- Historical live rows before cutoff removed (non-opening)  
- Synthetic openings present (`voucher_type = Archive Opening` on GL and/or SLE)  
- Spot-check Trial Balance / Balance Sheet for **current** FY  

---

## 7. Retrieve archived data (session)

Path: **Retrieve Archived Data**

![Retrieve Archived Data](images/05-retrieve-archived-data.png)

1. Tick one or more **already archived** years  
2. **Apply to this session** — reports/lists for this user include those years  

![Session archive mode for 2025](images/06-retrieve-year-2025-active.png)

3. **Use live data only** — return to hot path (no archive UNION)

Retrieval does **not** move data. It only changes what this session can see.

---

## 8. Restore a fiscal year

Managers only.

1. **Restore a year** on Retrieve page (or API `preview_restore` / `restore_year`)  
2. Collision dry-run first  
3. If collisions: resolve in live data, or force only after review  
   (force keeps colliding archive rows that did not insert)  
4. After success: openings rebuilt for the live cutoff  

---

## 9. Day-to-day operations checklist

- [ ] Verified DB (+ files) backup; ID and checksum recorded in Archive Settings  
- [ ] Fiscal Year masters exist for years you will archive  
- [ ] Pending reposts / blocking drafts cleared  
- [ ] Preview = Preflight OK  
- [ ] Confirmation phrase entered  
- [ ] Archive Run = Completed (evidence JSON present)  
- [ ] Current FY reports look correct  
- [ ] Optional: retrieve one archived year, then return to live-only  

---

## 10. Troubleshooting

| Symptom | Fix |
|---------|-----|
| Lock / PRE-004 | Mark stuck Archive Run Failed; delete Redis key `eda_archive_job_lock:<site>` |
| Archived years list empty | Archive must complete; FY tag needs Fiscal Year master or calendar fallback |
| Wrong year label (e.g. 2026 instead of 2025) | Fixed in 1.1.0 — re-archive or retag; ensure FY master exists |
| Restore dropdown empty | Need at least one archived year; hard-refresh Desk |
| Uninstall blocked | Restore/export archives first, or approved `eda_force_uninstall` |
| Mid-run Failed | Openings auto-rebuild on failure path; fix cause and re-run after review |

---

## 11. Multi-company behaviour

- Global safe cutoff = **latest** current FY start among companies  
- Tables with a `company` column also respect that company's own FY start  
- Never archives into any company's still-open fiscal year  

---

## 12. Support package

Delivered with this module:

1. App source: `erpnext_data_archiver`  
2. Product Documentation  
3. Testing Documentation  
4. Operator Manual  
