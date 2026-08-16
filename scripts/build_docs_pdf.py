"""Build Product + Testing + Operator PDFs (Octanode proposal style)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_professional():
	path = ROOT / "scripts" / "build_professional_docs.py"
	spec = importlib.util.spec_from_file_location("build_professional_docs", path)
	mod = importlib.util.module_from_spec(spec)
	assert spec.loader is not None
	spec.loader.exec_module(mod)
	return mod


def build_all():
	return _load_professional().build_all()


if __name__ == "__main__":
	build_all()
