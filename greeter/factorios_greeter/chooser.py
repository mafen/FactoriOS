"""Minecraft appliance chooser."""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from gameos_launcher import LaunchSelection, get_provider, paths
from gameos_launcher.download import ProgressStats
from gameos_launcher.last_launch import load_last_launch, save_last_launch

from . import power, updates, worker
from .context import UserContext

DEFAULT_PROFILE = "default"


class ChooserScreen(Gtk.Box):
    def __init__(self, context: UserContext, on_switch_user: Callable[[], None]) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_vexpand(True)
        self.set_hexpand(True)
        self.context = context
        self._on_switch_user = on_switch_user
        self._provider = get_provider(paths.PROVIDER_MINECRAFT)
        self._last_launch = self._load_last_launch()

        shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        shell.set_vexpand(True)
        shell.set_hexpand(True)
        shell.set_valign(Gtk.Align.CENTER)
        shell.set_halign(Gtk.Align.CENTER)
        self.append(shell)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.set_margin_top(28)
        card.set_margin_bottom(28)
        card.set_margin_start(32)
        card.set_margin_end(32)
        card.set_size_request(760, -1)
        card.set_halign(Gtk.Align.CENTER)
        shell.append(card)

        title = Gtk.Label(label="GameOS")
        title.add_css_class("title-1")
        card.append(title)

        subtitle = Gtk.Label(label="Minecraft appliance", xalign=0)
        subtitle.add_css_class("dim-label")
        subtitle.set_halign(Gtk.Align.START)
        card.append(subtitle)

        card.append(Gtk.Label(label="Version", xalign=0))
        version_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.version_combo = Gtk.DropDown.new_from_strings([])
        self.version_combo.set_hexpand(True)
        version_row.append(self.version_combo)
        self.install_button = Gtk.Button(label="Install…")
        self.install_button.connect("clicked", self._on_install_clicked)
        version_row.append(self.install_button)
        self.delete_version_button = Gtk.Button(label="Delete")
        self.delete_version_button.connect("clicked", self._on_delete_version)
        version_row.append(self.delete_version_button)
        card.append(version_row)

        card.append(Gtk.Label(label="Profile", xalign=0))
        profile_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.profile_combo = Gtk.DropDown.new_from_strings([])
        self.profile_combo.set_hexpand(True)
        profile_row.append(self.profile_combo)
        self.new_profile_button = Gtk.Button(label="New profile…")
        self.new_profile_button.connect("clicked", self._on_new_profile)
        profile_row.append(self.new_profile_button)
        self.delete_profile_button = Gtk.Button(label="Delete")
        self.delete_profile_button.connect("clicked", self._on_delete_profile)
        profile_row.append(self.delete_profile_button)
        card.append(profile_row)

        self.status = Gtk.Label(label="", xalign=0)
        self.status.add_css_class("dim-label")
        self.status.set_wrap(True)
        self.status.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.status.set_halign(Gtk.Align.FILL)
        self.status.set_max_width_chars(88)
        card.append(self.status)

        self.progress = Gtk.ProgressBar()
        self.progress.set_show_text(True)
        self.progress.set_visible(False)
        card.append(self.progress)

        self.log_scroller = Gtk.ScrolledWindow()
        self.log_scroller.set_min_content_height(180)
        self.log_scroller.set_max_content_height(260)
        self.log_scroller.set_vexpand(True)
        self.log_scroller.set_hexpand(True)
        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_cursor_visible(False)
        self.log_view.set_monospace(True)
        self.log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.log_scroller.set_child(self.log_view)
        card.append(self.log_scroller)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.END)
        self.launch_button = Gtk.Button(label="Launch")
        self.launch_button.add_css_class("suggested-action")
        self.launch_button.connect("clicked", self._on_launch)
        actions.append(self.launch_button)
        card.append(actions)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        updates_btn = Gtk.Button(label="Updates…")
        updates_btn.add_css_class("flat")
        updates_btn.connect("clicked", lambda *_: updates.show_dialog(self))
        footer.append(updates_btn)
        footer.append(Gtk.Box(hexpand=True))
        footer.append(power.make_row())
        card.append(footer)

        self._refresh_versions()
        self._refresh_profiles()

    def _load_last_launch(self) -> dict | None:
        return load_last_launch(self.context.username)

    def _save_last_launch(self, version: str, profile: str) -> None:
        record = {
            "game": paths.PROVIDER_MINECRAFT,
            "version": version,
            "profile": profile,
        }
        try:
            save_last_launch(self.context.username, record)
        except OSError:
            pass
        self._last_launch = record

    def _selected(self, combo: Gtk.DropDown) -> str | None:
        model = combo.get_model()
        idx = combo.get_selected()
        if model is None or idx == Gtk.INVALID_LIST_POSITION:
            return None
        item = model.get_item(idx)
        return item.get_string() if item else None

    def _refresh_versions(self) -> None:
        installed = self._provider.list_installed()
        items = installed or ["(none installed)"]
        self.version_combo.set_model(Gtk.StringList.new(items))
        wanted = (self._last_launch or {}).get("version")
        if wanted and wanted in installed:
            self.version_combo.set_selected(installed.index(wanted))
        self.launch_button.set_sensitive(bool(installed))
        self.delete_version_button.set_sensitive(bool(installed))

    def _refresh_profiles(self) -> None:
        on_disk = self._provider.list_profiles(self.context.username)
        items = on_disk or [DEFAULT_PROFILE]
        self.profile_combo.set_model(Gtk.StringList.new(items))
        wanted = (self._last_launch or {}).get("profile")
        if wanted and wanted in items:
            self.profile_combo.set_selected(items.index(wanted))
        self.delete_profile_button.set_sensitive(bool(on_disk))

    def _set_status(self, message: str, *, log: bool = True) -> None:
        self.status.set_label(message)
        if log and message:
            self._append_log(message)

    def _append_log(self, message: str) -> None:
        buf = self.log_view.get_buffer()
        if buf.get_char_count() > 0:
            buf.insert(buf.get_end_iter(), "\n")
        buf.insert(buf.get_end_iter(), message)
        self.log_view.scroll_to_iter(buf.get_end_iter(), 0.0, False, 0.0, 0.0)

    def _clear_log(self) -> None:
        self.log_view.get_buffer().set_text("")

    def _on_install_clicked(self, *_args) -> None:
        self.install_button.set_sensitive(False)
        self._set_status("Looking up Minecraft versions…")

        def fetch():
            return self._provider.release_choices()

        def done(choices):
            self.install_button.set_sensitive(True)
            self.status.set_label("")
            self._show_install_dialog(choices)

        def failed(exc):
            self.install_button.set_sensitive(True)
            self._set_status(f"Lookup failed: {exc}")

        worker.run(fetch, on_done=done, on_error=failed)

    def _show_install_dialog(self, choices) -> None:
        dialog = Gtk.Window(title="Install Minecraft", transient_for=self.get_root(), modal=True)
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=8,
            margin_top=16, margin_bottom=16, margin_start=16, margin_end=16,
        )

        radio_head = None
        radios = []
        for choice in choices:
            btn = Gtk.CheckButton.new_with_label(choice.label)
            if radio_head is None:
                radio_head = btn
                btn.set_active(True)
            else:
                btn.set_group(radio_head)
            radios.append((btn, choice.version))
            box.append(btn)

        custom_btn = Gtk.CheckButton.new_with_label("Specific version:")
        if radio_head is not None:
            custom_btn.set_group(radio_head)
        else:
            custom_btn.set_active(True)
        box.append(custom_btn)

        entry = Gtk.Entry(placeholder_text="e.g. 1.20.6")
        entry.set_margin_start(24)
        entry.connect("changed", lambda *_: custom_btn.set_active(True))
        box.append(entry)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: dialog.close())
        actions.append(cancel)
        install = Gtk.Button(label="Install")
        install.add_css_class("suggested-action")
        actions.append(install)
        box.append(actions)

        def on_install(*_args) -> None:
            for btn, version in radios:
                if btn.get_active():
                    dialog.close()
                    self._do_install(version)
                    return
            version = entry.get_text().strip()
            if version:
                dialog.close()
                self._do_install(version)

        install.connect("clicked", on_install)
        entry.connect("activate", on_install)
        dialog.set_child(box)
        dialog.present()

    def _do_install(self, version: str) -> None:
        self._clear_log()
        self._set_status(f"Installing Minecraft {version}…")
        self.progress.set_visible(True)
        self.progress.set_fraction(0.0)
        self.progress.set_text("")
        self.install_button.set_sensitive(False)
        self.launch_button.set_sensitive(False)

        stats = ProgressStats()

        def push():
            self.progress.set_fraction(stats.fraction)
            self.progress.set_text(stats.label())
            return False

        def cb(done, total):
            stats.update(done, total)
            GLib.idle_add(push)

        def set_status(message: str):
            GLib.idle_add(self._set_status, message)

        def install():
            return self._provider.install(
                self.context.username,
                version,
                progress=cb,
                status=set_status,
            )

        def done(_result):
            self.progress.set_visible(False)
            self.install_button.set_sensitive(True)
            self._set_status(f"Minecraft {version} installed.")
            self._refresh_versions()
            self._refresh_profiles()

        def failed(exc):
            self.progress.set_visible(False)
            self.install_button.set_sensitive(True)
            self.launch_button.set_sensitive(bool(self._provider.list_installed()))
            self._set_status(f"Install failed: {exc}")

        worker.run(install, on_done=done, on_error=failed)

    def _on_new_profile(self, *_args) -> None:
        dialog = Gtk.Window(title="New profile", transient_for=self.get_root(), modal=True)
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=8,
            margin_top=16, margin_bottom=16, margin_start=16, margin_end=16,
        )
        box.append(Gtk.Label(label="Create a new Minecraft profile", xalign=0))
        entry = Gtk.Entry(placeholder_text="Profile name")
        box.append(entry)
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: dialog.close())
        actions.append(cancel)
        create = Gtk.Button(label="Create")
        create.add_css_class("suggested-action")
        actions.append(create)
        box.append(actions)

        def go(*_args):
            name = entry.get_text().strip()
            if not name:
                return
            dialog.close()
            try:
                self._provider.ensure_profile(self.context.username, name)
                self._set_status(f"Created profile “{name}”.")
                self._refresh_profiles()
                profiles = self._provider.list_profiles(self.context.username)
                if name in profiles:
                    self.profile_combo.set_selected(profiles.index(name))
            except OSError as exc:
                self._set_status(f"Create failed: {exc}")

        create.connect("clicked", go)
        entry.connect("activate", go)
        dialog.set_child(box)
        dialog.present()

    def _on_delete_profile(self, *_args) -> None:
        profile = self._selected(self.profile_combo)
        if not profile:
            return
        dialog = Gtk.Window(title="Delete profile", transient_for=self.get_root(), modal=True)
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=12,
            margin_top=16, margin_bottom=16, margin_start=16, margin_end=16,
        )
        box.append(Gtk.Label(
            label=f"Delete the “{profile}” Minecraft profile?\n\nThis removes that profile's worlds, settings, and local state.",
            wrap=True,
            xalign=0,
        ))
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: dialog.close())
        actions.append(cancel)
        confirm = Gtk.Button(label="Delete")
        confirm.add_css_class("destructive-action")

        def go(*_args):
            dialog.close()
            try:
                self._provider.delete_profile(self.context.username, profile)
                self._set_status(f"Deleted profile “{profile}”.")
                self._refresh_profiles()
            except OSError as exc:
                self._set_status(f"Delete failed: {exc}")

        confirm.connect("clicked", go)
        actions.append(confirm)
        box.append(actions)
        dialog.set_child(box)
        dialog.present()

    def _on_delete_version(self, *_args) -> None:
        version = self._selected(self.version_combo)
        if not version or version == "(none installed)":
            return
        dialog = Gtk.Window(title="Delete version", transient_for=self.get_root(), modal=True)
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=12,
            margin_top=16, margin_bottom=16, margin_start=16, margin_end=16,
        )
        box.append(Gtk.Label(
            label=f"Remove Minecraft {version}?\n\nProfiles and worlds are kept; only the installed game files are deleted.",
            wrap=True,
            xalign=0,
        ))
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: dialog.close())
        actions.append(cancel)
        confirm = Gtk.Button(label="Delete")
        confirm.add_css_class("destructive-action")

        def go(*_args):
            dialog.close()
            try:
                self._provider.delete_version(version)
                self._set_status(f"Deleted Minecraft {version}.")
                self._refresh_versions()
            except OSError as exc:
                self._set_status(f"Delete failed: {exc}")

        confirm.connect("clicked", go)
        actions.append(confirm)
        box.append(actions)
        dialog.set_child(box)
        dialog.present()

    def _on_launch(self, *_args) -> None:
        version = self._selected(self.version_combo)
        profile = self._selected(self.profile_combo) or DEFAULT_PROFILE
        if not version or version == "(none installed)":
            return
        self._provider.ensure_profile(self.context.username, profile)
        self._save_last_launch(version, profile)
        self.launch_button.set_sensitive(False)
        self._clear_log()
        self._set_status("Launching Minecraft…")

        selection = LaunchSelection(
            provider=paths.PROVIDER_MINECRAFT,
            username=self.context.username,
            version=version,
            profile=profile,
        )

        def do_launch():
            proc = self._provider.launch(selection)
            return proc.wait()

        def done(rc):
            self.launch_button.set_sensitive(True)
            self._set_status(f"Minecraft exited (status {rc}).")
            self._refresh_versions()
            self._refresh_profiles()

        def failed(exc):
            self.launch_button.set_sensitive(True)
            self._set_status(f"Launch failed: {exc}")

        worker.run(do_launch, on_done=done, on_error=failed)
