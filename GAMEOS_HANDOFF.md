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
