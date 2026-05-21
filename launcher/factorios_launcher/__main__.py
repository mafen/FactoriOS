"""Tiny CLI for poking at the launcher without going through the greeter."""

from __future__ import annotations

import argparse
import getpass
import json
import sys

from . import paths, versions
from .auth import AuthError, Session
from .providers import all_providers, get_provider


def main() -> int:
    p = argparse.ArgumentParser(prog="factorios-launcher")
    sub = p.add_subparsers(dest="cmd", required=True)

    releases = sub.add_parser("releases", help="Print release choices for a provider")
    releases.add_argument("provider", choices=[p.id for p in all_providers()], nargs="?", default=paths.PROVIDER_FACTORIO)

    login = sub.add_parser("login", help="Login and cache the session")
    login.add_argument("username")

    install = sub.add_parser("install", help="Download and install a version")
    install.add_argument("provider", choices=[p.id for p in all_providers()])
    install.add_argument("username")
    install.add_argument("version", help="e.g. 1.1.110 or latest")
    install.add_argument(
        "variant",
        nargs="?",
        default=None,
        help="provider-specific variant (Factorio build, etc.)",
    )

    list_cmd = sub.add_parser("list", help="List installed versions")
    list_cmd.add_argument("provider", choices=[p.id for p in all_providers()], nargs="?", default=paths.PROVIDER_FACTORIO)
    sub.add_parser("demo", help="Download the Factorio demo (no auth needed)")

    args = p.parse_args()

    if args.cmd == "releases":
        provider = get_provider(args.provider)
        print(json.dumps([choice.__dict__ for choice in provider.release_choices(Session())], indent=2))
        return 0

    if args.cmd == "list":
        provider = get_provider(args.provider)
        if args.provider == paths.PROVIDER_FACTORIO:
            for v, b in versions.list_installed():
                print(f"{v}\t{b}")
        else:
            for version in provider.list_installed():
                print(version)
        return 0

    if args.cmd == "login":
        s = Session()
        try:
            s.login(args.username, getpass.getpass("factorio.com password: "))
        except AuthError as e:
            print(f"login failed: {e}", file=sys.stderr)
            return 1
        s.save(paths.user_session(args.username))
        print(f"session saved to {paths.user_session(args.username)}")
        return 0

    if args.cmd == "demo":
        def progress(done, total):
            pct = (done / total * 100) if total else 0
            print(f"\r{done/1e6:.1f} / {total/1e6:.1f} MB ({pct:.0f}%)", end="", flush=True)
        versions.install_demo(progress=progress)
        print()
        return 0

    if args.cmd == "install":
        provider = get_provider(args.provider)
        s = None
        if provider.requires_auth:
            sess_path = paths.user_session(args.username)
            if not sess_path.exists():
                print(f"no cached session for {args.username}; run `login` first", file=sys.stderr)
                return 1
            s = Session.load(sess_path)

        def progress(done, total):
            pct = (done / total * 100) if total else 0
            print(f"\r{done/1e6:.1f} / {total/1e6:.1f} MB ({pct:.0f}%)", end="", flush=True)
        provider.install(args.username, args.version, session=s, variant=args.variant, progress=progress)
        print()
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
