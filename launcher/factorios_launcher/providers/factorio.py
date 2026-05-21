"""Factorio provider adapter around the original launcher modules."""

from __future__ import annotations

from .. import paths, profiles, versions
from ..auth import Session
from ..download import is_newer, latest_releases
from .base import GameProvider, LaunchSelection, ReleaseChoice


class FactorioProvider(GameProvider):
    id = paths.PROVIDER_FACTORIO
    name = "Factorio"
    requires_auth = True
    supports_remembered_login = True
    variant_label = "Build"

    def available_variants(self, session: Session | None = None) -> list[str]:
        if session and session.has_space_age:
            return [paths.BUILD_SPACE_AGE, paths.BUILD_VANILLA]
        return [paths.BUILD_VANILLA]

    def default_variant(self, session: Session | None = None) -> str | None:
        if session and session.has_space_age:
            return paths.DEFAULT_BUILD
        return paths.BUILD_VANILLA

    def display_variant(self, variant: str) -> str:
        return paths.BUILD_DISPLAY.get(variant, variant)

    def list_installed(self, variant: str | None = None) -> list[str]:
        build = variant or paths.BUILD_VANILLA
        return versions.list_installed_for_build(build)

    def list_profiles(self, username: str, variant: str | None = None) -> list[str]:
        return profiles.list_profiles(username, build=variant)

    def ensure_profile(self, username: str, profile: str, variant: str | None = None):
        return profiles.ensure(username, profile, build=variant)

    def delete_profile(self, username: str, profile: str, variant: str | None = None) -> None:
        profiles.remove(username, profile, build=variant)

    def delete_version(self, version: str, variant: str | None = None) -> None:
        build = variant or paths.BUILD_VANILLA
        versions.remove(version, build)

    def release_choices(
        self,
        session: Session | None = None,
        variant: str | None = None,
    ) -> list[ReleaseChoice]:
        build = variant or self.default_variant(session)
        if build is None:
            return []
        releases = latest_releases(session or Session())
        api = paths.BUILD_API[build]
        stable = releases.get("stable", {}).get(api)
        experimental = releases.get("experimental", {}).get(api)
        choices: list[ReleaseChoice] = []
        if stable:
            choices.append(ReleaseChoice(stable, f"Latest stable ({stable})"))
        if experimental and (not stable or is_newer(experimental, stable)):
            choices.append(ReleaseChoice(experimental, f"Latest experimental ({experimental})"))
        return choices

    def install(
        self,
        username: str,
        version: str,
        session: Session | None = None,
        variant: str | None = None,
        progress=None,
        status=None,
    ):
        if session is None:
            raise RuntimeError("Factorio install requires an authenticated session.")
        build = variant or self.default_variant(session)
        if build is None:
            raise RuntimeError("No Factorio build available.")
        return versions.install(session, version, build=build, progress=progress)

    def launch(self, selection: LaunchSelection, session: Session | None = None):
        build = selection.variant or paths.BUILD_VANILLA
        return profiles.launch(
            paths.version_id(selection.version, build),
            selection.username,
            selection.profile,
            build=build,
            session=session,
            use_mimalloc=selection.use_mimalloc,
        )
