# gameos-greeter

GTK4 kiosk application for GameOS.

This branch boots directly into the Minecraft chooser. The active UI surface is
single-provider even though the backend stays provider-based.

## Screens

- **Chooser** — Minecraft version dropdown, profile dropdown, install flow,
  profile creation/deletion, launch, updates, and power controls.

## Notes

- Installs run in a worker thread and feed back both stage messages and byte
  progress.
- The chooser remembers the last launched Minecraft version/profile for the
  local appliance user.
