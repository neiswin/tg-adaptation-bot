import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

_pool: asyncpg.Pool | None = None


def _db_dsn() -> str:
    host = os.getenv("DB_HOST", "127.0.0.1")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    if not all([name, user, password]):
        raise RuntimeError("DB_* env vars are not set")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


async def init_db() -> None:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn=_db_dsn(), min_size=1, max_size=5)


async def close_db() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def upsert_user(telegram_id: int, username: str | None, first_name: str | None, last_name: str | None) -> None:
    if _pool is None:
        raise RuntimeError("DB pool is not initialized")
    await _pool.execute(
        """
        INSERT INTO users (telegram_id, username, first_name, last_name, first_seen, last_seen)
        VALUES ($1, $2, $3, $4, now(), now())
        ON CONFLICT (telegram_id) DO UPDATE
          SET username  = EXCLUDED.username,
              first_name = EXCLUDED.first_name,
              last_name  = EXCLUDED.last_name,
              last_seen  = now();
        """,
        telegram_id, username, first_name, last_name
    )

async def get_user_stats() -> dict:
    if _pool is None:
        raise RuntimeError("DB pool is not initialized")

    row = await _pool.fetchrow(
        """
        SELECT
          count(*)::int AS total,
          count(*) FILTER (WHERE last_seen > now() - interval '7 days')::int AS active_7d,
          count(*) FILTER (WHERE last_seen > now() - interval '30 days')::int AS active_30d
        FROM users;
        """
    )
    return dict(row)
