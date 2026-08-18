frappe.pages["archive-retrieval"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Retrieve Archived Data"),
		single_column: true,
	});

	ensure_eda_stylesheet();

	const state = { data: null, show_zero: false, poll_timer: null };
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
						<button type="button" class="btn btn-primary eda-activate" disabled>
							${__("Apply to this session")}
						</button>
						<button type="button" class="btn btn-default eda-deactivate">
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
							"To archive: pick a closed fiscal year under Run archive. Leave Run now ticked so the job starts immediately. Restore is available after a run completes."
						)}
					</p>
					<div class="eda-op-cards">
						<div role="button" tabindex="0" class="eda-op-card eda-run">
							<span class="eda-op-copy">
								<span class="eda-op-title">${__("Run archive")}</span>
								<span class="eda-op-desc">${__(
									"Pick a fiscal year to move out of live tables"
								)}</span>
							</span>
							<span class="eda-op-chevron" aria-hidden="true"></span>
						</div>
						<div role="button" tabindex="0" class="eda-op-card eda-restore">
							<span class="eda-op-copy">
								<span class="eda-op-title">${__("Restore a year")}</span>
								<span class="eda-op-desc">${__("Copy one fiscal year back into live data")}</span>
							</span>
							<span class="eda-op-chevron" aria-hidden="true"></span>
						</div>
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

	function ensure_eda_stylesheet() {
		// Always inject layout-critical rules so v15 Desk still looks right
		// when public assets are missing or not rebuilt yet.
		if (!document.getElementById("eda-archiver-critical")) {
			const style = document.createElement("style");
			style.id = "eda-archiver-critical";
			style.textContent = `
.eda-page{--eda-ink:var(--text-color,#1f272e);--eda-muted:var(--text-muted,#687385);--eda-line:var(--border-color,#dce1e8);--eda-surface:var(--fg-color,var(--card-bg,#fff));--eda-subtle:var(--subtle-fg,var(--control-bg,#f4f6f8));--eda-accent:var(--primary,#249689);max-width:1080px;margin:0 auto;padding:4px 12px 48px;color:var(--eda-ink);box-sizing:border-box}
.eda-page *,.eda-page *::before,.eda-page *::after{box-sizing:border-box}
.eda-muted{color:var(--eda-muted)!important;font-size:12.5px;line-height:1.45;margin:0}
.eda-hero{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(240px,1fr);gap:14px;margin:8px 0 18px}
.eda-kicker{margin:0 0 6px;font-size:11px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:var(--eda-muted)}
.eda-hero-title{margin:0 0 8px;font-size:1.45rem;line-height:1.25;font-weight:700}
.eda-hero-sub{margin:0;max-width:48ch;font-size:13.5px;line-height:1.5;color:var(--eda-muted)}
.eda-status{display:flex!important;align-items:flex-start;gap:12px;padding:14px 16px;border-radius:12px;border:1px solid var(--eda-line);background:var(--eda-surface);min-height:72px}
.eda-status.is-live{background:#eef8f1;border-color:rgba(36,150,137,.28)}
.eda-status.is-archive{background:#fff7eb;border-color:rgba(201,120,18,.32)}
.eda-pulse{width:10px;height:10px;margin-top:5px;border-radius:50%;flex:0 0 auto;background:#249689;box-shadow:0 0 0 4px rgba(36,150,137,.16)}
.eda-status.is-archive .eda-pulse{background:#d97706;box-shadow:0 0 0 4px rgba(217,119,6,.16)}
.eda-status strong{display:block;font-size:13.5px;font-weight:700}
.eda-status-detail{margin-top:3px;font-size:12.5px;color:var(--eda-muted)}
.eda-grid{display:grid!important;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:14px;margin-bottom:14px}
.eda-panel{display:block;background:var(--eda-surface)!important;border:1px solid var(--eda-line)!important;border-radius:14px!important;padding:16px 18px!important;box-shadow:0 1px 2px rgba(16,24,40,.04)}
.eda-panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:14px}
.eda-panel-head h3{margin:0;font-size:14px;font-weight:700}
.eda-count-chip{display:inline-flex;align-items:center;font-size:11px;font-weight:650;padding:4px 9px;border-radius:999px;background:var(--eda-subtle);color:var(--eda-muted);border:1px solid var(--eda-line)}
.eda-years{display:grid;gap:8px}
.eda-year{display:flex!important;align-items:center;gap:12px;margin:0!important;padding:12px 14px!important;border-radius:11px;border:1px solid var(--eda-line);background:var(--eda-subtle);cursor:pointer}
.eda-year.is-on{background:rgba(36,150,137,.1);border-color:rgba(36,150,137,.55)}
.eda-year-input{position:absolute;opacity:0;pointer-events:none}
.eda-year-check{width:20px;height:20px;border-radius:6px;border:1.5px solid rgba(31,39,46,.28);background:#fff;flex:0 0 auto;position:relative}
.eda-year.is-on .eda-year-check{background:#249689;border-color:#249689}
.eda-year.is-on .eda-year-check::after{content:"";position:absolute;left:6px;top:2px;width:5px;height:10px;border:solid #fff;border-width:0 2px 2px 0;transform:rotate(45deg)}
.eda-year-body{display:flex;flex-direction:column;gap:2px;min-width:0;flex:1}
.eda-year-name{font-size:1.15rem;font-weight:750;line-height:1.15}
.eda-year-rows{font-size:12px;color:var(--eda-muted)}
.eda-toolbar{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px;padding-top:14px;border-top:1px solid var(--eda-line)}
.eda-op-cards{display:grid!important;gap:8px;margin-top:12px}
.eda-op-card{display:flex!important;flex-direction:row!important;align-items:center!important;justify-content:space-between!important;gap:12px;width:100%;text-align:left;padding:12px 14px!important;border-radius:11px!important;border:1px solid var(--eda-line)!important;background:var(--eda-subtle)!important;cursor:pointer}
.eda-op-card.is-disabled{opacity:.55;cursor:not-allowed}
.eda-op-copy{display:flex!important;flex-direction:column!important;align-items:flex-start!important;gap:2px!important;min-width:0;flex:1}
.eda-op-title{display:block!important;width:100%;font-size:13.5px!important;font-weight:700!important;line-height:1.3!important}
.eda-op-desc{display:block!important;width:100%;font-size:12px!important;font-weight:400!important;color:var(--eda-muted)!important;line-height:1.4!important}
.eda-op-chevron{flex:0 0 auto;width:18px;height:18px;opacity:.45;background:no-repeat center/14px 14px url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='none' stroke='%23687385' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M6 3l5 5-5 5'/%3E%3C/svg%3E")}
.eda-badge{display:inline-flex!important;align-items:center;padding:3px 8px;border-radius:999px;font-size:11px;font-weight:700}
.eda-badge.is-ok{background:#e4f5e9;color:#176b3a}
.eda-badge.is-warn{background:#fff4e5;color:#9a4d00}
.eda-foot-tools{display:flex;align-items:center;gap:12px;flex-wrap:wrap;justify-content:flex-end}
.eda-toggle{display:inline-flex!important;align-items:center;gap:6px;margin:0!important;font-size:12px;color:var(--eda-muted);cursor:pointer}
.eda-bars{display:flex;flex-direction:column;gap:11px}
.eda-bar-row{display:grid!important;grid-template-columns:minmax(140px,200px) minmax(0,1fr) 72px;gap:12px;align-items:center}
.eda-bar-label{font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.eda-bar-track{display:block!important;height:9px!important;border-radius:999px;background:var(--eda-subtle)!important;border:1px solid var(--eda-line);overflow:hidden}
.eda-bar-fill{display:block!important;height:100%!important;border-radius:inherit;background:linear-gradient(90deg,#1f8a7e,#2bb3a3);min-width:4px}
.eda-bar-value{font-size:12.5px;font-variant-numeric:tabular-nums;font-weight:650;text-align:right}
.eda-empty{padding:22px 16px;border:1px dashed var(--eda-line);border-radius:12px;text-align:center;background:var(--eda-subtle)}
.eda-empty-title{font-weight:700;margin-bottom:4px}
@media (max-width:900px){.eda-hero,.eda-grid{grid-template-columns:1fr!important}.eda-bar-row{grid-template-columns:1fr 64px!important;grid-template-areas:"label value" "track track";gap:6px 10px}.eda-bar-label{grid-area:label}.eda-bar-value{grid-area:value}.eda-bar-track{grid-area:track}}
`;
			document.head.appendChild(style);
		}

		const id = "eda-archiver-css";
		if (document.getElementById(id)) return;
		const link = document.createElement("link");
		link.id = id;
		link.rel = "stylesheet";
		link.type = "text/css";
		link.href = "/assets/erpnext_data_archiver/css/archiver.css?v=1.1.4";
		document.head.appendChild(link);
	}

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
			schedule_poll();
		});
	}

	function schedule_poll() {
		if (state.poll_timer) {
			clearTimeout(state.poll_timer);
			state.poll_timer = null;
		}
		const active = state.data && state.data.active_run;
		if (active) {
			state.poll_timer = setTimeout(refresh, 5000);
		}
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
						"Run an archive from Operations (Run now), or queue one and start a long-queue worker. Archived years appear here after a run completes."
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
			$main.find(".eda-restore").toggleClass("is-disabled", !years.length);
			$main
				.find(".eda-cutoff")
				.text(
					__("Cutoff for the next run: {0}", [
						frappe.datetime.str_to_user(d.cutoff_date),
					])
				);
			const lr = d.active_run || d.last_run;
			const $lr = $main.find(".eda-last-run");
			if (lr) {
				const ok = lr.status === "Completed";
				const running = d.active_run && lr.name === d.active_run.name;
				$lr.html(
					`<span class="eda-badge ${ok ? "is-ok" : running ? "is-warn" : "is-warn"}">${frappe.utils.escape_html(
						lr.status
					)}</span>` +
						`<code class="eda-run-id">${frappe.utils.escape_html(lr.name)}</code>` +
						(running
							? `<span class="eda-muted">${__("In progress — page refreshes automatically")}</span>`
							: "")
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

	function open_run_dialog() {
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
				{
					fieldname: "run_now",
					fieldtype: "Check",
					label: __("Run now (do not wait for a background worker)"),
					default: 1,
				},
			],
			primary_action_label: __("Start Archive"),
			primary_action(values) {
				const run_now = cint(values.run_now);
				d.disable_primary_action();
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
							fiscal_year: values.fiscal_year,
							run_now,
						},
					})
					.then((r) => {
						const m = (r && r.message) || {};
						frappe.show_alert({
							message:
								m.message ||
								(m.queued
									? __("Archive run queued for {0}", [values.fiscal_year])
									: __("Archive completed for {0}", [values.fiscal_year])),
							indicator: "green",
						});
						d.hide();
						refresh();
					})
					.finally(() => d.enable_primary_action());
			},
		});
		d.fields_dict.fiscal_year.$input.on("change", () => {
			d.set_df_property("cutoff_note", "options", cutoff_note_html(d.get_value("fiscal_year")));
		});
		d.show();
	}

	function open_restore_dialog() {
		const years = (state.data.archived_years || []).map((y) => y.fiscal_year);
		if (!years.length) {
			frappe.msgprint(
				__(
					"Nothing to restore yet. Complete an archive run first — queued jobs do not create archived years until a worker finishes them."
				)
			);
			return;
		}
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
				{
					fieldname: "run_now",
					fieldtype: "Check",
					label: __("Run now (do not wait for a background worker)"),
					default: 1,
				},
			],
			primary_action_label: __("Preview & Restore"),
			primary_action: (values) => {
				const run_now = cint(values.run_now);
				d.disable_primary_action();
				frappe.call("erpnext_data_archiver.api.preview_restore", values).then((r) => {
					const p = r.message || {};
					const finish = (force) =>
						frappe
							.call({
								method: "erpnext_data_archiver.api.restore_year",
								freeze: true,
								freeze_message: run_now
									? __("Restoring {0}…", [values.fiscal_year])
									: __("Queuing restore…"),
								timeout: run_now ? 600000 : 120000,
								args: {
									fiscal_year: values.fiscal_year,
									force: force || 0,
									run_now,
								},
							})
							.then((res) => {
								const m = (res && res.message) || {};
								frappe.show_alert({
									message: m.message || __("Restore started"),
									indicator: "green",
								});
								d.hide();
								refresh();
							})
							.catch(() => d.enable_primary_action());
					if (!p.ok) {
						frappe.confirm(
							__(
								"Collisions detected with live documents. Force restore (INSERT IGNORE) anyway?"
							),
							() => finish(1),
							() => d.enable_primary_action()
						);
						return;
					}
					finish(0);
				}).catch(() => d.enable_primary_action());
			},
		});
		d.show();
	}

	$main.on("click", ".eda-run", open_run_dialog);
	$main.on("keydown", ".eda-run", (e) => {
		if (e.key === "Enter" || e.key === " ") {
			e.preventDefault();
			open_run_dialog();
		}
	});
	$main.on("click", ".eda-restore", open_restore_dialog);
	$main.on("keydown", ".eda-restore", (e) => {
		if (e.key === "Enter" || e.key === " ") {
			e.preventDefault();
			open_restore_dialog();
		}
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
