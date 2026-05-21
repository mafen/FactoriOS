# factorios-launcher

Pure-Python library + small CLI for FactoriOS' game providers. In this
appliance configuration the Minecraft provider is the only one enabled by
default. No UI, no GTK.

The greeter depends on this; future tooling (headless server provisioning, scripted reinstalls, etc.) should too.

## Modules

- `auth` — CSRF-scraped form login against `factorio.com/login`, session serialization for Remember Me.
- `download` — authenticated binary download, `latest-releases` API.
- `versions` — install/list/remove versions under `/var/lib/factorios/versions/`.
- `profiles` — per-user profile directories, `launch()` to spawn Factorio with `--write-data` pointed at a profile.
- `paths` — the single source of truth for on-disk layout. Don't hard-code paths elsewhere.
- `providers/` — provider registry plus `factorio` and `minecraft` adapters used by the greeter.

## CLI

```bash
factorios-launcher releases factorio
factorios-launcher releases minecraft
factorios-launcher login <username>
factorios-launcher install factorio <user> <version> space-age
factorios-launcher install minecraft _local 1.20.6
factorios-launcher list minecraft
```

In development without install:

```
PYTHONPATH=launcher python -m factorios_launcher releases
```

## Tests

None yet. The login flow needs real factorio.com credentials to exercise end-to-end.
