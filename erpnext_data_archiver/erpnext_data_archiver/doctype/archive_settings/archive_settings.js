frappe.ui.form.on("Archive Settings", {
	refresh(frm) {
		if (!frappe.user.has_role(["System Manager", "Archive Manager"])) return;

		frm.add_custom_button(__("Preview Archive"), () => {
			frappe
				.call("erpnext_data_archiver.api.preview_archive", {
					fiscal_year:
						frm.doc.monthly_in_current_year && frm.doc.archive_through_month
							? null
							: frm.doc.archive_through_year,
					through_month: frm.doc.monthly_in_current_year
						? frm.doc.archive_through_month
						: null,
				})
				.then((r) => {
					const m = r.message || {};
					const prev = m.preview || {};
					let html =
						"<p><b>" +
						(m.ok ? __("Preflight OK") : __("Preflight blocked")) +
						"</b></p>";
					if (m.error) html += "<p>" + frappe.utils.escape_html(m.error) + "</p>";
					if (m.fiscal_year) {
						html +=
							"<p>" +
							__("Archive through") +
							": <b>" +
							frappe.utils.escape_html(m.fiscal_year) +
							"</b></p>";
					}
					if (m.through_month) {
						html +=
							"<p>" +
							__("Through month") +
							": <b>" +
							frappe.utils.escape_html(m.through_month) +
							"</b></p>";
					}
					html +=
						"<p>" +
						__("Cutoff") +
						": " +
						frappe.utils.escape_html(m.cutoff_date || prev.cutoff || "") +
						" — " +
						__("Rows") +
						": " +
						(prev.total_rows || 0) +
						"</p><ul>";
					(prev.doctypes || []).forEach((d) => {
						html +=
							"<li>" +
							frappe.utils.escape_html(d.doctype) +
							": " +
							d.rows +
							"</li>";
					});
					html += "</ul>";
					frappe.msgprint({ title: __("Archive Preview"), message: html, wide: true });
				});
		});

		frm.add_custom_button(__("Run Archive Now"), () => {
			const phrase = frm.doc.confirmation_phrase || "ARCHIVE";
			if (!frm.doc.archive_through_year && !frm.doc.archive_through_month) {
				frappe.msgprint(__("Pick Archive Through Fiscal Year or Archive Through Month first."));
				return;
			}
			frappe.prompt(
				[
					{
						fieldname: "fiscal_year",
						fieldtype: "Data",
						label: __("Archive through year"),
						default: frm.doc.archive_through_year,
						read_only: 1,
					},
					{
						fieldname: "through_month",
						fieldtype: "Data",
						label: __("Archive through month"),
						default: frm.doc.archive_through_month,
						read_only: 1,
					},
					{
						fieldname: "confirmation",
						fieldtype: "Data",
						label: __("Type {0} to confirm", [phrase]),
						reqd: 1,
					},
					{
						fieldname: "run_now",
						fieldtype: "Check",
						label: __("Run now (do not wait for a background worker)"),
						default: 1,
					},
				],
				(values) => {
					const run_now = cint(values.run_now);
					frappe
						.call({
							method: "erpnext_data_archiver.api.confirm_archive",
							freeze: true,
							freeze_message: run_now
								? __("Archiving now. This can take a few minutes.")
								: __("Queuing archive…"),
							timeout: run_now ? 600000 : 120000,
							args: {
								confirmation: values.confirmation,
								fiscal_year:
									frm.doc.monthly_in_current_year && frm.doc.archive_through_month
										? null
										: frm.doc.archive_through_year,
								through_month:
									frm.doc.monthly_in_current_year
										? frm.doc.archive_through_month
										: null,
								run_now,
							},
						})
						.then((r) =>
							frappe.show_alert({
								message: (r.message && r.message.message) || __("Archive started"),
								indicator: "green",
							})
						);
				},
				__("Confirm Archive"),
				__("Start Archive")
			);
		});

		frm.add_custom_button(__("Open Retrieve Archived Data"), () => {
			frappe.set_route("archive-retrieval");
		});

		frm.add_custom_button(__("Diagnostics"), () => {
			frappe.call("erpnext_data_archiver.api.get_diagnostics").then((r) => {
				const d = r.message || { wrapped: [], skipped: [] };
				frappe.msgprint({
					title: __("Archive report patches"),
					message:
						"<b>" +
						__("Wrapped report entry points") +
						"</b><br>" +
						(d.wrapped.join("<br>") || __("none")) +
						"<br><br><b>" +
						__("Skipped (version differences)") +
						"</b><br>" +
						(d.skipped.join("<br>") || __("none")),
					wide: true,
				});
			});
		});
	},

	archive_through_year(frm) {
		if (!frm.doc.archive_through_year || frm.doc.archive_through_month) return;
		frappe.call({
			method: "erpnext_data_archiver.api.preview_archive",
			args: { fiscal_year: frm.doc.archive_through_year },
			callback(r) {
				const cutoff = r.message && r.message.cutoff_date;
				if (cutoff) {
					frm.set_value("cutoff_date", cutoff);
				}
			},
		});
	},

	archive_through_month(frm) {
		if (!frm.doc.archive_through_month) return;
		frappe.call({
			method: "erpnext_data_archiver.api.preview_archive",
			args: { through_month: frm.doc.archive_through_month },
			callback(r) {
				const cutoff = r.message && r.message.cutoff_date;
				if (cutoff) {
					frm.set_value("cutoff_date", cutoff);
				}
			},
		});
	},
});
