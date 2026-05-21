# Run on every bash login. agetty autologs root on tty1 (see
# autologin.conf), so this is what greets the user and kicks off the
# installer. On other ttys we leave the user with a normal shell.
if [[ "$(tty)" == "/dev/tty1" ]]; then
    cat <<'BANNER'

 ┌─────────────────────────────────────────────────┐
 │  Welcome to the GameOS installer.               │
 │                                                 │
 │  This will wipe a disk and install GameOS.      │
 │  Bring up the network with `nmtui` if needed,   │
 │  then re-run `gameos-install` if it bails.      │
 └─────────────────────────────────────────────────┘

BANNER
    # Initialize the pacman keyring if mkarchiso didn't pre-seed one for us
    # (otherwise the installer's pacstrap fails with "keyring is not
    # writable" because pacman tries and fails to import keys on demand).
    if [[ ! -s /etc/pacman.d/gnupg/pubring.gpg ]]; then
        echo "Initializing pacman keyring (one-off, ~10s)…"
        pacman-key --init >/dev/null 2>&1
        pacman-key --populate archlinux >/dev/null 2>&1
        echo
    fi

    if ping -c1 -W2 archlinux.org >/dev/null 2>&1; then
        /usr/local/bin/gameos-install
    else
        echo "No network detected — bring it up with 'nmtui', then run:"
        echo "    gameos-install"
        echo
    fi
fi
