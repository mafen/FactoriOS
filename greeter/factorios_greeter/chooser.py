"""Provider-aware chooser for installed games and profiles."""

from __future__ import annotations

import json
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from factorios_launcher import LaunchSelection, get_provider, paths
from factorios_launcher.download import ProgressStats, parse_version
from factorios_launcher.providers import all_providers

from . import power, updates, worker
from .context import UserContext


class ChooserScreen(Gtk.Box):
    def __init__(self, context: UserContext, on_switch_user: Callable[[], None]) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_margin_top(40)
        self.set_margin_bottom(40)
        self.set_margin_start(80)
        self.set_margin_end(80)
        self.context = context
        self._on_switch_user = on_switch_user
        self._last_launch = self._load_last_launch()
        self._release_cache: dict[tuple[str, str | None], list] = {}

        self._provider_ids = [
            provider.id
            for provider in all_providers()
            if not provider.requires_auth or context.has_factorio_auth
        ]
        remembered_provider = (self._last_launch or {}).get("provider")
        if remembered_provider in self._provider_ids:
            self._provider_id = remembered_provider
        elif context.has_factorio_auth:
            self._provider_id = paths.PROVIDER_FACTORIO
        else:
            self._provider_id = paths.PROVIDER_MINECRAFT
        self._provider = get_provider(self._provider_id)

        remembered_variant = (self._last_launch or {}).get("variant")
        self._variant = self._default_variant()
        if remembered_variant in self._provider.available_variants(self.context.factorio_session):
            self._variant = remembered_variant

        title = Gtk.Label(label="FactoriOS")
        title.add_css_class("title-1")
        self.append(title)

        subtitle = Gtk.Label(label=self._subtitle(), xalign=0)
        subtitle.add_css_class("dim-label")
        self.header_label = subtitle
        self.append(subtitle)

        self.provider_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.provider_row.append(Gtk.Label(label="Game", xalign=0))
        self.provider_combo = Gtk.DropDown.new_from_strings([get_provider(pid).name for pid in self._provider_ids])
        self.provider_combo.set_selected(self._provider_ids.index(self._provider_id))
        self.provider_combo.connect("notify::selected", self._on_provider_changed)
        self.provider_row.append(self.provider_combo)
        self.provider_row.set_visible(len(self._provider_ids) > 1)
        self.append(self.provider_row)

        self.variant_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.variant_label = Gtk.Label(label="Build", xalign=0)
        self.variant_row.append(self.variant_label)
        self.variant_combo = Gtk.DropDown.new_from_strings([])
        self.variant_combo.connect("notify::selected", self._on_variant_changed)
        self.variant_row.append(self.variant_combo)
        self.append(self.variant_row)

        self.append(Gtk.Label(label="Version", xalign=0))
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
        self.append(version_row)

        self.update_hint = Gtk.Label(label="", xalign=0)
        self.update_hint.add_css_class("dim-label")
        self.update_hint.set_visible(False)
        self.append(self.update_hint)

        self.append(Gtk.Label(label="Profile", xalign=0))
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
        self.append(profile_row)

        self.status = Gtk.Label(label="", xalign=0)
        self.status.add_css_class("dim-label")
        self.append(self.status)

        self.progress = Gtk.ProgressBar()
        self.progress.set_show_text(True)
        self.progress.set_visible(False)
        self.append(self.progress)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.END)
        self.mimalloc_check = Gtk.CheckButton.new_with_label("Use mimalloc (Factorio only)")
        remembered_mimalloc = (self._last_launch or {}).get("use_mimalloc", True)
        self.mimalloc_check.set_active(bool(remembered_mimalloc))
        actions.append(self.mimalloc_check)
        switch = Gtk.Button(label="Switch user")
        switch.connect("clicked", lambda *_: self._on_switch_user())
        actions.append(switch)
        self.launch_button = Gtk.Button(label="Launch")
        self.launch_button.add_css_class("suggested-action")
        self.launch_button.connect("clicked", self._on_launch)
        actions.append(self.launch_button)
        self.append(actions)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.forget_button = Gtk.Button(label="Forget me")
        self.forget_button.add_css_class("flat")
        self.forget_button.connect("clicked", self._on_forget_me)
        footer.append(self.forget_button)
        updates_btn = Gtk.Button(label="Updates…")
        updates_btn.add_css_class("flat")
        updates_btn.connect("clicked", lambda *_: updates.show_dialog(self))
        footer.append(updates_btn)
        footer.append(Gtk.Box(hexpand=True))
        footer.append(power.make_row())
        self.append(footer)

        self._refresh_all()

    def _subtitle(self) -> str:
        if self.context.has_factorio_auth:
            return f"Signed in as {self.context.username}"
        return "Local Minecraft profile"

    def _remembered(self, key: str):
        if not self._last_launch:
            return None
        if self._last_launch.get("provider") != self._provider_id:
            return None
        if self._last_launch.get("variant") != self._variant:
            return None
        return self._last_launch.get(key)

    def _load_last_launch(self) -> dict | None:
        path = paths.user_last_launch(self.context.username)
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _save_last_launch(self, version: str, profile: str) -> None:
        record = {
            "provider": self._provider_id,
            "variant": self._variant,
            "version": version,
            "profile": profile,
            "use_mimalloc": self.mimalloc_check.get_active(),
        }
        path = paths.user_last_launch(self.context.username)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record))
        except OSError:
            pass
        self._last_launch = record

    def _default_variant(self) -> str | None:
        return self._provider.default_variant(self.context.factorio_session)

    def _selected(self, combo: Gtk.DropDown) -> str | None:
        model = combo.get_model()
        idx = combo.get_selected()
        if model is None or idx == Gtk.INVALID_LIST_POSITION:
            return None
        item = model.get_item(idx)
        return item.get_string() if item else None

    def _set_provider(self, provider_id: str) -> None:
        self._provider_id = provider_id
        self._provider = get_provider(provider_id)
        remembered_variant = (self._last_launch or {}).get("variant")
        variants = self._provider.available_variants(self.context.factorio_session)
        if remembered_variant in variants:
            self._variant = remembered_variant
        else:
            self._variant = self._provider.default_variant(self.context.factorio_session)

    def _refresh_variants(self) -> None:
        variants = self._provider.available_variants(self.context.factorio_session)
        self.variant_label.set_label(self._provider.variant_label or "Variant")
        self.variant_row.set_visible(bool(variants))
        if not variants:
            self.variant_combo.set_model(Gtk.StringList.new([]))
            return
        labels = [self._provider.display_variant(v) for v in variants]
        self.variant_combo.set_model(Gtk.StringList.new(labels))
        if self._variant in variants:
            self.variant_combo.set_selected(variants.index(self._variant))
        else:
            self._variant = variants[0]
            self.variant_combo.set_selected(0)

    def _refresh_versions(self) -> None:
        installed = self._provider.list_installed(self._variant)
        items = installed or ["(none installed)"]
        self.version_combo.set_model(Gtk.StringList.new(items))
        remembered = self._remembered("version")
        if remembered and remembered in installed:
            self.version_combo.set_selected(installed.index(remembered))
        self.launch_button.set_sensitive(bool(installed))
        self.delete_version_button.set_sensitive(bool(installed))

    def _refresh_profiles(self) -> None:
        on_disk = self._provider.list_profiles(self.context.username, self._variant)
        default_profile = "default"
        items = on_disk or [default_profile]
        self.profile_combo.set_model(Gtk.StringList.new(items))
        remembered = self._remembered("profile")
        if remembered and remembered in items:
            self.profile_combo.set_selected(items.index(remembered))
        self.delete_profile_button.set_sensitive(bool(on_disk))

    def _refresh_update_hint(self) -> None:
        if self._provider_id != paths.PROVIDER_FACTORIO:
            self.update_hint.set_visible(False)
            return
        key = (self._provider_id, self._variant)
        cached = self._release_cache.get(key)
        installed = self._provider.list_installed(self._variant)

        def render(choices):
            if not choices:
                self.update_hint.set_visible(False)
                return
            newest = max(installed, key=parse_version, default=None)
            latest = choices[0].version
            if newest and parse_version(latest) <= parse_version(newest):
                self.update_hint.set_visible(False)
                return
            label = choices[0].label if not newest else f"Update available: {latest} (you have {newest})"
            self.update_hint.set_label(label)
            self.update_hint.set_visible(True)

        if cached is not None:
            render(cached)
            return

        self.update_hint.set_visible(False)

        def fetch():
            return self._provider.release_choices(self.context.factorio_session, self._variant)

        def done(choices):
            self._release_cache[key] = choices
            if self._provider_id == paths.PROVIDER_FACTORIO:
                render(choices)

        worker.run(fetch, on_done=done, on_error=lambda _exc: None)

    def _refresh_all(self) -> None:
        self.header_label.set_label(self._subtitle())
        self.forget_button.set_visible(self.context.has_factorio_auth)
        self.mimalloc_check.set_sensitive(self._provider_id == paths.PROVIDER_FACTORIO)
        self._refresh_variants()
        self._refresh_versions()
        self._refresh_profiles()
        self._refresh_update_hint()

    def _on_provider_changed(self, *_args) -> None:
        idx = self.provider_combo.get_selected()
        if idx == Gtk.INVALID_LIST_POSITION:
            return
        self._set_provider(self._provider_ids[idx])
        self.status.set_label("")
        self._refresh_all()

    def _on_variant_changed(self, *_args) -> None:
        variants = self._provider.available_variants(self.context.factorio_session)
        idx = self.variant_combo.get_selected()
        if not variants or idx == Gtk.INVALID_LIST_POSITION or idx >= len(variants):
            return
        self._variant = variants[idx]
        self.status.set_label("")
        self._refresh_versions()
        self._refresh_profiles()
        self._refresh_update_hint()

    def _on_install_clicked(self, *_args) -> None:
        self.install_button.set_sensitive(False)
        self.status.set_label(f"Looking up {self._provider.name} releases…")

        def fetch():
            return self._provider.release_choices(self.context.factorio_session, self._variant)

        def done(choices):
            self.install_button.set_sensitive(True)
            self.status.set_label("")
            self._show_install_dialog(choices)

        def failed(exc):
            self.install_button.set_sensitive(True)
            self.status.set_label(f"Lookup failed: {exc}")

        worker.run(fetch, on_done=done, on_error=failed)

    def _show_install_dialog(self, choices) -> None:
        dialog = Gtk.Window(title=f"Install {self._provider.name}", transient_for=self.get_root(), modal=True)
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
        self.status.set_label(f"Installing {self._provider.name} {version}…")
        self.progress.set_visible(True)
        self.progress.set_fraction(0.0)
        self.progress.set_text("")
        self.install_button.set_sensitive(False)

        stats = ProgressStats()

        def push():
            self.progress.set_fraction(stats.fraction)
            self.progress.set_text(stats.label())
            return False

        def cb(done, total):
            stats.update(done, total)
            GLib.idle_add(push)

        def install():
            return self._provider.install(
                self.context.username,
                version,
                session=self.context.factorio_session,
                variant=self._variant,
                progress=cb,
            )

        def done(_result):
            self.progress.set_visible(False)
            self.install_button.set_sensitive(True)
            self.status.set_label(f"Installed {self._provider.name} {version}.")
            self._release_cache.pop((self._provider_id, self._variant), None)
            self._refresh_versions()
            self._refresh_profiles()
            self._refresh_update_hint()

        def failed(exc):
            self.progress.set_visible(False)
            self.install_button.set_sensitive(True)
            self.status.set_label(f"Install failed: {exc}")

        worker.run(install, on_done=done, on_error=failed)

    def _on_new_profile(self, *_args) -> None:
        dialog = Gtk.Window(title="New profile", transient_for=self.get_root(), modal=True)
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=8,
            margin_top=16, margin_bottom=16, margin_start=16, margin_end=16,
        )
        box.append(Gtk.Label(label=f"Create a new {self._provider.name} profile", xalign=0))
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
                self._provider.ensure_profile(self.context.username, name, self._variant)
                self.status.set_label(f"Created profile “{name}”.")
                self._refresh_profiles()
            except OSError as exc:
                self.status.set_label(f"Create failed: {exc}")

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
            label=f"Delete the “{profile}” {self._provider.name} profile?\n\nThis removes that profile's saves, settings, and local state.",
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
                self._provider.delete_profile(self.context.username, profile, self._variant)
                self.status.set_label(f"Deleted profile “{profile}”.")
                self._refresh_profiles()
            except OSError as exc:
                self.status.set_label(f"Delete failed: {exc}")

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
            label=f"Remove {self._provider.name} {version}?\n\nProfiles are kept; only the installed game files are deleted.",
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
                self._provider.delete_version(version, self._variant)
                self.status.set_label(f"Deleted {self._provider.name} {version}.")
                self._refresh_versions()
            except OSError as exc:
                self.status.set_label(f"Delete failed: {exc}")

        confirm.connect("clicked", go)
        actions.append(confirm)
        box.append(actions)
        dialog.set_child(box)
        dialog.present()

    def _on_forget_me(self, *_args) -> None:
        if not self.context.has_factorio_auth:
            return
        dialog = Gtk.Window(title="Forget me", transient_for=self.get_root(), modal=True)
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=12,
            margin_top=16, margin_bottom=16, margin_start=16, margin_end=16,
        )
        box.append(Gtk.Label(
            label=(
                f"Forget {self.context.username}?\n\n"
                "The cached factorio.com session is deleted and Remember Me is cleared."
            ),
            wrap=True,
            xalign=0,
        ))
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda *_: dialog.close())
        actions.append(cancel)
        confirm = Gtk.Button(label="Forget me")
        confirm.add_css_class("destructive-action")

        def go(*_args):
            dialog.close()
            sess_path = paths.user_session(self.context.username)
            if sess_path.exists():
                sess_path.unlink(missing_ok=True)
            if paths.LAST_USER.exists():
                try:
                    if paths.LAST_USER.read_text().strip() == self.context.username:
                        paths.LAST_USER.unlink()
                except OSError:
                    pass
            self._on_switch_user()

        confirm.connect("clicked", go)
        actions.append(confirm)
        box.append(actions)
        dialog.set_child(box)
        dialog.present()

    def _on_launch(self, *_args) -> None:
        version = self._selected(self.version_combo)
        profile = self._selected(self.profile_combo) or "default"
        if not version or version == "(none installed)":
            return
        self._provider.ensure_profile(self.context.username, profile, self._variant)
        self._save_last_launch(version, profile)
        self.launch_button.set_sensitive(False)
        self.status.set_label(f"Launching {self._provider.name}…")

        selection = LaunchSelection(
            provider=self._provider_id,
            username=self.context.username,
            version=version,
            profile=profile,
            variant=self._variant,
            use_mimalloc=self.mimalloc_check.get_active(),
        )

        def do_launch():
            proc = self._provider.launch(selection, session=self.context.factorio_session)
            return proc.wait()

        def done(rc):
            self.launch_button.set_sensitive(True)
            self.status.set_label(f"{self._provider.name} exited (status {rc}).")
            self._refresh_versions()
            self._refresh_profiles()
            self._refresh_update_hint()

        def failed(exc):
            self.launch_button.set_sensitive(True)
            self.status.set_label(f"Launch failed: {exc}")

        worker.run(do_launch, on_done=done, on_error=failed)
