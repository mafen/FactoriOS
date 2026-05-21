# GAMEOS_HANDOFF.md

Quick branch-specific notes for `gameos-neutral-core`.

## What This Branch Is

- Product surface: Minecraft-only appliance
- Internal architecture: still provider-based / game-independent
- Canonical names:
  - packages: `gameos-launcher`, `gameos-greeter`, `gameos-base`
  - service: `gameos.service`
  - data root: `/var/lib/gameos`
- Compatibility shims still exist for some old `factorios-*` names

## Important Branches

- `gameos-neutral-core`: current GameOS branch
- `minecraft-only`: earlier Minecraft-only branch before more neutral renaming
- `shared-platform-wip`: earlier shared-provider snapshot

## Most Important Files

- `launcher/factorios_launcher/providers/minecraft.py`
  Minecraft install/launch logic, inherited manifest merge, runtime fallback
- `greeter/factorios_greeter/chooser.py`
  Main Minecraft appliance UI, progress/log panel, profile/version actions
- `installer/install.sh`
  Arch install flow, keyring refresh before `pacstrap`
- `.github/workflows/build-iso.yml`
  Build + repo publish + installer smoke test
- `systemd/factorios.service`
  Canonical installed unit becomes `gameos.service` via packaging

## Recent Fixes You’ll Want To Remember

- Keyring fix:
  - live ISO now includes `archlinux-keyring`
  - live shell refreshes it before launching installer
  - installer refreshes it again before `pacstrap`
  - reason: fixed `unknown trust` / `PGP signature` pacstrap failures

- Java runtime fallback:
  - if Mojang asks for a missing runtime feed like `java-runtime-delta`,
    installer falls back to a known feed such as `java-runtime-gamma`
  - covered by unit test in `tests/test_minecraft_provider.py`

- Chooser/log UI:
  - bigger scrolling log panel exists now
  - chooser content is centered in a fixed-width card
  - status text wraps instead of running off-screen

- Kiosk shell:
  - labwc root right-click menu is explicitly suppressed in
    `systemd/factorios-labwc-rc.xml`

## How To Smoke Test Locally

```bash
python -m compileall launcher greeter tests
PYTHONPATH=launcher python -m unittest discover -s tests -v
```

For a full ISO build:

```bash
./build.sh
```

## Current CI Shape

- ISO build job
- staged pacman repo artifact upload
- installer smoke job that:
  - refreshes `archlinux-keyring`
  - reinitializes pacman keyring
  - runs a real `pacstrap` against the staged `[gameos]` repo

This does **not** boot the ISO graphically or prove Minecraft launches.

## Known Gaps / Good Next Steps

- Add a CI stage for a real Minecraft provider install against Mojang endpoints
  on `workflow_dispatch` or nightly
- Consider updating `CLAUDE.md` to match GameOS reality, or replace it with a
  neutral version
- There are still source directory names like `packages/factorios-*` and
  `systemd/factorios-*`; package output names are already neutral
- The UI titlebar / card layout were fixed, but real VM validation is still
  worth doing after bigger UI changes

## NixOS Ideas

If you revisit the base distro choice later, these are the most promising
GameOS-shaped NixOS directions:

- Replace the Arch installer + pacstrap path with a NixOS image build
  approach:
  use `nixos-generators` or a custom ISO config to produce the live/install
  image declaratively instead of assembling packages + local pacman repo.

- Model the kiosk session as a NixOS module:
  one module for the `gameos` user, `labwc`, seat permissions, `gameos.service`,
  tmpfiles, and the greeter package. That would make the whole appliance
  reproducible from one config tree.

- Package the launcher/greeter as Nix derivations:
  either simple Python application derivations or a flake output that builds
  `gameos-launcher`, `gameos-greeter`, and the system package set together.

- Keep Minecraft mutable data outside the Nix store:
  `/var/lib/gameos` still makes sense on NixOS because downloaded runtimes,
  assets, worlds, and provider state are mutable and should not live in the
  store.

- Let NixOS own the system Java fallback story if desired:
  even if Mojang-managed runtime download remains the default, NixOS would make
  it easy to expose a declarative fallback JRE/JDK package for debugging or
  emergency recovery.

- Convert the current systemd/tmfiles/sysusers glue into NixOS options:
  the current `systemd/` files are already close to what a NixOS module would
  express, which makes this one of the easier parts to migrate.

- Start with a dev or VM target first, not a full migration:
  the safest path would be to create a NixOS VM target that boots directly into
  the existing greeter, prove the session model works, and only then consider
  replacing the Arch ISO/install flow fully.

## If Something Breaks

- Installer/package trust issue:
  check `iso/packages.x86_64`, `iso/airootfs/root/.bash_profile`,
  and `installer/install.sh`
- Minecraft runtime issue:
  check `_install_runtime()` and `_resolve_runtime_component()` in
  `launcher/factorios_launcher/providers/minecraft.py`
- Weird kiosk escape/menu behavior:
  check `systemd/factorios-labwc-rc.xml`
- Stretched or clipped UI:
  check `greeter/factorios_greeter/app.py` and `chooser.py`
