# ERPNext Data Archiver — Operator Manual

**App version:** 1.1.0  
**Date:** 2026-08-16  
**Platform:** ERPNext v14–v16 (MariaDB)

---

## Quick start

1. Install app → `bench migrate` → `bench build --app erpnext_data_archiver`
2. Open **Archive Settings** → Enable → set Backup ID + Checksum
3. Set **Archive Through Fiscal Year** (e.g. last closed year)
4. **Preview Archive** → must be OK
5. **Run Archive Now** → type `ARCHIVE`
6. Confirm **Archive Run** = Completed
7. Use **Retrieve Archived Data** only to *read* archived years in this session

---

## Archive vs Retrieve (do not confuse)

| Action | Where | What it does |
|--------|-------|----------------|
| Archive | Settings or Run archive dialog | Moves data out of live tables through a chosen year |
| Retrieve | Year checkboxes on Retrieve page | Session view only — does not move data |
| Restore | Restore a year | Copies one archived year back to live |

---

## Desk home

Open Desk after login. Search for Archive Settings, Archive Run, or Retrieve Archived Data.

![Desk home](images/01-desk-home.png)

---

## Settings fields

![Archive Settings](images/02-archive-settings.png)

| Field | Guidance |
|-------|----------|
| Enabled | Master switch |
| Require Backup Reference | Keep on in production |
| Last Backup ID / Checksum | Verified backup evidence |
| Confirmation Phrase | Default ARCHIVE |
| Archive Through Fiscal Year | Preferred way to choose what to archive |
| Archive Cutoff Date | Auto from year; advanced override |
| DocType Rules | Seeded defaults — review before first run |

---

## Preflight / Preview

Click **Preview Archive**. You should see Preflight OK and estimated row counts.

![Archive Preview](images/03-preview-archive.png)

If blocked: clear drafts (PRE-002), finish reposts (PRE-003), wait for a running job (PRE-004), or set backup fields (PRE-006). Then Preview again.

---

## After a successful run

![Completed Archive Run](images/04-archive-run-completed.png)

- Historical live rows before cutoff are gone (except retained open docs)
- Shadow tables hold archived rows tagged by fiscal year
- Opening entries keep current-year balances correct
- Spot-check Trial Balance / Balance Sheet for the current year

---

## Retrieve archived years (session)

![Retrieve Archived Data](images/05-retrieve-archived-data.png)

1. Tick fiscal year(s) already archived  
2. **Apply to this session**  

![Session archive mode](images/06-retrieve-year-2025-active.png)

3. **Use live data only** to return to the hot path  

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Stuck archive / PRE-004 | Mark the stuck Archive Run as Failed, then try again |
| No years on Retrieve page | Complete at least one successful archive first |
| Cannot uninstall the app | Restore or export archived years first |
