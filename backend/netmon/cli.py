"""Management CLI.

Examples::

    netmon migrate                  # apply database migrations
    netmon create-admin -e me@example.com
    netmon seed-demo                # demo network (pairs well with NETMON_MONITOR_MODE=simulation)
    netmon serve --reload
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeVar

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from netmon import __version__
from netmon.core.config import Settings, get_settings
from netmon.core.security import hash_password
from netmon.db.session import create_engine, create_session_factory
from netmon.models import User, UserRole
from netmon.services.bootstrap import ensure_default_rules, ensure_first_admin, seed_demo
from netmon.services.demo import backfill_history

BASE_DIR = Path(__file__).resolve().parent
R = TypeVar("R")


def alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(BASE_DIR / "db" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    cfg.attributes["configure_logger"] = False
    return cfg


def cmd_migrate(args: argparse.Namespace) -> int:
    command.upgrade(alembic_config(), args.revision)
    print(f"database migrated to {args.revision}")
    return 0


async def _with_session(fn: Callable[[AsyncSession, Settings], Awaitable[R]]) -> R:
    settings = get_settings()
    engine = create_engine(settings)
    try:
        async with create_session_factory(engine)() as session:
            return await fn(session, settings)
    finally:
        await engine.dispose()


def cmd_init(args: argparse.Namespace) -> int:
    cmd_migrate(argparse.Namespace(revision="head"))

    async def run(session: AsyncSession, settings: Settings) -> tuple[User | None, int, int]:
        admin = await ensure_first_admin(session, settings)
        rules = await ensure_default_rules(session)
        devices = await seed_demo(session) if args.demo else 0
        if devices and args.history_hours:
            await backfill_history(session, args.history_hours)
        return admin, rules, devices

    admin, rules, devices = asyncio.run(_with_session(run))
    if admin:
        print(f"created administrator {admin.email}")
    print(f"default alert rules added: {rules}; demo devices added: {devices}")
    return 0


def cmd_create_admin(args: argparse.Namespace) -> int:
    password = args.password or getpass.getpass("Password (min 8 chars): ")
    if len(password) < 8:
        print("password must be at least 8 characters", file=sys.stderr)
        return 1

    async def run(session: AsyncSession, _settings: Settings) -> User:
        email = args.email.lower()
        user = await session.scalar(select(User).where(func.lower(User.email) == email))
        if user is None:
            user = User(email=email, full_name=args.name or "Administrator")
            session.add(user)
        user.hashed_password = hash_password(password)
        user.role = UserRole.ADMIN
        user.is_active = True
        await session.commit()
        return user

    user = asyncio.run(_with_session(run))
    print(f"administrator {user.email} is ready")
    return 0


def cmd_seed_demo(args: argparse.Namespace) -> int:
    async def run(session: AsyncSession, _settings: Settings) -> tuple[int, int]:
        await ensure_default_rules(session)
        added = await seed_demo(session)
        samples = await backfill_history(session, args.history_hours) if args.history_hours else 0
        return added, samples

    added, samples = asyncio.run(_with_session(run))
    print(f"demo devices added: {added}" if added else "devices already exist - none added")
    if samples:
        print(f"synthetic history: {samples} samples over {args.history_hours} h")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "netmon.main:app_factory",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="netmon", description="NetMon management CLI")
    parser.add_argument("--version", action="version", version=f"netmon {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("migrate", help="apply database migrations")
    p.add_argument("revision", nargs="?", default="head")
    p.set_defaults(func=cmd_migrate)

    p = sub.add_parser("init", help="migrate, create first admin and default alert rules")
    p.add_argument("--demo", action="store_true", help="also seed the demo network")
    p.add_argument(
        "--history-hours",
        type=int,
        default=0,
        help="with --demo: back-fill this many hours of synthetic history",
    )
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("create-admin", help="create or reset an administrator account")
    p.add_argument("-e", "--email", required=True)
    p.add_argument("-n", "--name")
    p.add_argument("-p", "--password", help="omit to be prompted")
    p.set_defaults(func=cmd_create_admin)

    p = sub.add_parser("seed-demo", help="insert the demo office network")
    p.add_argument(
        "--history-hours",
        type=int,
        default=0,
        help="back-fill this many hours of synthetic measurements (e.g. 168)",
    )
    p.set_defaults(func=cmd_seed_demo)

    p = sub.add_parser("serve", help="run the API server")
    p.add_argument("--host", default="0.0.0.0")  # noqa: S104 - server bind address
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true")
    p.set_defaults(func=cmd_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
