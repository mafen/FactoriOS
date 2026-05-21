"""Small UI-facing context objects."""

from __future__ import annotations

from dataclasses import dataclass

from factorios_launcher.auth import Session


@dataclass
class UserContext:
    username: str
    factorio_session: Session | None = None

    @property
    def has_factorio_auth(self) -> bool:
        return self.factorio_session is not None
