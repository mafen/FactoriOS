import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factorios_launcher import last_launch, paths


class PathsAndStateTests(unittest.TestCase):
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
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_existing_last_launch_prefers_legacy_when_new_missing(self):
        legacy = paths.legacy_user_last_launch("alice")
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text('{"version":"1.20.6","profile":"legacy"}')

        loaded = last_launch.load_last_launch("alice")

        self.assertEqual(loaded["profile"], "legacy")
        self.assertEqual(paths.existing_user_last_launch("alice"), legacy)

    def test_save_last_launch_writes_to_new_root(self):
        last_launch.save_last_launch("bob", {"game": "minecraft", "version": "1.20.6"})

        new_path = paths.user_last_launch("bob")
        self.assertTrue(new_path.is_file())
        self.assertEqual(last_launch.load_last_launch("bob")["version"], "1.20.6")


if __name__ == "__main__":
    unittest.main()
