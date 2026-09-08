"""The persistence primitive: one Codex thread driven through a fixed continuation loop.

This module stays free of imports on purpose. `runner` reaches the admission boundary in
`lib/`, so re-exporting it here would make importing `session` or a prompt drag that along.
Import the module you actually need.
"""
