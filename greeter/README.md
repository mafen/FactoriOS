# factorios-greeter

GTK4 application that *is* the entire user-facing surface of an installed
FactoriOS system. labwc execs this; nothing else runs.

## Screens

- **Chooser** — direct-boot Minecraft screen with version dropdown, profile dropdown, *Install…*, *New profile…*, and *Launch*. *Launch* spawns the selected game and waits — when it exits, we return to the chooser.

## Threading

GTK is single-threaded. Anything that hits the network or the disk goes through `worker.run()`, which runs the callable on a daemon thread and posts the result back to the main loop via `GLib.idle_add`.

## Run in dev

Outside the kiosk you won't have `/var/lib/factorios/` writable — the greeter silently skips the Remember Me writes, so it still works on a normal desktop:

```
PYTHONPATH=launcher:greeter python -m factorios_greeter
```

Requires `python-gobject`, `gtk4`, `python-requests`.
