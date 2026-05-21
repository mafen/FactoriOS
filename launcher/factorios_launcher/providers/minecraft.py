"""Minecraft provider using Mojang's official manifests.

This is intentionally v1-scoped:
  * vanilla only
  * local/offline profiles only
  * provider-managed Java runtime downloads
  * Linux launch rules only
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any

import requests

from .. import paths
from ..download import ProgressCb
from .base import GameProvider, LaunchSelection, ReleaseChoice, StatusCb

VERSION_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
JAVA_RUNTIME_URL = "https://launchermeta.mojang.com/v1/products/java-runtime/{component}/all.json"
DEFAULT_PROFILE = "default"
OS_NAME = "linux"
ARCH_NAME = "64" if platform.machine().lower() in {"x86_64", "amd64"} else platform.machine().lower()
RULE_OS = "linux"
LAUNCHER_BRAND = "GameOS"
LAUNCHER_VERSION = "0.1"


class MinecraftError(RuntimeError):
    """Raised for user-facing Minecraft install / launch failures."""


def _http() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = f"{LAUNCHER_BRAND}-launcher/{LAUNCHER_VERSION}"
    return s


class MinecraftProvider(GameProvider):
    id = paths.PROVIDER_MINECRAFT
    name = "Minecraft"

    def list_installed(self, variant: str | None = None) -> list[str]:
        root = paths.provider_versions(self.id)
        if not root.exists():
            return []
        return sorted(p.name for p in root.iterdir() if p.is_dir() and (p / "version.json").is_file())

    def list_profiles(self, username: str, variant: str | None = None) -> list[str]:
        root = paths.user_provider_profiles(username, self.id)
        if not root.exists():
            return []
        return sorted(p.name for p in root.iterdir() if p.is_dir())

    def ensure_profile(self, username: str, profile: str, variant: str | None = None) -> Path:
        root = paths.user_provider_profile(username, self.id, profile)
        (root / "saves").mkdir(parents=True, exist_ok=True)
        (root / "resourcepacks").mkdir(parents=True, exist_ok=True)
        (root / "shaderpacks").mkdir(parents=True, exist_ok=True)
        (root / "mods").mkdir(parents=True, exist_ok=True)
        self._write_instance_meta(username, profile)
        return root

    def delete_profile(self, username: str, profile: str, variant: str | None = None) -> None:
        root = paths.user_provider_profile(username, self.id, profile)
        if root.exists():
            shutil.rmtree(root)

    def delete_version(self, version: str, variant: str | None = None) -> None:
        root = paths.provider_versions(self.id) / version
        if root.exists():
            shutil.rmtree(root)

    def release_choices(
        self,
        session: Any = None,
        variant: str | None = None,
    ) -> list[ReleaseChoice]:
        manifest = _fetch_json(_http(), VERSION_MANIFEST_URL, "version manifest lookup")
        latest = manifest.get("latest", {})
        versions = manifest.get("versions", [])
        choices: list[ReleaseChoice] = []
        release_id = latest.get("release")
        snapshot_id = latest.get("snapshot")
        if release_id:
            choices.append(ReleaseChoice(release_id, f"Latest release ({release_id})"))
        if snapshot_id and snapshot_id != release_id:
            choices.append(ReleaseChoice(snapshot_id, f"Latest snapshot ({snapshot_id})"))
        seen = {choice.version for choice in choices}
        for item in versions:
            version_id = item.get("id")
            if not version_id or version_id in seen:
                continue
            if item.get("type") not in {"release", "snapshot"}:
                continue
            choices.append(ReleaseChoice(version_id, f"{version_id} ({item.get('type', 'unknown')})"))
            seen.add(version_id)
            if len(choices) >= 8:
                break
        return choices

    def install(
        self,
        username: str,
        version: str,
        session: Any = None,
        variant: str | None = None,
        progress: ProgressCb | None = None,
        status: StatusCb | None = None,
    ) -> Path:
        versions_root = paths.provider_versions(self.id)
        versions_root.mkdir(parents=True, exist_ok=True)
        version_dir = versions_root / version
        if (version_dir / "version.json").is_file():
            meta = json.loads((version_dir / "version.json").read_text())
            self.ensure_profile(username, DEFAULT_PROFILE)
            self._write_instance_meta(
                username,
                DEFAULT_PROFILE,
                selected_version=version,
                java_component=((meta.get("javaVersion") or {}).get("component")),
            )
            return version_dir

        _push_status(status, "Fetching version metadata…")
        http = _http()
        manifest = _fetch_json(http, VERSION_MANIFEST_URL, "version manifest lookup")
        resolved = _resolve_version_meta(http, manifest, version)

        stage = Path(tempfile.mkdtemp(prefix=f".{version}.", dir=str(versions_root)))
        try:
            (stage / "natives").mkdir(parents=True, exist_ok=True)
            _push_status(status, "Downloading client jar…")
            client = ((resolved.get("downloads") or {}).get("client")) or {}
            if not isinstance(client, dict) or not client.get("url"):
                raise MinecraftError(f"Version {version} is missing a downloadable client jar.")
            _download_to(
                http,
                client["url"],
                stage / f"{version}.jar",
                progress=progress,
                sha1=client.get("sha1"),
                label="client jar",
            )

            _push_status(status, "Syncing asset index…")
            self._install_asset_index(http, resolved, progress=progress)
            _push_status(status, "Syncing assets…")
            self._install_assets(http, resolved, progress=progress)
            _push_status(status, "Downloading libraries…")
            self._install_libraries(http, resolved, stage, progress=progress)
            _push_status(status, "Provisioning Java runtime…")
            runtime_component = self._install_runtime(http, resolved, progress=progress)

            resolved["_gameos"] = {
                "runtime_component": runtime_component,
                "selected_version": version,
            }
            (stage / "version.json").write_text(json.dumps(resolved, indent=2))

            if version_dir.exists():
                shutil.rmtree(version_dir)
            stage.rename(version_dir)
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise

        self.ensure_profile(username, DEFAULT_PROFILE)
        self._write_instance_meta(
            username,
            DEFAULT_PROFILE,
            selected_version=version,
            java_component=runtime_component,
        )
        return version_dir

    def launch(self, selection: LaunchSelection, session: Any = None):
        version_dir = paths.provider_versions(self.id) / selection.version
        meta_path = version_dir / "version.json"
        if not meta_path.is_file():
            raise MinecraftError(f"Minecraft version {selection.version} is not installed.")

        meta = json.loads(meta_path.read_text())
        if not meta.get("mainClass"):
            raise MinecraftError(f"Minecraft version {selection.version} is missing a main class.")
        profile_dir = self.ensure_profile(selection.username, selection.profile)
        runtime = self._runtime_executable(meta)
        if not runtime.is_file():
            raise MinecraftError("Managed Java runtime is missing.")

        natives_dir = version_dir / "natives"
        classpath = self._classpath(meta, selection.version)
        args = [
            str(runtime),
            *self._jvm_args(meta, selection.version, profile_dir, natives_dir, classpath),
            meta["mainClass"],
            *self._game_args(meta, selection.version, selection.username, selection.profile, profile_dir),
        ]
        env = os.environ.copy()
        env["MESA_GL_VERSION_OVERRIDE"] = env.get("MESA_GL_VERSION_OVERRIDE", "4.5")
        self._write_instance_meta(
            selection.username,
            selection.profile,
            selected_version=selection.version,
            java_component=((meta.get("javaVersion") or {}).get("component")),
            last_launched_version=selection.version,
        )
        return subprocess.Popen(args, cwd=profile_dir, env=env)

    def _install_asset_index(self, http: requests.Session, version_meta: dict, progress: ProgressCb | None = None) -> None:
        asset_index = version_meta.get("assetIndex") or {}
        asset_root = paths.provider_assets(self.id)
        indexes = asset_root / "indexes"
        indexes.mkdir(parents=True, exist_ok=True)
        if not asset_index.get("url"):
            raise MinecraftError("Version metadata is missing an asset index.")
        _download_to(
            http,
            asset_index["url"],
            indexes / f"{asset_index['id']}.json",
            progress=progress,
            sha1=asset_index.get("sha1"),
            label="asset index",
        )

    def _install_assets(self, http: requests.Session, version_meta: dict, progress: ProgressCb | None = None) -> None:
        asset_index = version_meta.get("assetIndex") or {}
        index_path = paths.provider_assets(self.id) / "indexes" / f"{asset_index['id']}.json"
        if not index_path.is_file():
            raise MinecraftError("Asset index download did not produce a usable index file.")
        data = json.loads(index_path.read_text())
        objects_root = paths.provider_assets(self.id) / "objects"
        objects_root.mkdir(parents=True, exist_ok=True)
        for obj in (data.get("objects") or {}).values():
            if not isinstance(obj, dict):
                continue
            sha1 = obj.get("hash")
            if not sha1 or len(sha1) < 2:
                continue
            rel = Path(sha1[:2]) / sha1
            target = objects_root / rel
            if target.is_file():
                continue
            url = f"https://resources.download.minecraft.net/{sha1[:2]}/{sha1}"
            _download_to(http, url, target, progress=progress, sha1=sha1, label="asset object")

    def _install_libraries(
        self,
        http: requests.Session,
        version_meta: dict,
        version_dir: Path,
        progress: ProgressCb | None = None,
    ) -> None:
        libs_root = paths.provider_libraries(self.id)
        libs_root.mkdir(parents=True, exist_ok=True)
        natives_dir = version_dir / "natives"
        for lib in _effective_libraries(version_meta):
            if not _library_allowed(lib):
                continue
            downloads = lib.get("downloads", {})
            artifact = downloads.get("artifact")
            if artifact and artifact.get("url") and artifact.get("path"):
                _download_to(
                    http,
                    artifact["url"],
                    libs_root / artifact["path"],
                    progress=progress,
                    sha1=artifact.get("sha1"),
                    label=f"library {lib.get('name', artifact['path'])}",
                )
            classifier = _native_classifier_name(lib)
            if classifier:
                native = downloads.get("classifiers", {}).get(classifier)
                if native and native.get("url") and native.get("path"):
                    jar_path = libs_root / native["path"]
                    _download_to(
                        http,
                        native["url"],
                        jar_path,
                        progress=progress,
                        sha1=native.get("sha1"),
                        label=f"native {lib.get('name', native['path'])}",
                    )
                    _extract_natives(jar_path, natives_dir)

    def _install_runtime(
        self,
        http: requests.Session,
        version_meta: dict,
        progress: ProgressCb | None = None,
    ) -> str:
        component = ((version_meta.get("javaVersion") or {}).get("component")) or "jre-legacy"
        runtimes_root = paths.provider_runtimes(self.id)
        runtime_home = runtimes_root / component
        version_marker = runtime_home / ".runtime-version"
        java_bin = runtime_home / "bin" / "java"
        if java_bin.is_file() and version_marker.is_file():
            return component

        feed = _fetch_json(http, JAVA_RUNTIME_URL.format(component=component), f"Java runtime feed for {component}")
        candidates = feed.get(OS_NAME) or []
        if not candidates:
            raise MinecraftError(f"No managed Java runtime published for {component} on {OS_NAME}.")
        manifest_info = candidates[0].get("manifest") or {}
        manifest_url = manifest_info.get("url")
        if not manifest_url:
            raise MinecraftError(f"Runtime manifest for {component} is missing a URL.")
        manifest = _fetch_json(http, manifest_url, f"Java runtime manifest for {component}")

        temp_root = runtime_home.with_name(f".{runtime_home.name}.tmp")
        if temp_root.exists():
            shutil.rmtree(temp_root)
        temp_root.mkdir(parents=True, exist_ok=True)
        try:
            for rel, entry in manifest.get("files", {}).items():
                target = temp_root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                if entry.get("type") != "file":
                    continue
                raw = (entry.get("downloads") or {}).get("raw") or {}
                url = raw.get("url")
                if not url:
                    continue
                _download_to(
                    http,
                    url,
                    target,
                    progress=progress,
                    sha1=raw.get("sha1"),
                    label=f"runtime file {rel}",
                )
                if entry.get("executable"):
                    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

            if runtime_home.exists():
                shutil.rmtree(runtime_home)
            temp_root.rename(runtime_home)
        except Exception:
            shutil.rmtree(temp_root, ignore_errors=True)
            raise
        version_marker.write_text(json.dumps(candidates[0].get("version", {}), indent=2))
        return component

    def _runtime_executable(self, version_meta: dict) -> Path:
        component = ((version_meta.get("javaVersion") or {}).get("component")) or "jre-legacy"
        gameos_component = ((version_meta.get("_gameos") or {}).get("runtime_component")) or component
        return paths.provider_runtimes(self.id) / gameos_component / "bin" / "java"

    def _classpath(self, version_meta: dict, version: str) -> str:
        libs_root = paths.provider_libraries(self.id)
        parts: list[str] = []
        for lib in _effective_libraries(version_meta):
            if not _library_allowed(lib):
                continue
            artifact = (lib.get("downloads") or {}).get("artifact")
            if artifact and artifact.get("path"):
                parts.append(str(libs_root / artifact["path"]))
        parts.append(str(paths.provider_versions(self.id) / version / f"{version}.jar"))
        return ":".join(parts)

    def _jvm_args(self, version_meta: dict, version: str, profile_dir: Path, natives_dir: Path, classpath: str) -> list[str]:
        replacements = {
            "natives_directory": str(natives_dir),
            "launcher_name": LAUNCHER_BRAND,
            "launcher_version": LAUNCHER_VERSION,
            "classpath": classpath,
            "classpath_separator": ":",
            "library_directory": str(paths.provider_libraries(self.id)),
            "version_name": version,
            "game_directory": str(profile_dir),
            "assets_root": str(paths.provider_assets(self.id)),
            "assets_index_name": (version_meta.get("assetIndex") or {}).get("id", ""),
        }
        args = version_meta.get("arguments", {}).get("jvm")
        if isinstance(args, list):
            return _expand_args(args, replacements)
        return [
            f"-Djava.library.path={natives_dir}",
            f"-Dminecraft.launcher.brand={LAUNCHER_BRAND}",
            f"-Dminecraft.launcher.version={LAUNCHER_VERSION}",
            "-cp",
            classpath,
        ]

    def _game_args(
        self,
        version_meta: dict,
        version: str,
        username: str,
        profile: str,
        profile_dir: Path,
    ) -> list[str]:
        player_name = _offline_player_name(username, profile)
        replacements = {
            "auth_player_name": player_name,
            "version_name": version,
            "game_directory": str(profile_dir),
            "assets_root": str(paths.provider_assets(self.id)),
            "assets_index_name": (version_meta.get("assetIndex") or {}).get("id", ""),
            "auth_uuid": uuid.uuid5(uuid.NAMESPACE_DNS, f"{username}:{profile}").hex,
            "auth_access_token": "offline",
            "user_type": "legacy",
            "version_type": version_meta.get("type", "release"),
            "user_properties": "{}",
            "auth_session": "offline",
            "clientid": "",
            "xuid": "",
        }
        args = version_meta.get("arguments", {}).get("game")
        if isinstance(args, list):
            return _expand_args(args, replacements)
        legacy = version_meta.get("minecraftArguments", "")
        return [_replace_placeholders(part, replacements) for part in legacy.split() if part]

    def _write_instance_meta(
        self,
        username: str,
        profile: str,
        selected_version: str | None = None,
        java_component: str | None = None,
        last_launched_version: str | None = None,
    ) -> None:
        path = paths.user_provider_profile(username, self.id, profile) / "instance.json"
        data = {
            "provider": self.id,
            "profile": profile,
            "selected_version": selected_version,
            "java_component": java_component,
            "last_launched_version": last_launched_version,
        }
        if path.exists():
            try:
                current = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                current = {}
            if isinstance(current, dict):
                data = {**current, **{k: v for k, v in data.items() if v is not None}}
        path.write_text(json.dumps(data, indent=2))


def _push_status(status: StatusCb | None, message: str) -> None:
    if status:
        status(message)


def _fetch_json(http: requests.Session, url: str, label: str) -> dict:
    try:
        r = http.get(url, timeout=60)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as exc:
        raise MinecraftError(f"Failed during {label}: {exc}") from exc
    except ValueError as exc:
        raise MinecraftError(f"Failed during {label}: invalid JSON response") from exc


def _resolve_version_meta(http: requests.Session, manifest: dict, version: str) -> dict:
    versions = {item.get("id"): item for item in manifest.get("versions", []) if isinstance(item, dict)}
    if version not in versions:
        raise MinecraftError(f"Unknown Minecraft version: {version}")
    cache: dict[str, dict] = {}
    return _resolve_version_chain(http, versions, version, cache)


def _resolve_version_chain(
    http: requests.Session,
    versions: dict[str, dict],
    version: str,
    cache: dict[str, dict],
) -> dict:
    if version in cache:
        return cache[version]
    entry = versions.get(version)
    if not entry or not entry.get("url"):
        raise MinecraftError(f"Version metadata for {version} is missing a manifest URL.")
    meta = _fetch_json(http, entry["url"], f"version metadata for {version}")
    parent_version = meta.get("inheritsFrom")
    if parent_version:
        parent = _resolve_version_chain(http, versions, parent_version, cache)
        merged = _merge_version_meta(parent, meta)
    else:
        merged = meta
    cache[version] = merged
    return merged


def _merge_version_meta(parent: dict, child: dict) -> dict:
    merged: dict[str, Any] = {**parent}
    for key, value in child.items():
        if key in {"libraries"}:
            merged[key] = list(parent.get(key, [])) + list(value or [])
        elif key == "arguments":
            parent_args = parent.get("arguments", {}) if isinstance(parent.get("arguments"), dict) else {}
            child_args = value if isinstance(value, dict) else {}
            out = dict(parent_args)
            for arg_key, arg_value in child_args.items():
                if isinstance(arg_value, list) and isinstance(parent_args.get(arg_key), list):
                    out[arg_key] = list(parent_args[arg_key]) + list(arg_value)
                else:
                    out[arg_key] = arg_value
            merged[key] = out
        elif isinstance(parent.get(key), dict) and isinstance(value, dict):
            merged[key] = {**parent[key], **value}
        else:
            merged[key] = value
    merged.pop("inheritsFrom", None)
    return merged


def _effective_libraries(version_meta: dict) -> list[dict]:
    selected: dict[str, dict] = {}
    order: list[str] = []
    for lib in version_meta.get("libraries", []):
        if not isinstance(lib, dict):
            continue
        name = lib.get("name") or json.dumps(lib, sort_keys=True)
        if name not in selected:
            order.append(name)
        selected[name] = lib
    return [selected[name] for name in order]


def _download_to(
    http: requests.Session,
    url: str,
    dest: Path,
    progress: ProgressCb | None = None,
    sha1: str | None = None,
    label: str = "download",
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and sha1 and _sha1(dest) == sha1:
        return dest
    tmp = dest.with_name(f".{dest.name}.tmp")
    try:
        with http.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            done = 0
            with tmp.open("wb") as handle:
                for chunk in r.iter_content(64 * 1024):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
    except requests.RequestException as exc:
        tmp.unlink(missing_ok=True)
        raise MinecraftError(f"Failed during {label}: {exc}") from exc
    if sha1 and _sha1(tmp) != sha1:
        tmp.unlink(missing_ok=True)
        raise MinecraftError(f"Failed during {label}: checksum mismatch for {url}")
    tmp.replace(dest)
    return dest


def _sha1(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(128 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _library_allowed(lib: dict) -> bool:
    rules = lib.get("rules")
    if not rules:
        return True
    allowed = False
    for rule in rules:
        action = rule.get("action")
        os_rule = (rule.get("os") or {}).get("name")
        if os_rule and os_rule != RULE_OS:
            if action == "disallow":
                allowed = True
            continue
        allowed = action == "allow"
    return allowed


def _native_classifier_name(lib: dict) -> str | None:
    natives = lib.get("natives") or {}
    classifier = natives.get(RULE_OS)
    if not classifier:
        return None
    return classifier.replace("${arch}", ARCH_NAME)


def _extract_natives(jar_path: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(jar_path) as zf:
        for member in zf.infolist():
            name = member.filename
            if member.is_dir() or name.startswith("META-INF/"):
                continue
            target = dest / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def _expand_args(items: list, replacements: dict[str, str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if isinstance(item, str):
            out.append(_replace_placeholders(item, replacements))
            continue
        if not isinstance(item, dict):
            continue
        if not _rules_allow(item.get("rules")):
            continue
        value = item.get("value")
        if isinstance(value, list):
            out.extend(_replace_placeholders(part, replacements) for part in value)
        elif isinstance(value, str):
            out.append(_replace_placeholders(value, replacements))
    return out


def _rules_allow(rules: Any) -> bool:
    if not isinstance(rules, list) or not rules:
        return True
    allowed = False
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        action = rule.get("action")
        os_rule = (rule.get("os") or {}).get("name")
        features = rule.get("features")
        if features:
            if action == "disallow":
                allowed = True
            continue
        if os_rule and os_rule != RULE_OS:
            if action == "disallow":
                allowed = True
            continue
        allowed = action == "allow"
    return allowed


def _replace_placeholders(text: str, replacements: dict[str, str]) -> str:
    out = text
    for key, value in replacements.items():
        out = out.replace(f"${{{key}}}", value)
    return out


def _offline_player_name(username: str, profile: str) -> str:
    if username == paths.LOCAL_USER:
        return profile[:16]
    return username[:16]
