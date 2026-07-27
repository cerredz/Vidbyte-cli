"""Public process-I/O contracts. Keep this facade free of optional terminal dependencies."""

from .streams import IOStreams

__all__ = ["IOStreams"]
