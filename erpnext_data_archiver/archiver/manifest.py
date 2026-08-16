"""Batch checksums and manifest helpers (SAFE-002 / SAFE-003)."""

from __future__ import annotations

import hashlib
from typing import Iterable, Sequence


CRITICAL_FIELD_CANDIDATES = (
	"name",
	"debit",
	"credit",
	"debit_in_account_currency",
	"credit_in_account_currency",
	"actual_qty",
	"qty",
	"stock_value_difference",
	"incoming_rate",
	"valuation_rate",
	"grand_total",
	"outstanding_amount",
	"paid_amount",
	"base_grand_total",
	"amount",
	"net_amount",
)


def pick_critical_fields(columns: Sequence[str]) -> list[str]:
	cols = set(columns)
	picked = [c for c in CRITICAL_FIELD_CANDIDATES if c in cols]
	if "name" not in picked and "name" in cols:
		picked.insert(0, "name")
	return picked or (["name"] if "name" in cols else list(columns)[:5])


def row_fingerprint(row: dict, fields: Sequence[str]) -> str:
	parts = []
	for f in fields:
		v = row.get(f)
		if v is None:
			parts.append("")
		else:
			parts.append(str(v))
	return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def batch_checksum(fingerprints: Iterable[str]) -> str:
	"""Order-independent checksum of row fingerprints."""
	joined = "|".join(sorted(fingerprints))
	return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def verify_batch(expected_count: int, actual_count: int, expected_hash: str, actual_hash: str) -> None:
	if expected_count != actual_count:
		raise ValueError(
			f"Batch count mismatch: expected {expected_count}, got {actual_count}"
		)
	if expected_hash != actual_hash:
		raise ValueError(
			f"Batch checksum mismatch: expected {expected_hash}, got {actual_hash}"
		)
