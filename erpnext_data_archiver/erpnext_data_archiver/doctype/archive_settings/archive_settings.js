frappe.ui.form.on("Archive Settings", {
	refresh(frm) {
		if (!frappe.user.has_role(["System Manager", "Archive Manager"])) return;

		frm.add_custom_button(__("Preview Archive"), () => {
			frappe
				.call("erpnext_data_archiver.api.preview_archive", {
					fiscal_year: frm.doc.archive_through_year,
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
			if (!frm.doc.archive_through_year) {
				frappe.msgprint(__("Pick Archive Through Fiscal Year first."));
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
						fieldname: "confirmation",
						fieldtype: "Data",
						label: __("Type {0} to confirm", [phrase]),
						reqd: 1,
					},
				],
				(values) => {
					frappe
						.call({
							method: "erpnext_data_archiver.api.confirm_archive",
							args: {
								confirmation: values.confirmation,
								fiscal_year: frm.doc.archive_through_year,
							},
						})
						.then(() =>
							frappe.show_alert({
								message: __("Archive run queued"),
								indicator: "green",
							})
						);
				},
				__("Confirm Archive"),
				__("Queue Archive")
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
		if (!frm.doc.archive_through_year) return;
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
});
