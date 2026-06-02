"""Compatibility wrapper. Prefer scripts/legacy/auto_import_data.py."""

import runpy

if __name__ == "__main__":
    runpy.run_module("scripts.legacy.auto_import_data", run_name="__main__")
