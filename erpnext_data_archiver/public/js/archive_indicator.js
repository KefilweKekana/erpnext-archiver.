// Navbar indicator: shows a pill whenever the user has archive years active,
// with a one-click way back to live data.
$(document).on("app_ready", function () {
	if (!frappe.boot.archiver || !frappe.boot.archiver.enabled) return;

	function render_pill() {
		const years = (frappe.boot.archiver && frappe.boot.archiver.session_years) || [];
		$(".eda-nav-pill").remove();
		if (!years.length) return;

		const $pill = $(`
			<span class="eda-nav-pill" title="${__("Archive years active for your session. Click to manage.")}">
				${__("Archive")}: ${frappe.utils.escape_html(years.join(", "))}
			</span>
		`);
		$pill.on("click", () => frappe.set_route("archive-retrieval"));
		$(".navbar .navbar-nav").first().before($pill);
	}

	render_pill();

	// Keep the pill in sync after activate/deactivate calls from the page.
	const orig_call = frappe.call;
	frappe.call = function (opts, ...rest) {
		const method = typeof opts === "string" ? opts : opts && opts.method;
		if (
			method === "erpnext_data_archiver.api.activate_archive_years" ||
			method === "erpnext_data_archiver.api.deactivate_archive_years"
		) {
			const wrap = (cb) =>
				function (r) {
					if (r && r.message) {
						frappe.boot.archiver = frappe.boot.archiver || {};
						frappe.boot.archiver.session_years = r.message.session_years || [];
						render_pill();
					}
					if (cb) cb(r);
				};
			if (typeof opts === "string") {
				// frappe.call(method, args) form — args may carry callback.
				const args = Object.assign({}, rest[0]);
				args.callback = wrap(args.callback);
				rest[0] = args;
			} else {
				opts = Object.assign({}, opts, { callback: wrap(opts.callback) });
			}
		}
		return orig_call.call(this, opts, ...rest);
	};
});
