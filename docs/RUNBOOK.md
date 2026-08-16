# Archive operations runbook

## Before first archive

1. Take a full database (and files) backup; verify restore on a clone.
2. Open **Archive Settings**:
   - Enable archiving
   - Set **Last Backup ID** and **Last Backup Checksum**
   - Set **Archive Through Fiscal Year** (preferred) or Cutoff Date
   - Review DocType rules
3. Click **Preview Archive** — resolve any blocking preflight (drafts, repost, backup).
4. Type the confirmation phrase and queue the archive.

You can also start archive from **Retrieve Archived Data → Run archive** and pick
the fiscal year in the dialog.

## During a run

Monitor **Archive Run** status: Validating → Snapshotting → Moving → Reconciling → Completed.

- Batch journal rows show per-batch counts/checksums.
- On failure, status is **Failed** and live rows for the failed batch are not deleted
  (copy-verify-delete). Fix the cause and re-run after review.

## Failed reconciliation

1. Open the failed Archive Run → Reconciliation Report.
2. Or call `erpnext_data_archiver.api.get_reconciliation_evidence` with the run name.
3. Do **not** mark Completed manually. Restore from backup if integrity is unclear.

## Browse vs restore

| Goal | Action |
|------|--------|
| Temporary historical view | **Retrieve Archived Data** → select years (session only) |
| Permanent put-back | Restore fiscal year (manager) — dry-run collisions first |

## Restore

1. `preview_restore` / UI dry-run — resolve name collisions.
2. Queue restore; openings for that period are cleared after success.
3. Archive shadow rows for that FY are removed only after copy to live.

## Uninstall

Blocked while **Archived Fiscal Year** rows remain. Restore/export first, or set
`eda_force_uninstall` in `site_config.json` after retention approval.

## Site evidence still required

See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) for GATE 3/4/7 benchmarks and DR drills.
