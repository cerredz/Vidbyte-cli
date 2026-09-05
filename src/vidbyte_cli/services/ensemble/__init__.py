"""The same-host ensemble: one planner turn, N read-only proposals, one implementer.

This module stays free of imports on purpose. `runner` pulls in the whole API stack, so
re-exporting it here would make importing `sdk` or `settings` drag that stack along and
expose the import-order cycle between `lib.auth` and `lib.api.client`. Import the module
you actually need.
"""
