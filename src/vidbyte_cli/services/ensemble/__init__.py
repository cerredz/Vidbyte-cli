"""The same-host ensemble: one planner turn, N read-only proposals, one implementer.

Exports only what a caller outside this package needs. Every Vidbyte SDK symbol stays
behind `sdk.py`, which is the single module that imports the SDK at all.
"""

from .runner import EnsembleRunner

__all__ = ["EnsembleRunner"]
