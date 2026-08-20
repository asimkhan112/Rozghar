"""Operational commands.

`bootstrap-admin` exists because there is no public registration endpoint and
never will be. The first super admin has to come from somewhere, and a command
run by whoever controls the server is the right somewhere.

    python -m app.cli bootstrap-admin --email you@plenilo.com --name "Your Name"

`run-task` runs any scheduled task immediately. It is the same code path the
scheduler uses, advisory lock included, so running one by hand while the
scheduler is live is safe — one of the two will simply skip.

    python -m app.cli run-task ensure_partitions
    python -m app.cli run-task --list
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


async def run_scheduled_task(name: str) -> int:
    from app.tasks.scheduled_tasks import TASKS, run_task

    if name not in TASKS:
        print(f"error: unknown task {name!r}", file=sys.stderr)
        print(f"available: {', '.join(sorted(TASKS))}", file=sys.stderr)
        return 2

    result = await run_task(name, TASKS[name])
    if not result.ran:
        print(f"{name}: skipped — another instance holds the lock")
        return 0
    if result.error:
        print(f"{name}: failed after {result.duration_ms}ms — {result.error}", file=sys.stderr)
        return 1
    print(f"{name}: completed in {result.duration_ms}ms")
    for key, value in result.details.items():
        print(f"  {key}: {value}")
    return 0


async def seed_taxonomy(purge: bool) -> int:
    from app.db.seed_taxonomy import (
        purge_test_data,
        recount,
        seed_categories,
        seed_locations,
    )

    async with SessionFactory() as session:
        if purge:
            removed = await purge_test_data(session)
            for table, count in removed.items():
                print(f"removed {count} unused test {table}")

        categories = await seed_categories(session)
        locations = await seed_locations(session)
        await recount(session)
        await session.commit()

    print(f"added {categories} categories, {locations} locations")
    print("rebuilt job counts from published listings")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli", description="Plenilo backend operations")
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

    seed = sub.add_parser("seed-taxonomy", help="add real categories and locations")
    seed.add_argument(
        "--purge-test-data",
        action="store_true",
        dest="purge",
        help="also remove unreferenced M3–M7 rows left by the test suites",
    )

    task = sub.add_parser("run-task", help="run a scheduled task immediately")
    task.add_argument("name", nargs="?", help="task name")
    task.add_argument("--list", action="store_true", help="list the available tasks")

    args = parser.parse_args(argv)

    if args.command == "seed-taxonomy":
        return asyncio.run(_run(seed_taxonomy(args.purge)))

    if args.command == "run-task":
        from app.tasks.scheduled_tasks import TASKS

        if args.list or not args.name:
            for name in sorted(TASKS):
                print(name)
            return 0
        return asyncio.run(_run(run_scheduled_task(args.name)))

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
