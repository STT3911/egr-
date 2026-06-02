"""Compatibility wrapper. Prefer scripts/legacy/init_seed.py."""

import runpy

if __name__ == "__main__":
    runpy.run_module("scripts.legacy.init_seed", run_name="__main__")
