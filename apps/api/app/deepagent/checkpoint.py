"""Durable checkpointing for the Deep Agents stack, backed by Supabase Postgres.

A checkpointer is what makes interrupts resumable and lets a run survive a
process restart. `thread_id = project_id` means every project is its own durable
conversation.

Connection settings are tuned for the Supabase transaction pooler (pgbouncer):
  - autocommit=True       — setup() runs CREATE TABLE outside a transaction.
  - prepare_threshold=0   — pgbouncer transaction mode rejects prepared statements.
  - min_size=0 + check    — Supabase kills idle connections (~60s); we validate
                            a connection (SELECT 1) before lending it and keep no
                            idle connections lingering.

Graceful degradation: if SUPABASE_DB_URL is unset, the provider yields None and
the caller builds an in-memory agent instead (no durable state, no crash).
"""
from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from app.config import settings


def _build_pool():
    from psycopg_pool import AsyncConnectionPool

    return AsyncConnectionPool(
        conninfo=settings.supabase_db_url.strip(),
        min_size=0,
        max_size=10,
        max_idle=30.0,
        check=AsyncConnectionPool.check_connection,
        kwargs={"autocommit": True, "prepare_threshold": 0},
        open=False,
    )


@contextlib.asynccontextmanager
async def postgres_saver() -> AsyncIterator[object | None]:
    """Async context manager yielding an AsyncPostgresSaver (or None if disabled).

    Use for scripts/tests and short-lived contexts. For the long-lived app
    process, prefer a pool opened in the FastAPI lifespan.
    """
    db_url = settings.supabase_db_url.strip()
    if not db_url:
        yield None
        return

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    pool = _build_pool()
    await pool.open()
    try:
        saver = AsyncPostgresSaver(pool)
        await saver.setup()  # idempotent table creation
        yield saver
    finally:
        await pool.close()
