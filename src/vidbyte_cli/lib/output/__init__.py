"""Public presentation contracts. Feature presenters stay private to their own slices."""

from .formats import ColorMode, OutputFormat
from .manager import OutputManager, OutputPolicy
from .models import OutputDocument

__all__ = ["ColorMode", "OutputDocument", "OutputFormat", "OutputManager", "OutputPolicy"]
