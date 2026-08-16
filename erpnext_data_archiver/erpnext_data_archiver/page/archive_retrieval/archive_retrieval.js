frappe.pages["archive-retrieval"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Retrieve Archived Data"),
		single_column: true,
	});

	const state = { data: null, show_zero: false };
	const $main = $(page.main);

	$main.html(`
		<div class="eda-page">
			<header class="eda-hero">
				<div class="eda-hero-copy">
					<p class="eda-kicker">${__("Session view")}</p>
					<h2 class="eda-hero-title">${__("Choose which archived years to read")}</h2>
					<p class="eda-hero-sub">
						${__(
							"Retrieval does not move data. It only changes what this session can see in reports and lists."
						)}
					</p>
				</div>
				<div class="eda-hero-status eda-status" style="display:none"></div>
			</header>

			<div class="eda-grid">
				<section class="eda-panel eda-panel--years">
					<div class="eda-panel-head">
						<h3>${__("Archived years")}</h3>
						<span class="eda-count-chip eda-year-count"></span>
					</div>
					<div class="eda-years"></div>
					<div class="eda-toolbar">
						<button class="btn btn-primary eda-activate" disabled>
							${__("Apply to this session")}
						</button>
						<button class="btn btn-default eda-deactivate">
							${__("Use live data only")}
						</button>
					</div>
				</section>

				<section class="eda-panel eda-panel--manage eda-manager" style="display:none">
					<div class="eda-panel-head">
						<div>
							<h3>${__("Operations")}</h3>
							<p class="eda-cutoff eda-muted"></p>
						</div>
						<div class="eda-last-run"></div>
					</div>
					<p class="eda-muted" style="margin:0 0 4px">
						${__(
							"To archive: pick a closed fiscal year under Run archive. The year list on the left is only for reading years already archived."
						)}
					</p>
					<div class="eda-op-cards">
						<button type="button" class="eda-op-card eda-run">
							<span class="eda-op-copy">
								<span class="eda-op-title">${__("Run archive")}</span>
								<span class="eda-op-desc">${__(
									"Pick a fiscal year to move out of live tables"
								)}</span>
							</span>
							<span class="eda-op-chevron" aria-hidden="true"></span>
						</button>
						<button type="button" class="eda-op-card eda-restore">
							<span class="eda-op-copy">
								<span class="eda-op-title">${__("Restore a year")}</span>
								<span class="eda-op-desc">${__("Copy one fiscal year back into live data")}</span>
							</span>
							<span class="eda-op-chevron" aria-hidden="true"></span>
						</button>
					</div>
				</section>
			</div>

			<section class="eda-panel eda-panel--foot">
				<div class="eda-panel-head">
					<div>
						<h3>${__("Live footprint")}</h3>
						<p class="eda-muted">
							${__("Rows still in live tables (current period and retained open documents).")}
						</p>
					</div>
					<div class="eda-foot-tools">
						<span class="eda-footprint-summary eda-muted"></span>
						<label class="eda-toggle">
							<input type="checkbox" class="eda-show-zero">
							<span>${__("Show empty")}</span>
						</label>
					</div>
				</div>
				<div class="eda-bars"></div>
			</section>
		</div>
	`);

	function cint(v) {
		const n = parseInt(v, 10);
		return isNaN(n) ? 0 : n;
	}

	function format_rows(n) {
		try {
			return cint(n).toLocaleString();
		} catch (e) {
			return String(cint(n));
		}
	}

	function refresh() {
		frappe.call("erpnext_data_archiver.api.get_state").then((r) => {
			state.data = r.message;
			render();
		});
	}

	function render() {
		const d = state.data;
		if (!d) return;

		const active = d.session_years || [];
		const $status = $main.find(".eda-status");

		if (active.length) {
			$status
				.show()
				.removeClass("is-live")
				.addClass("is-archive")
				.html(
					`<span class="eda-pulse"></span>` +
						`<div><strong>${__("Archive mode")}</strong>` +
						`<div class="eda-status-detail">${__("Reading live data plus {0}", [
							frappe.utils.escape_html(active.join(", ")),
						])}</div></div>`
				);
		} else {
			$status
				.show()
				.removeClass("is-archive")
				.addClass("is-live")
				.html(
					`<span class="eda-pulse"></span>` +
						`<div><strong>${__("Live mode")}</strong>` +
						`<div class="eda-status-detail">${__(
							"Only the current fiscal year and open documents"
						)}</div></div>`
				);
		}

		const years = d.archived_years || [];
		$main
			.find(".eda-year-count")
			.text(years.length ? __("{0} available", [years.length]) : __("None yet"));

		const $years = $main.find(".eda-years").empty();
		if (!years.length) {
			$years.html(
				`<div class="eda-empty">
					<div class="eda-empty-title">${__("Nothing archived yet")}</div>
					<div class="eda-muted">${__(
						"Run an archive from Archive Settings, then return here to browse history."
					)}</div>
				</div>`
			);
			$main.find(".eda-activate").prop("disabled", true);
		} else {
			years.forEach((y) => {
				const checked = active.includes(y.fiscal_year);
				const fy = frappe.utils.escape_html(y.fiscal_year);
				$years.append(`
					<label class="eda-year ${checked ? "is-on" : ""}">
						<input type="checkbox" class="eda-year-input" value="${fy}" ${checked ? "checked" : ""}>
						<span class="eda-year-check" aria-hidden="true"></span>
						<span class="eda-year-body">
							<span class="eda-year-name">${fy}</span>
							<span class="eda-year-rows">${format_rows(y.rows)} ${__("rows")}</span>
						</span>
					</label>
				`);
			});
			$main.find(".eda-activate").prop("disabled", false);
		}

		if (d.is_manager) {
			$main.find(".eda-manager").show();
			$main
				.find(".eda-cutoff")
				.text(
					__("Cutoff for the next run: {0}", [
						frappe.datetime.str_to_user(d.cutoff_date),
					])
				);
			const lr = d.last_run;
			const $lr = $main.find(".eda-last-run");
			if (lr) {
				const ok = lr.status === "Completed";
				$lr.html(
					`<span class="eda-badge ${ok ? "is-ok" : "is-warn"}">${frappe.utils.escape_html(
						lr.status
					)}</span>` +
						`<code class="eda-run-id">${frappe.utils.escape_html(lr.name)}</code>`
				);
			} else {
				$lr.html(`<span class="eda-muted">${__("No runs yet")}</span>`);
			}
		}

		render_footprint(d.live_tables || []);
	}

	function render_footprint(tables) {
		const total = tables.reduce((s, t) => s + cint(t.live_rows), 0);
		const max = Math.max(...tables.map((t) => cint(t.live_rows)), 1);
		const visible = state.show_zero ? tables : tables.filter((t) => cint(t.live_rows) > 0);
		const hidden = tables.length - visible.length;

		$main
			.find(".eda-footprint-summary")
			.text(__("{0} live rows", [format_rows(total)]));

		const $bars = $main.find(".eda-bars").empty();
		if (!visible.length) {
			$bars.html(`<div class="eda-empty">${__("All configured live tables are empty.")}</div>`);
			return;
		}

		visible.forEach((t) => {
			const rows = cint(t.live_rows);
			const pct = Math.max(2, Math.round((rows / max) * 100));
			$bars.append(`
				<div class="eda-bar-row ${rows === 0 ? "is-zero" : ""}">
					<div class="eda-bar-label">${frappe.utils.escape_html(t.doctype)}</div>
					<div class="eda-bar-track">
						<div class="eda-bar-fill" style="width:${pct}%"></div>
					</div>
					<div class="eda-bar-value">${format_rows(rows)}</div>
				</div>
			`);
		});

		if (!state.show_zero && hidden > 0) {
			$bars.append(
				`<div class="eda-bar-note eda-muted">${__("{0} empty DocTypes hidden", [hidden])}</div>`
			);
		}
	}

	$main.on("change", ".eda-year-input", function () {
		$(this).closest(".eda-year").toggleClass("is-on", this.checked);
	});

	$main.on("change", ".eda-show-zero", function () {
		state.show_zero = this.checked;
		if (state.data) render_footprint(state.data.live_tables || []);
	});

	$main.on("click", ".eda-activate", function () {
		const years = $main
			.find(".eda-year-input:checked")
			.map((_, el) => el.value)
			.get();
		frappe
			.call("erpnext_data_archiver.api.activate_archive_years", {
				years: JSON.stringify(years),
			})
			.then(() => {
				frappe.show_alert({
					message: years.length
						? __("Session includes {0}", [years.join(", ")])
						: __("Live data only"),
					indicator: "green",
				});
				refresh();
			});
	});

	$main.on("click", ".eda-deactivate", function () {
		frappe.call("erpnext_data_archiver.api.deactivate_archive_years").then(() => {
			frappe.show_alert({ message: __("Live data only"), indicator: "blue" });
			refresh();
		});
	});

	$main.on("click", ".eda-run", function () {
		const years = state.data.archivable_years || [];
		const phrase = state.data.confirmation_phrase || "ARCHIVE";
		if (!years.length) {
			frappe.msgprint(
				__(
					"No completed fiscal years are available to archive yet. Create older Fiscal Years in ERPNext, or wait until the current year ends."
				)
			);
			return;
		}

		const default_year =
			state.data.archive_through_year ||
			(years.filter((y) => !y.already_archived).slice(-1)[0] || years[years.length - 1])
				.fiscal_year;

		function cutoff_note_html(fy) {
			const meta = years.find((y) => y.fiscal_year === fy);
			if (!meta) return "";
			return `<p class="text-muted" style="margin:0">
				${__("Will archive all eligible data before")}
				<strong>${frappe.utils.escape_html(meta.cutoff_date)}</strong>
				${meta.already_archived ? " · " + __("This year is already in archive.") : ""}
			</p>`;
		}

		const d = new frappe.ui.Dialog({
			title: __("Archive a Fiscal Year"),
			fields: [
				{
					fieldname: "help",
					fieldtype: "HTML",
					options: `<p class="text-muted" style="margin:0 0 8px">
						${__(
							"Choose the last closed year to archive. Everything through the end of that year leaves live tables. Newer years stay live."
						)}
					</p>`,
				},
				{
					fieldname: "fiscal_year",
					fieldtype: "Select",
					label: __("Archive through fiscal year"),
					options: years.map((y) => y.fiscal_year).join("\n"),
					default: default_year,
					reqd: 1,
				},
				{
					fieldname: "cutoff_note",
					fieldtype: "HTML",
					options: cutoff_note_html(default_year),
				},
				{
					fieldname: "confirmation",
					fieldtype: "Data",
					label: __("Type {0} to confirm", [phrase]),
					reqd: 1,
				},
			],
			primary_action_label: __("Queue Archive"),
			primary_action(values) {
				frappe
					.call({
						method: "erpnext_data_archiver.api.confirm_archive",
						args: {
							confirmation: values.confirmation,
							fiscal_year: values.fiscal_year,
						},
					})
					.then(() => {
						frappe.show_alert({
							message: __("Archive run queued for {0}", [values.fiscal_year]),
							indicator: "green",
						});
						d.hide();
						refresh();
					});
			},
		});
		d.fields_dict.fiscal_year.$input.on("change", () => {
			d.set_df_property("cutoff_note", "options", cutoff_note_html(d.get_value("fiscal_year")));
		});
		d.show();
	});

	$main.on("click", ".eda-restore", function () {
		const years = (state.data.archived_years || []).map((y) => y.fiscal_year);
		if (!years.length) return;
		const d = new frappe.ui.Dialog({
			title: __("Restore a Fiscal Year"),
			fields: [
				{
					fieldname: "fiscal_year",
					fieldtype: "Select",
					label: __("Fiscal Year"),
					options: years.join("\n"),
					default: years[0],
					reqd: 1,
				},
			],
			primary_action_label: __("Preview & Restore"),
			primary_action: (values) => {
				frappe.call("erpnext_data_archiver.api.preview_restore", values).then((r) => {
					const p = r.message || {};
					if (!p.ok) {
						frappe.confirm(
							__(
								"Collisions detected with live documents. Force restore (INSERT IGNORE) anyway?"
							),
							() =>
								frappe
									.call("erpnext_data_archiver.api.restore_year", {
										fiscal_year: values.fiscal_year,
										force: 1,
									})
									.then(() => {
										frappe.show_alert({
											message: __("Restore queued"),
											indicator: "green",
										});
										d.hide();
									})
						);
						return;
					}
					frappe.call("erpnext_data_archiver.api.restore_year", values).then(() => {
						frappe.show_alert({
							message: __("Restore queued"),
							indicator: "green",
						});
						d.hide();
					});
				});
			},
		});
		d.show();
	});

	frappe.realtime.on("eda_archive_progress", (data) => {
		frappe.show_alert(
			{
				message: __("Archiving {0}: {1} rows", [data.doctype, data.rows_archived]),
				indicator: "blue",
			},
			3
		);
	});

	refresh();
};
