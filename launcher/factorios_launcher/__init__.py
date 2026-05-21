"""Game appliance launcher library used by GameOS."""

from .auth import Session, AuthError
from . import paths, versions, profiles, download
from .providers import all_providers, get_provider, LaunchSelection, ReleaseChoice

__all__ = [
    "Session",
    "AuthError",
    "paths",
    "versions",
    "profiles",
    "download",
    "all_providers",
    "get_provider",
    "LaunchSelection",
    "ReleaseChoice",
]
