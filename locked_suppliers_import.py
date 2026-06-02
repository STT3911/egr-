"""Compatibility wrapper. Prefer scripts/legacy/locked_suppliers_import.py."""

import runpy

if __name__ == "__main__":
    runpy.run_module("scripts.legacy.locked_suppliers_import", run_name="__main__")
