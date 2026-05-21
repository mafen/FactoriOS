import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factorios_launcher import paths
from factorios_launcher.providers.base import LaunchSelection
from factorios_launcher.providers.minecraft import (
    MinecraftError,
    MinecraftProvider,
    _download_to,
    _effective_libraries,
    _merge_version_meta,
    _offline_player_name,
    _replace_placeholders,
    _resolve_runtime_component,
    _resolve_version_chain,
    _rules_allow,
)


class FakeResponse:
    def __init__(self, payload=None, chunks=None, status_code=200):
        self.payload = payload
        self.chunks = chunks or []
        self.status_code = status_code
        self.headers = {"content-length": str(sum(len(c) for c in self.chunks))}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self.payload

    def iter_content(self, _size):
        yield from self.chunks

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeHTTP:
    def __init__(self, mapping):
        self.mapping = mapping

    def get(self, url, **kwargs):
        response = self.mapping[url]
        if callable(response):
            response = response(url, **kwargs)
        return response


class MinecraftProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        root = Path(self.tempdir.name) / "gameos"
        legacy = Path(self.tempdir.name) / "factorios"
        self.patcher = mock.patch.multiple(
            paths,
            ROOT=root,
            LEGACY_ROOT=legacy,
            VERSIONS=root / "versions",
            USERS=root / "users",
            LAST_USER=root / "last-user",
            PROVIDERS=root / "providers",
            PROVIDER_CONFIG=root / "providers.json",
            LOCAL_USER="_local",
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_merge_version_meta_concatenates_arguments_and_libraries(self):
        parent = {
            "libraries": [{"name": "parent"}],
            "arguments": {"game": ["--demo"], "jvm": ["-Xmx1G"]},
            "downloads": {"client": {"url": "parent"}},
        }
        child = {
            "libraries": [{"name": "child"}],
            "arguments": {"game": ["--fullscreen"]},
            "downloads": {"client": {"url": "child"}},
        }

        merged = _merge_version_meta(parent, child)

        self.assertEqual([lib["name"] for lib in merged["libraries"]], ["parent", "child"])
        self.assertEqual(merged["arguments"]["game"], ["--demo", "--fullscreen"])
        self.assertEqual(merged["downloads"]["client"]["url"], "child")

    def test_resolve_version_chain_merges_parent_manifest(self):
        http = FakeHTTP(
            {
                "https://child": FakeResponse({"id": "child", "inheritsFrom": "base", "libraries": [{"name": "child"}]}),
                "https://base": FakeResponse({"id": "base", "libraries": [{"name": "base"}], "mainClass": "net.example.Main"}),
            }
        )
        versions = {
            "child": {"url": "https://child"},
            "base": {"url": "https://base"},
        }

        merged = _resolve_version_chain(http, versions, "child", {})

        self.assertEqual(merged["mainClass"], "net.example.Main")
        self.assertEqual([lib["name"] for lib in merged["libraries"]], ["base", "child"])

    def test_effective_libraries_prefers_last_override(self):
        libs = _effective_libraries(
            {
                "libraries": [
                    {"name": "same", "downloads": {"artifact": {"path": "old.jar"}}},
                    {"name": "same", "downloads": {"artifact": {"path": "new.jar"}}},
                ]
            }
        )

        self.assertEqual(len(libs), 1)
        self.assertEqual(libs[0]["downloads"]["artifact"]["path"], "new.jar")

    def test_rules_allow_linux_allow_rule(self):
        self.assertTrue(_rules_allow([{"action": "allow", "os": {"name": "linux"}}]))
        self.assertFalse(_rules_allow([{"action": "allow", "os": {"name": "osx"}}]))

    def test_replace_placeholders(self):
        self.assertEqual(
            _replace_placeholders("--username=${auth_player_name}", {"auth_player_name": "alex"}),
            "--username=alex",
        )

    def test_offline_player_name_uses_profile_for_local_user(self):
        self.assertEqual(_offline_player_name("_local", "builder"), "builder")
        self.assertEqual(_offline_player_name("alex", "builder"), "alex")

    def test_download_to_raises_checksum_error(self):
        http = FakeHTTP({"https://file": FakeResponse(chunks=[b"wrong"])})
        dest = Path(self.tempdir.name) / "bad.bin"

        with self.assertRaises(MinecraftError):
            _download_to(http, "https://file", dest, sha1="deadbeef", label="test file")

    def test_runtime_component_falls_back_when_requested_feed_is_missing(self):
        http = FakeHTTP(
            {
                "https://launchermeta.mojang.com/v1/products/java-runtime/java-runtime-delta/all.json": lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("http 404")),
                "https://launchermeta.mojang.com/v1/products/java-runtime/java-runtime-gamma/all.json": FakeResponse(
                    {"linux": [{"manifest": {"url": "https://runtime-manifest"}}]}
                ),
            }
        )

        with mock.patch(
            "factorios_launcher.providers.minecraft._fetch_json",
            side_effect=[
                MinecraftError("missing delta"),
                {"linux": [{"manifest": {"url": "https://runtime-manifest"}}]},
            ],
        ):
            resolved = _resolve_runtime_component(http, "java-runtime-delta")

        self.assertEqual(resolved, "java-runtime-gamma")

    def test_install_runtime_falls_back_to_system_java_when_no_managed_feed_exists(self):
        provider = MinecraftProvider()
        http = FakeHTTP({})
        version_meta = {"javaVersion": {"component": "java-runtime-epsilon"}}
        messages: list[str] = []

        with (
            mock.patch("factorios_launcher.providers.minecraft._resolve_runtime_component", side_effect=MinecraftError("missing")),
            mock.patch("factorios_launcher.providers.minecraft.shutil.which", return_value="/usr/bin/java"),
        ):
            resolved = provider._install_runtime(http, version_meta, status=messages.append)

        self.assertEqual(resolved, "system-java")
        self.assertTrue(any("using system Java" in message for message in messages))

    def test_launch_uses_system_java_fallback_runtime(self):
        provider = MinecraftProvider()
        version_dir = paths.provider_versions(provider.id) / "1.20.6"
        version_dir.mkdir(parents=True, exist_ok=True)
        (version_dir / "natives").mkdir()
        (version_dir / "1.20.6.jar").write_bytes(b"jar")

        lib = paths.provider_libraries(provider.id) / "lib/example.jar"
        lib.parent.mkdir(parents=True, exist_ok=True)
        lib.write_bytes(b"lib")

        meta = {
            "id": "1.20.6",
            "mainClass": "net.minecraft.client.main.Main",
            "javaVersion": {"component": "java-runtime-epsilon"},
            "assetIndex": {"id": "17"},
            "_gameos": {"runtime_component": "system-java"},
            "libraries": [
                {"name": "example", "downloads": {"artifact": {"path": "lib/example.jar"}}}
            ],
            "arguments": {
                "jvm": ["-cp", "${classpath}"],
                "game": ["--username", "${auth_player_name}", "--gameDir", "${game_directory}"],
            },
        }
        (version_dir / "version.json").write_text(json.dumps(meta))

        selection = LaunchSelection(provider=provider.id, username="_local", version="1.20.6", profile="builder")

        with (
            mock.patch("factorios_launcher.providers.minecraft.subprocess.Popen") as popen,
            mock.patch("factorios_launcher.providers.minecraft.shutil.which", return_value="/usr/bin/java"),
            mock.patch("pathlib.Path.is_file", autospec=True, side_effect=lambda path: str(path) in {"/usr/bin/java", str(version_dir / "version.json"), str(version_dir / "1.20.6.jar"), str(lib)}),
        ):
            popen.return_value = mock.Mock()
            provider.launch(selection)

        args = popen.call_args.args[0]
        self.assertEqual(args[0], "/usr/bin/java")

    def test_launch_builds_expected_arguments_and_updates_instance_metadata(self):
        provider = MinecraftProvider()
        version_dir = paths.provider_versions(provider.id) / "1.20.6"
        version_dir.mkdir(parents=True, exist_ok=True)
        (version_dir / "natives").mkdir()
        (version_dir / "1.20.6.jar").write_bytes(b"jar")

        lib = paths.provider_libraries(provider.id) / "lib/example.jar"
        lib.parent.mkdir(parents=True, exist_ok=True)
        lib.write_bytes(b"lib")

        java = paths.provider_runtimes(provider.id) / "java-runtime-gamma" / "bin" / "java"
        java.parent.mkdir(parents=True, exist_ok=True)
        java.write_text("")
        java.chmod(0o755)

        meta = {
            "id": "1.20.6",
            "mainClass": "net.minecraft.client.main.Main",
            "javaVersion": {"component": "java-runtime-gamma"},
            "assetIndex": {"id": "17"},
            "libraries": [
                {"name": "example", "downloads": {"artifact": {"path": "lib/example.jar"}}}
            ],
            "arguments": {
                "jvm": ["-cp", "${classpath}"],
                "game": ["--username", "${auth_player_name}", "--gameDir", "${game_directory}"],
            },
        }
        (version_dir / "version.json").write_text(json.dumps(meta))

        selection = LaunchSelection(provider=provider.id, username="_local", version="1.20.6", profile="builder")

        with mock.patch("factorios_launcher.providers.minecraft.subprocess.Popen") as popen:
            popen.return_value = mock.Mock()
            provider.launch(selection)

        args = popen.call_args.args[0]
        self.assertEqual(args[0], str(java))
        self.assertIn("--username", args)
        self.assertIn("builder", args)
        instance_meta = json.loads(
            (paths.user_provider_profile("_local", provider.id, "builder") / "instance.json").read_text()
        )
        self.assertEqual(instance_meta["selected_version"], "1.20.6")
        self.assertEqual(instance_meta["last_launched_version"], "1.20.6")


if __name__ == "__main__":
    unittest.main()
