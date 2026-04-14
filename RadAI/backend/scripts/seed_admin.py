"""
RadAI — seed or reset the default admin user.

Idempotent: creates the admin user if it does not exist, otherwise updates
the existing row. Used by `make verify` and CI to guarantee the dev-default
credentials (admin / changeme) can log in against a freshly provisioned
database.

Run INSIDE the backend container:

    docker compose exec backend python scripts/seed_admin.py

Environment overrides:
    ADMIN_USERNAME  (default: admin)
    ADMIN_PASSWORD  (default: changeme)
    ADMIN_EMAIL     (default: admin@radai.local)
    ADMIN_ROLE      (default: admin)
"""
import asyncio
import os
import sys

from passlib.context import CryptContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def _async_db_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)
    # Translate sync psycopg2 URL → asyncpg driver
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql+psycopg2://"):
        url = url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    return url


async def main() -> int:
    username = os.environ.get("ADMIN_USERNAME", "admin")
    password = os.environ.get("ADMIN_PASSWORD", "changeme")
    email = os.environ.get("ADMIN_EMAIL", "admin@radai.local")
    role = os.environ.get("ADMIN_ROLE", "admin")

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    password_hash = pwd_ctx.hash(password)

    engine = create_async_engine(_async_db_url())

    async with engine.begin() as conn:
        existing = await conn.execute(
            text("SELECT id FROM users WHERE username = :u"),
            {"u": username},
        )
        row = existing.first()
        if row is None:
            await conn.execute(
                text(
                    "INSERT INTO users (username, email, password_hash, role, is_active) "
                    "VALUES (:u, :e, :h, :r, true)"
                ),
                {"u": username, "e": email, "h": password_hash, "r": role},
            )
            print(f"Created admin user '{username}' with role '{role}'")
        else:
            await conn.execute(
                text(
                    "UPDATE users SET password_hash = :h, email = :e, role = :r, "
                    "is_active = true WHERE username = :u"
                ),
                {"h": password_hash, "e": email, "r": role, "u": username},
            )
            print(f"Reset admin user '{username}' password and role '{role}'")

    await engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
