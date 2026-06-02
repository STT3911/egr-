"""Compatibility wrapper. Prefer scripts/legacy/gias_del_list.py."""

import runpy

if __name__ == "__main__":
    runpy.run_module("scripts.legacy.gias_del_list", run_name="__main__")
