# GameOS

A joke Linux distribution whose only purpose is booting straight into a game.

This branch is Minecraft-first at the product surface, but the internals are
provider-based so the launcher/greeter core stays game-independent.

## Status

Working pieces:

- `gameos-launcher` — shared provider core plus a vanilla Minecraft provider
  with local profiles, managed Java runtime downloads, and Mojang manifest
  installs.
- `gameos-greeter` — direct-boot Minecraft chooser for install, profile
  management, launch, power actions, and package updates.
- `gameos-base` — systemd/labwc kiosk session, tmpfiles/sysusers, and package
  glue.
- `installer/` and `iso/` — Arch-based installer ISO and unattended kiosk boot.

## Canonical Runtime Layout

```text
/var/lib/gameos/
  providers/minecraft/
    versions/<version>/
    assets/
    libraries/
    runtimes/
  users/_local/minecraft/profiles/<profile>/
    instance.json
    saves/
    resourcepacks/
    shaderpacks/
```

`/var/lib/factorios` is treated as a legacy fallback for a small amount of
read-only compatibility. New writes go to `/var/lib/gameos`.

## Build

```bash
./build.sh
./build.sh full
```

The top-level build script builds the PKGBUILDs, stages them into the local
`[gameos]` repo inside the ISO airootfs, then runs `iso/build.sh`.
