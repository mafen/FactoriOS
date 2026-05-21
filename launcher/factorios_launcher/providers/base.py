"""Provider abstraction shared by the greeter and CLI."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from ..download import ProgressCb


@dataclass(frozen=True)
class ReleaseChoice:
    version: str
    label: str


@dataclass(frozen=True)
class LaunchSelection:
    provider: str
    username: str
    version: str
    profile: str
    variant: str | None = None
    use_mimalloc: bool = True


class GameProvider(ABC):
    id: str
    name: str
    requires_auth: bool = False
    supports_remembered_login: bool = False
    variant_label: str | None = None

    def available_variants(self, session: Any = None) -> list[str]:
        return []

    def default_variant(self, session: Any = None) -> str | None:
        variants = self.available_variants(session)
        return variants[0] if variants else None

    def display_variant(self, variant: str) -> str:
        return variant

    @abstractmethod
    def list_installed(self, variant: str | None = None) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def list_profiles(self, username: str, variant: str | None = None) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def ensure_profile(self, username: str, profile: str, variant: str | None = None):
        raise NotImplementedError

    @abstractmethod
    def delete_profile(self, username: str, profile: str, variant: str | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete_version(self, version: str, variant: str | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def release_choices(
        self,
        session: Any = None,
        variant: str | None = None,
    ) -> list[ReleaseChoice]:
        raise NotImplementedError

    @abstractmethod
    def install(
        self,
        username: str,
        version: str,
        session: Any = None,
        variant: str | None = None,
        progress: ProgressCb | None = None,
    ):
        raise NotImplementedError

    @abstractmethod
    def launch(self, selection: LaunchSelection, session: Any = None):
        raise NotImplementedError
