# gameos-launcher

Pure-Python launcher library for GameOS.

Current branch behavior:

- canonical distribution / CLI: `gameos-launcher`
- legacy CLI kept: `factorios-launcher`
- canonical storage root: `/var/lib/gameos`
- only the Minecraft provider is enabled by default

## Provider Scope

- `providers/minecraft.py` handles Mojang manifest lookup, inherited version
  resolution, asset/library/runtime download, local profile metadata, and
  launch construction.
- `providers/` remains the long-term provider abstraction even though this
  branch exposes only Minecraft in the product UI.

## CLI

```bash
gameos-launcher releases minecraft
gameos-launcher list minecraft
gameos-launcher install minecraft _local 1.20.6
```
