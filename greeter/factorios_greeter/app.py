"""GameOS greeter Gtk.Application — top-level wiring."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from gameos_launcher import paths

from .chooser import ChooserScreen
from .context import UserContext


class GreeterWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application) -> None:
        super().__init__(application=application, title="GameOS")
        self.set_default_size(720, 520)
        self.set_resizable(True)
        # Don't call self.fullscreen() — under labwc on VirtualBox's vmwgfx,
        # the fullscreen mode-set triggers a DRM hot-unplug of the virtual
        # connector (~13s after start), which kills the compositor and
        # restart-loops the session. Kiosk-style fullscreening should come
        # from the compositor config, not the app.
        self.set_child(ChooserScreen(UserContext(username=paths.LOCAL_USER), on_switch_user=self._noop_switch_user))

    def _noop_switch_user(self) -> None:
        # Minecraft-only appliance: there is no auth surface to switch away from.
        return


class GreeterApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id="com.gameos.Greeter")

    def do_activate(self) -> None:
        window = GreeterWindow(self)
        window.present()


def main() -> int:
    return GreeterApp().run(None)
