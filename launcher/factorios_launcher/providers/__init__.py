"""Provider registry."""

from __future__ import annotations

from .. import paths
from .base import GameProvider, LaunchSelection, ReleaseChoice
from .factorio import FactorioProvider
from .minecraft import MinecraftProvider

_PROVIDERS: dict[str, GameProvider] = {
    provider.id: provider
    for provider in (
        FactorioProvider(),
        MinecraftProvider(),
    )
}


def all_providers() -> list[GameProvider]:
    return [_PROVIDERS[provider_id] for provider_id in paths.enabled_providers() if provider_id in _PROVIDERS]


def get_provider(provider_id: str) -> GameProvider:
    return _PROVIDERS[provider_id]


__all__ = [
    "GameProvider",
    "LaunchSelection",
    "ReleaseChoice",
    "all_providers",
    "get_provider",
]
