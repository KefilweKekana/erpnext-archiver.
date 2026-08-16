def run():
	"""Clear stuck lock + smoke-test lock lifecycle and opening preserve."""
	import frappe
	from frappe.utils import getdate

	from erpnext_data_archiver.archiver import engine, opening_state, preflight

	key = preflight.LOCK_KEY + ":" + frappe.local.site
	frappe.cache().delete_value(key)

	owner = "test-lock-owner"
	assert preflight.acquire_job_lock(owner), "first acquire"
	assert not preflight.acquire_job_lock("other"), "second owner blocked"
	assert preflight.acquire_job_lock(owner), "same owner refresh"
	preflight.release_job_lock(owner)
	assert preflight.acquire_job_lock("other"), "after release"
	preflight.release_job_lock("other")

	settings = engine.get_settings()
	cutoff = getdate(settings.cutoff_date or engine.compute_cutoff_date(settings))
	before = frappe.db.count("Archive Opening GL", {"cutoff_date": cutoff})
	synth_before = frappe.db.sql(
		"SELECT COUNT(*) FROM `tabGL Entry` WHERE voucher_type='Archive Opening'"
	)[0][0]
	run_name = frappe.db.get_value("Archive Run", {"status": "Completed"}, "name") or None
	if before > 0 and run_name:
		got = opening_state._build_gl_openings(cutoff, run_name)
		after = frappe.db.count("Archive Opening GL", {"cutoff_date": cutoff})
		synth_after = frappe.db.sql(
			"SELECT COUNT(*) FROM `tabGL Entry` WHERE voucher_type='Archive Opening'"
		)[0][0]
		print("openings_preserved", before, after, synth_before, synth_after, "returned", got)
		if after == 0 or (synth_before > 0 and synth_after == 0):
			frappe.throw("Re-archive wiped openings/synthetics")
	else:
		print("skip_opening_preserve", "before", before, "run", run_name)

	print("lock_ok")
	return {"ok": True, "openings_before": before}
