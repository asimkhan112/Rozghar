"""Operational commands.

`bootstrap-admin` exists because there is no public registration endpoint and
never will be. The first super admin has to come from somewhere, and a command
run by whoever controls the server is the right somewhere.

    python -m app.cli bootstrap-admin --email you@rozgar.pk --name "Your Name"
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import secrets
import string
import sys

from sqlalchemy import select

from app.core.permissions import SystemRole
from app.core.security import hash_password
from app.db.database import SessionFactory, dispose_engine
from app.models.admin import Admin
from app.models.rbac import Role

MIN_PASSWORD_LENGTH = 12


def _generate_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_"
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def bootstrap_admin(email: str, full_name: str, password: str | None) -> int:
    generated = password is None
    if generated:
        password = _generate_password()
    elif len(password) < MIN_PASSWORD_LENGTH:
        print(f"error: password must be at least {MIN_PASSWORD_LENGTH} characters", file=sys.stderr)
        return 2

    async with SessionFactory() as session:
        existing = (
            await session.execute(select(Admin).where(Admin.email == email))
        ).scalar_one_or_none()
        if existing is not None:
            print(f"error: an admin with email {email} already exists", file=sys.stderr)
            return 1

        role = (
            await session.execute(select(Role).where(Role.key == SystemRole.SUPER_ADMIN.value))
        ).scalar_one_or_none()
        if role is None:
            print(
                "error: the super_admin role is missing — run 'alembic upgrade head' first",
                file=sys.stderr,
            )
            return 1

        admin = Admin(
            email=email,
            full_name=full_name,
            password_hash=hash_password(password),
            role_id=role.id,
            is_active=True,
        )
        session.add(admin)
        await session.commit()

    print(f"created super admin {email}")
    if generated:
        # Printed once, never stored. If it is lost, create another account.
        print(f"generated password: {password}")
        print("store it now — it is not recoverable")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli", description="Rozgar backend operations")
    sub = parser.add_subparsers(dest="command", required=True)

    boot = sub.add_parser("bootstrap-admin", help="create the first super admin")
    boot.add_argument("--email", required=True)
    boot.add_argument("--name", required=True, dest="full_name")
    boot.add_argument(
        "--password",
        help="omit to be prompted, or use --generate-password",
    )
    boot.add_argument(
        "--generate-password",
        action="store_true",
        help="generate a strong password and print it once",
    )

    args = parser.parse_args(argv)

    if args.command == "bootstrap-admin":
        password = args.password
        if not password and not args.generate_password:
            # getpass keeps the password out of shell history and process args.
            password = getpass.getpass("password: ")
            if password != getpass.getpass("confirm: "):
                print("error: passwords do not match", file=sys.stderr)
                return 2
        try:
            return asyncio.run(_run(bootstrap_admin(args.email, args.full_name, password)))
        finally:
            pass

    parser.print_help()
    return 2


async def _run(coro):  # type: ignore[no-untyped-def]
    try:
        return await coro
    finally:
        await dispose_engine()


if __name__ == "__main__":
    raise SystemExit(main())
