"""Single source of truth for FactoriOS on-disk layout.

The original appliance only knew about Factorio, so several helpers below
remain Factorio-shaped for compatibility. New code should prefer the
provider-oriented helpers near the top of the file.
"""

import json
from pathlib import Path

ROOT = Path("/var/lib/factorios")
VERSIONS = ROOT / "versions"
USERS = ROOT / "users"
LAST_USER = ROOT / "last-user"
PROVIDERS = ROOT / "providers"
PROVIDER_CONFIG = ROOT / "providers.json"

PROVIDER_FACTORIO = "factorio"
PROVIDER_MINECRAFT = "minecraft"
ALL_PROVIDERS = (PROVIDER_FACTORIO, PROVIDER_MINECRAFT)

# Reserved names for the guest/demo flow. factorio.com usernames are
# alphanumeric, so a leading underscore can never collide with a real one.
GUEST_USER = "_guest"
LOCAL_USER = "_local"
DEMO_VERSION = "_demo"

# Build identifiers. The user-facing names (vanilla, space-age) map to
# factorio.com's internal build names (alpha, expansion). These map both
# directions here so the rest of the codebase never deals in alpha/expansion.
BUILD_VANILLA = "vanilla"
BUILD_SPACE_AGE = "space-age"
ALL_BUILDS = (BUILD_VANILLA, BUILD_SPACE_AGE)
BUILD_DISPLAY = {
    BUILD_VANILLA: "Vanilla",
    BUILD_SPACE_AGE: "Space Age",
}
BUILD_API = {
    BUILD_VANILLA: "alpha",
    BUILD_SPACE_AGE: "expansion",
}
DEFAULT_BUILD = BUILD_SPACE_AGE  # used when the user owns both


def provider_root(provider: str) -> Path:
    return PROVIDERS / provider


def provider_versions(provider: str) -> Path:
    return provider_root(provider) / "versions"


def provider_assets(provider: str) -> Path:
    return provider_root(provider) / "assets"


def provider_libraries(provider: str) -> Path:
    return provider_root(provider) / "libraries"


def provider_runtimes(provider: str) -> Path:
    return provider_root(provider) / "runtimes"


def provider_state(provider: str) -> Path:
    return provider_root(provider) / "state"


def enabled_providers() -> tuple[str, ...]:
    try:
        data = json.loads(PROVIDER_CONFIG.read_text())
    except (OSError, json.JSONDecodeError):
        return ALL_PROVIDERS
    if isinstance(data, list):
        providers = [item for item in data if item in ALL_PROVIDERS]
        if providers:
            return tuple(providers)
    return ALL_PROVIDERS


def user_provider_dir(username: str, provider: str) -> Path:
    return user_dir(username) / provider


def user_provider_profiles(username: str, provider: str) -> Path:
    return user_provider_dir(username, provider) / "profiles"


def user_provider_profile(username: str, provider: str, profile: str) -> Path:
    return user_provider_profiles(username, provider) / profile


# --- users / sessions / profiles --------------------------------------

def user_dir(username: str) -> Path:
    return USERS / username


def user_session(username: str) -> Path:
    return user_dir(username) / "session.json"


def user_profiles(username: str, build: str | None = None) -> Path:
    """Profiles root for a user. Build-segregated for real accounts, flat
    for the guest/demo flow."""
    base = user_dir(username) / "profiles"
    return base / build if build is not None else base


def profile_dir(username: str, profile: str, build: str | None = None) -> Path:
    return user_profiles(username, build) / profile


def user_factorio_dir(username: str) -> Path:
    """LEGACY pre-per-profile path: a user-level ~/.factorio target that
    sat above all of the user's profiles. Kept for the one-shot migration
    in profiles._link_home_factorio that folds its contents into whichever
    profile launches first. New code should not write here — the profile
    directory IS the Factorio write-data dir now (paths.profile_dir)."""
    return user_dir(username) / "factorio"


def user_last_launch(username: str) -> Path:
    """Per-user record of the last (build, version, profile) chosen for
    launch. Read on greeter startup to pre-select the same triple."""
    return user_dir(username) / "last-launch.json"


# --- versions ---------------------------------------------------------

def version_id(version: str, build: str) -> str:
    """The on-disk identifier for an authenticated install. Demo passes
    DEMO_VERSION directly and skips this."""
    return f"{version}-{build}"


def version_dir(version_id: str) -> Path:
    return VERSIONS / version_id


def factorio_binary(version_id: str) -> Path:
    # Layout inside the official linux64 tarball.
    return version_dir(version_id) / "bin" / "x64" / "factorio"
