"""Marks the repository-local lint suite as an importable package.

The suite is deliberately outside `src/`, so it never ships in the wheel and never imports
the CLI it analyzes. `python lint/run.py` is its only entry point.
"""
