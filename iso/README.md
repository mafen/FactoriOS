# archiso profile

Builds the GameOS installer ISO.

The top-level `./build.sh`:

1. builds the `gameos-*` packages
2. stages them into `iso/airootfs/var/cache/gameos-repo/`
3. runs `iso/build.sh`

The live environment exposes that local repo as `[gameos]` so the installer can
`pacstrap` the appliance packages into the target system.
