"""Transparent archive-aware SQL rewriting.

This module patches ``frappe.database.database.Database.sql`` once per worker
process. The wrapper is deliberately conservative:

* Only SELECT-ish queries are ever rewritten. INSERT/UPDATE/DELETE/DDL always
  pass through untouched, so writes can never hit archive tables.
* Rewriting happens only when an "archive context" is active:
    - a user activated one or more archive years via "Retrieve Archived Data"
      (stored per-user in the cache), or
    - a date-routed report sets ``include_archives`` for archive-only or
      combined modes (active-only reports never rewrite — opening-state only).
* Without an active context every query is byte-identical to vanilla Frappe,
  so day-to-day screens, lists and active-only reports only ever touch the
  small live tables (ARCH-001 / PERF-001).

The rewrite turns::

    FROM `tabGL Entry` ...

into::

    FROM (SELECT <live cols> FROM `tabGL Entry`
          UNION ALL
          SELECT <live cols> FROM `tabGL Entry Archive`
          WHERE `fiscal_year_archived` IN (...)) `tabGL Entry` ...

Archive tables are exact structural copies of the live tables plus three
metadata columns, and are indexed on (fiscal_year_archived, posting date), so
year-filtered retrieval stays indexed and scales with years.
"""

import json
import re
import threading

import frappe

# Sentinel: include every archived year (used by summary report wrappers).
ALL_YEARS = "*"

_CACHE_KEY_PREFIX = "eda_years:"            # per-user selected years
_TABLES_CACHE_KEY = "eda_archivable_tables"  # per-site table map
_COLUMNS_CACHE_KEY = "eda_table_columns:"    # per-site column lists

_ORIG_SQL = None
_INSTALLED = False
_RESOLVING = threading.local()

# Matches FROM/JOIN followed by a backticked table name; the table name is
# filled in per archivable table. Negative lookahead guards against rewriting
# references that already point at the archive table.
_FROM_JOIN_TEMPLATE = r"((?:FROM|JOIN)\s+)`{table}`(?!\s*Archive`)"


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------

def install():
    """Patch Database.sql once per process. Safe to call repeatedly."""
    global _ORIG_SQL, _INSTALLED
    if _INSTALLED:
        return
    try:
        from frappe.database.database import Database
    except Exception:
        return

    _ORIG_SQL = Database.sql

    def sql(self, query, values=(), *args, **kwargs):
        try:
            rewritten = maybe_rewrite(self, query)
            if rewritten is not None:
                query = rewritten
        except Exception:
            # A rewrite failure must never break the query itself; fall back
            # to the untouched query.
            try:
                frappe.log_error("erpnext_data_archiver: query rewrite failed")
            except Exception:
                pass
        return _ORIG_SQL(self, query, values, *args, **kwargs)

    Database.sql = sql
    _INSTALLED = True


def original_sql():
    return _ORIG_SQL


# ---------------------------------------------------------------------------
# Archive context
# ---------------------------------------------------------------------------

class include_archives:
    """Context manager: include archived rows for the wrapped code block.

    ``years=None`` means *all* archived years; otherwise pass a list of
    Fiscal Year names.
    """

    def __init__(self, years=None):
        self.years = ALL_YEARS if years is None else [str(y) for y in years]
        self._prev = None
        self._had_prev = False

    def __enter__(self):
        # NOTE: frappe.flags is a frappe._dict, whose missing-key __getattr__
        # returns None instead of raising — so membership, not hasattr, is
        # the correct presence test.
        self._had_prev = "include_archive_years" in frappe.flags
        self._prev = frappe.flags.get("include_archive_years")
        frappe.flags.include_archive_years = self.years
        return self

    def __exit__(self, *exc):
        if self._had_prev:
            frappe.flags.include_archive_years = self._prev
        else:
            try:
                del frappe.flags["include_archive_years"]
            except Exception:
                frappe.flags.include_archive_years = None
        return False


class bypass_archives:
    """Context manager: never rewrite inside the block (engine internals)."""

    def __enter__(self):
        self._depth = getattr(frappe.flags, "archiver_bypass", 0) or 0
        frappe.flags.archiver_bypass = self._depth + 1
        return self

    def __exit__(self, *exc):
        frappe.flags.archiver_bypass = self._depth
        return False


def resolve_active_years():
    """Return the active archive-year selection, ALL_YEARS, or None."""
    if frappe.flags.get("archiver_bypass"):
        return None

    if "include_archive_years" in frappe.flags:
        years = frappe.flags.get("include_archive_years")
        if years:
            return years
        return None

    # Per-request memoisation so we hit the cache at most once per request.
    memo = getattr(frappe.local, "_eda_session_years", None)
    if memo is not None:
        return memo or None

    years = None
    try:
        user = getattr(frappe.session, "user", None)
        if user and user != "Guest":
            raw = frappe.cache().get_value(_CACHE_KEY_PREFIX + user)
            if raw:
                years = json.loads(raw) or None
    except Exception:
        years = None

    try:
        frappe.local._eda_session_years = years or False
    except Exception:
        pass
    return years


def set_session_years(user, years):
    """Persist the user's archive-year selection (8 h sliding window)."""
    cache = frappe.cache()
    key = _CACHE_KEY_PREFIX + user
    if years:
        cache.set_value(key, json.dumps(list(years)), expires_in_sec=8 * 60 * 60)
    else:
        cache.delete_value(key)
    try:
        frappe.local._eda_session_years = list(years) if years else False
    except Exception:
        pass


def get_session_years(user=None):
    user = user or getattr(frappe.session, "user", None)
    if not user:
        return []
    try:
        raw = frappe.cache().get_value(_CACHE_KEY_PREFIX + user)
        return json.loads(raw) if raw else []
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Table / column metadata (cached per site)
# ---------------------------------------------------------------------------

def archive_table_name(doctype):
    """Shadow table name for a DocType, respecting the 64-char limit."""
    base = "tab" + doctype
    name = base + " Archive"
    if len(name) <= 64:
        return name
    import hashlib

    digest = hashlib.md5(base.encode()).hexdigest()[:8]
    return (base + " Arc")[:55] + "_" + digest


def _site_cache_get(key):
    try:
        return frappe.cache().get_value(key + ":" + frappe.local.site)
    except Exception:
        return None


def _site_cache_set(key, value, ttl=3600):
    try:
        frappe.cache().set_value(key + ":" + frappe.local.site, value, expires_in_sec=ttl)
    except Exception:
        pass


def clear_metadata_cache():
    for key in (_TABLES_CACHE_KEY,):
        try:
            frappe.cache().delete_value(key + ":" + frappe.local.site)
        except Exception:
            pass
    try:
        frappe.local._eda_session_years = None
    except Exception:
        pass


def get_archivable_tables():
    """Map of live table -> archive table for all enabled rules.

    Only tables whose archive shadow actually exists is included, so the
    rewrite never references missing tables.
    """
    cached = _site_cache_get(_TABLES_CACHE_KEY)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    tables = {}
    # Guard against recursion: loading the rule list itself runs SQL, which
    # re-enters maybe_rewrite; the guard makes nested calls pass through.
    _RESOLVING.active = True
    try:
        rules = frappe.get_all(
            "Archive DocType Rule",
            filters={"enabled": 1},
            fields=["doctype_name", "archive_children"],
        )
        names = [r.doctype_name for r in rules]
        for r in rules:
            if r.archive_children:
                try:
                    names.extend(
                        d.options
                        for d in frappe.get_meta(r.doctype_name).get_table_fields()
                    )
                except Exception:
                    pass
        for dt in dict.fromkeys(names):
            live = "tab" + dt
            arch = archive_table_name(dt)
            if table_exists(arch):
                tables[live] = arch
    except Exception:
        tables = {}
    finally:
        _RESOLVING.active = False

    try:
        _site_cache_set(_TABLES_CACHE_KEY, json.dumps(tables))
    except Exception:
        pass
    return tables


def table_exists(table):
    try:
        rows = _raw_sql(
            "SELECT 1 FROM information_schema.TABLES"
            " WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s LIMIT 1",
            (table,),
        )
        return bool(rows)
    except Exception:
        return False


def get_table_columns(table):
    """Ordered column names of a table (cached)."""
    key = _COLUMNS_CACHE_KEY + table
    cached = _site_cache_get(key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass
    rows = _raw_sql(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS"
        " WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s"
        " ORDER BY ORDINAL_POSITION",
        (table,),
    )
    cols = [r[0] for r in rows]
    try:
        _site_cache_set(key, json.dumps(cols))
    except Exception:
        pass
    return cols


def _raw_sql(query, values=()):
    """Run SQL through the *unpatched* Database.sql (no recursion)."""
    if _ORIG_SQL is not None:
        return _ORIG_SQL(frappe.db, query, values)
    return frappe.db.sql(query, values)


# ---------------------------------------------------------------------------
# Rewrite
# ---------------------------------------------------------------------------

def maybe_rewrite(db, query):
    """Return the rewritten query, or None if it must pass through untouched."""
    if not isinstance(query, str):
        return None

    # Re-entrancy guard (metadata lookups run SQL themselves).
    if getattr(_RESOLVING, "active", False):
        return None

    # Never rewrite while the engine itself is copying/restoring data.
    if frappe.flags.get("archiver_bypass"):
        return None

    head = query.lstrip()[:6].upper()
    if not (head.startswith("SELECT") or head.startswith("WITH") or head.startswith("(")):
        return None

    # Only act on sites that actually have the app installed.
    if not _app_active():
        return None

    years = resolve_active_years()
    if not years:
        return None

    tables = get_archivable_tables()
    if not tables:
        return None

    rewritten = query
    for live, archive in tables.items():
        if "`" + live + "`" not in rewritten:
            continue
        pattern = _FROM_JOIN_TEMPLATE.format(table=re.escape(live))
        if not re.search(pattern, rewritten):
            continue
        cols = get_table_columns(live)
        if not cols:
            continue
        # When archives are UNIONed in, exclude synthetic opening GL/SLE so history
        # is not double-counted against Archive Opening voucher rows.
        live_from = "`{live}`".format(live=live)
        if live in ("tabGL Entry", "tabStock Ledger Entry") and "voucher_type" in cols:
            live_from = (
                "(SELECT {cols} FROM `{live}`"
                " WHERE IFNULL(`voucher_type`, '') != 'Archive Opening')"
            ).format(cols=", ".join("`%s`" % c for c in cols), live=live)
        col_sql = ", ".join("`%s`" % c for c in cols)
        if years == ALL_YEARS:
            where = ""
        else:
            escaped = ", ".join(_escape(db, y) for y in years)
            where = " WHERE `fiscal_year_archived` IN (%s)" % escaped
        if live in ("tabGL Entry", "tabStock Ledger Entry") and "voucher_type" in cols:
            union = (
                "({live_from} UNION ALL "
                "SELECT {cols} FROM `{archive}`{where})"
            ).format(live_from=live_from, cols=col_sql, archive=archive, where=where)
        else:
            union = (
                "(SELECT {cols} FROM `{live}` UNION ALL "
                "SELECT {cols} FROM `{archive}`{where})"
            ).format(cols=col_sql, live=live, archive=archive, where=where)
        rewritten = re.sub(pattern, lambda m: m.group(1) + union + " `" + live + "`", rewritten)

    return rewritten if rewritten != query else None


def _escape(db, value):
    try:
        return db.escape(str(value))
    except Exception:
        return "'" + str(value).replace("'", "''") + "'"


def _app_active():
    try:
        memo = getattr(frappe.local, "_eda_app_active", None)
        if memo is not None:
            return memo
        active = "erpnext_data_archiver" in (frappe.get_installed_apps() or [])
        frappe.local._eda_app_active = active
        return active
    except Exception:
        return False
