"""Persistence helpers for chooser last-launch state."""

from __future__ import annotations

import json

from . import paths


def load_last_launch(username: str) -> dict | None:
    path = paths.existing_user_last_launch(username)
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save_last_launch(username: str, record: dict) -> None:
    path = paths.user_last_launch(username)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record))
