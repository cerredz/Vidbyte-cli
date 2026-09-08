"""Shared machinery every lint rule depends on: discovery, contracts, ratchet, reporting.

Nothing here scans for a specific violation — a rule owns its own detection. Nothing here
imports `vidbyte_cli`, because a lint run must work on source that does not import cleanly.
"""
