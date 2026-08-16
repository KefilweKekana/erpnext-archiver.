"""Fiscal-year helpers with ERPNext-version-tolerant fallbacks (v14-v16)."""

import frappe
from frappe.utils import getdate, nowdate


def fiscal_year_for_date(date):
    """Return the Fiscal Year name whose range contains ``date`` (or None)."""
    date = getdate(date)
    rows = frappe.db.sql(
        """
        SELECT name FROM `tabFiscal Year`
        WHERE %s BETWEEN year_start_date AND year_end_date
        ORDER BY year_start_date DESC
        LIMIT 1
        """,
        (date,),
    )
    return rows[0][0] if rows else None


def fiscal_year_bounds(fiscal_year):
    """Return (start, end) dates for a Fiscal Year name."""
    row = frappe.db.sql(
        "SELECT year_start_date, year_end_date FROM `tabFiscal Year` WHERE name = %s",
        (fiscal_year,),
    )
    if row:
        return getdate(row[0][0]), getdate(row[0][1])
    return None, None


def current_fy_start():
    """Safest current-fiscal-year start across all companies.

    Uses the **latest** company FY start so archiving never deletes into any
    company's still-open fiscal year (multi-company calendar mismatch).
    """
    starts = []
    try:
        from erpnext.accounts.utils import get_fiscal_year

        companies = frappe.get_all("Company", pluck="name") or []
        for company in companies or [None]:
            try:
                fy = get_fiscal_year(nowdate(), company=company)
                # get_fiscal_year returns (name, year_start_date, year_end_date)
                starts.append(getdate(fy[1]))
            except Exception:
                continue
    except Exception:
        pass

    if not starts:
        # Fallback: any Fiscal Year containing today.
        name = fiscal_year_for_date(nowdate())
        if name:
            start, _end = fiscal_year_bounds(name)
            if start:
                return start

    if starts:
        return max(starts)

    # Last-resort fallback: start of the calendar year.
    today = getdate(nowdate())
    return today.replace(month=1, day=1)


def company_fy_starts():
    """Map company name → current FY start date (for per-row archive guards)."""
    out = {}
    try:
        from erpnext.accounts.utils import get_fiscal_year

        for company in frappe.get_all("Company", pluck="name") or []:
            try:
                fy = get_fiscal_year(nowdate(), company=company)
                out[company] = getdate(fy[1])
            except Exception:
                continue
    except Exception:
        pass
    return out


def cutoff_after_fiscal_year(fiscal_year):
    """First date that must stay live after archiving through ``fiscal_year``."""
    from frappe.utils import add_days

    _start, end = fiscal_year_bounds(fiscal_year)
    if not end:
        end = _infer_year_end(fiscal_year)
    if not end:
        frappe.throw(f"Fiscal Year {fiscal_year} was not found.")
    return add_days(getdate(end), 1)


def _infer_year_end(fiscal_year):
    """Best-effort year end when Fiscal Year master row is missing."""
    text = str(fiscal_year or "").strip()
    # Patterns: 2024-2025, 2024-25, FY 2024-25
    import re

    m = re.search(r"(20\d{2})\s*[-/]\s*(\d{2}|\d{4})", text)
    if m:
        end_raw = m.group(2)
        end_year = int(end_raw) if len(end_raw) == 4 else 2000 + int(end_raw)
        return getdate(f"{end_year}-12-31")
    if len(text) >= 4 and text[:4].isdigit():
        year = int(text[:4])
        return getdate(f"{year}-12-31")
    return None


def list_completed_fiscal_years():
    """Fiscal years that have fully ended before the current FY start."""
    current_start = current_fy_start()
    return frappe.db.sql(
        """
        SELECT name, year_start_date, year_end_date
        FROM `tabFiscal Year`
        WHERE IFNULL(disabled, 0) = 0
          AND year_end_date < %s
        ORDER BY year_end_date ASC
        """,
        (current_start,),
        as_dict=True,
    )
