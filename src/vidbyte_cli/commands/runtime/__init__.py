"""Static commands for locally executed Vidbyte runtime primitives.

This group is distinct from hosted services because execution remains on the user's
machine and delegates to an installed native coding-agent host.
"""

from .adversarial_team import AdversarialTeamCommand
from .doctor import RuntimeDoctorCommand
from .list import RuntimeListCommand
from .persistence import PersistenceCommand

__all__ = [
    "AdversarialTeamCommand",
    "PersistenceCommand",
    "RuntimeDoctorCommand",
    "RuntimeListCommand",
]
