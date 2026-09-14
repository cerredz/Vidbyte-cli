"""Provider adapters for local context connections."""

from .github import GitHubConnectionAdapter
from .google_drive import GoogleDriveConnectionAdapter
from .slack import SlackConnectionAdapter

__all__ = ["GitHubConnectionAdapter", "GoogleDriveConnectionAdapter", "SlackConnectionAdapter"]
