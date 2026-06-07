"""LangGraph checkpointer + store singletons backed by Supabase Postgres.

Why this exists:
  Without a checkpointer, the Maya graph is stateless — every founder turn
  we rehydrate from `messages` table, build a fresh graph state, and throw
  it away at turn end. That's fine for chat throughput but it means:
    - we can't `interrupt()` (no state to resume from)
    - we can't time-travel / replay a turn
    - if uvicorn crashes mid-turn, the in-flight state is gone (we re-do
      every tool call on restart instead of resuming at the last good
      super-step)
    - sub-agents can't have their own memory across dispatches

  Wiring an `AsyncPostgresSaver` (and `AsyncPostgresStore` for cross-project
  founder prefs) gives us all of the above. `thread_id = project_id` means
  every project is its own durable conversation.

Architecture:
  - ONE connection pool, opened at app startup via FastAPI lifespan.
  - Saver + Store share the pool (cheap; both use the same DB).
  - Graceful degradation: if `SUPABASE_DB_URL` is empty, this module
    returns None for saver/store and the rest of the app falls back to
    today's stateless behavior. No crash, no error spam — just a single
    "checkpointer disabled" log at startup so the founder knows.

  - `setup()` is called lazily on first use to create the checkpoint /
    store tables in Supabase. Idempotent.

External surface:
    await init_checkpointer()    # call from FastAPI lifespan startup
    await close_checkpointer()   # call from FastAPI lifespan shutdown
    get_checkpointer() -> AsyncPostgresSaver | None
    get_store()        -> AsyncPostgresStore | None

Tables created in Supabase (idempotent):
    checkpoints, checkpoint_writes, checkpoint_blobs, checkpoint_migrations
      — LangGraph's own checkpoint tables.
    store, store_migrations
      — LangGraph's Store tables (for cross-project founder prefs).

  These live alongside our existing tables (`messages`, `discovery_*`,
  `decisions`, etc.) in the same Supabase database. The REST API doesn't
  see them — they're queried via the direct postgres connection.
"""
from __future__ import annotations

from typing import Optional

from app.config import settings


# Module-level singletons. Populated by init_checkpointer(); None when
# SUPABASE_DB_URL isn't set or init failed.
_checkpointer = None      # AsyncPostgresSaver | None
_store = None             # AsyncPostgresStore | None
_pool = None              # AsyncConnectionPool | None
_initialized = False      # True after first init_checkpointer() call
_disabled_reason: Optional[str] = None  # human-readable why if None


async def init_checkpointer() -> None:
    """Open the connection pool and start the saver + store. Called from
    FastAPI lifespan startup. Idempotent — safe to call twice.

    If SUPABASE_DB_URL is unset, this is a no-op (sets `_disabled_reason`).
    The app continues to work; the graph just won't have durable state.
    """
    global _checkpointer, _store, _pool, _initialized, _disabled_reason
    if _initialized:
        return
    _initialized = True

    db_url = settings.supabase_db_url.strip()
    if not db_url:
        _disabled_reason = (
            "SUPABASE_DB_URL is not set in .env - LangGraph checkpointer "
            "disabled. The app will work but each Maya turn rehydrates from "
            "the messages table (today's behavior). To enable: get the "
            "Transaction-pooler URL from Supabase dashboard -> Settings -> "
            "Database -> Connection string and set SUPABASE_DB_URL in .env."
        )
        print(f"[checkpointer] {_disabled_reason}")
        return

    try:
        # Import lazily so the app can boot even if these packages are
        # missing (the import failure becomes a degraded-mode log, not
        # a hard crash).
        from psycopg_pool import AsyncConnectionPool
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from langgraph.store.postgres.aio import AsyncPostgresStore
    except ImportError as e:
        _disabled_reason = (
            f"LangGraph postgres packages not installed: {e}. "
            "Run: pip install langgraph-checkpoint-postgres 'psycopg[binary,pool]'"
        )
        print(f"[checkpointer] {_disabled_reason}")
        return

    try:
        # `open=False` defers connection until we explicitly open(). That
        # way an unreachable DB at startup doesn't crash the app — we get
        # a clean error log instead.
        #
        # Resiliency against Supabase dropping idle connections:
        # - `min_size=0` — don't keep idle connections lingering. Supabase
        #   kills connections after ~60s of NAT/firewall idleness, and a
        #   killed-then-handed-out connection causes the exact failure mode
        #   we saw in production: "consuming input failed: server closed
        #   the connection unexpectedly".
        # - `check=AsyncConnectionPool.check_connection` — run a `SELECT 1`
        #   before lending a pooled connection. Dead connections get
        #   silently discarded and replaced, so callers always see a
        #   live connection.
        # - `max_idle=30.0` — drop any idle connection that's been sitting
        #   for >30s, well under Supabase's idle-kill window.
        from psycopg_pool import AsyncConnectionPool as _Pool
        _pool = _Pool(
            conninfo=db_url,
            min_size=0,
            max_size=10,
            max_idle=30.0,
            check=_Pool.check_connection,
            kwargs={
                # autocommit is REQUIRED for langgraph-checkpoint-postgres —
                # it runs CREATE TABLE / CREATE INDEX in setup() outside a
                # transaction.
                "autocommit": True,
                "prepare_threshold": 0,
            },
            open=False,
        )
        await _pool.open()
        _checkpointer = AsyncPostgresSaver(_pool)
        _store = AsyncPostgresStore(_pool)
        # First-run table creation. Idempotent — both setup() methods are
        # safe to call on every startup (they check for existing tables).
        await _checkpointer.setup()
        await _store.setup()
        print("[checkpointer] AsyncPostgresSaver + AsyncPostgresStore ready (Supabase)")
    except Exception as e:
        # Don't crash the app — degrade. The user gets a clear log and
        # can fix the URL / firewall / password without redeploying code.
        _disabled_reason = f"checkpointer init failed: {e}"
        print(f"[checkpointer] {_disabled_reason}")
        _checkpointer = None
        _store = None
        if _pool is not None:
            try:
                await _pool.close()
            except Exception:
                pass
            _pool = None


async def close_checkpointer() -> None:
    """Close the connection pool. Called from FastAPI lifespan shutdown.

    Resets `_initialized` so a subsequent `init_checkpointer()` actually
    re-opens the pool (otherwise the singleton guard makes it a no-op,
    leaving saver/store as None for the rest of the process). This matters
    in two real scenarios:
      1. Tests that exercise close+reopen (e.g. e2e_production_readiness
         section C).
      2. Production: if we ever add health-check-driven pool recycling
         on persistent connection failures, the close must allow a clean
         re-init."""
    global _checkpointer, _store, _pool, _initialized, _disabled_reason
    if _pool is not None:
        try:
            await _pool.close()
        except Exception as e:
            print(f"[checkpointer] pool.close() failed: {e}")
    _checkpointer = None
    _store = None
    _pool = None
    _initialized = False
    _disabled_reason = None


def get_checkpointer():
    """Return the AsyncPostgresSaver, or None if disabled/uninitialized.
    Callers must handle None (typically by not passing `checkpointer=` to
    graph.compile, which produces today's stateless behavior)."""
    return _checkpointer


def get_store():
    """Return the AsyncPostgresStore, or None if disabled/uninitialized."""
    return _store


def is_enabled() -> bool:
    return _checkpointer is not None


def disabled_reason() -> Optional[str]:
    """Human-readable explanation of why the checkpointer is off, if it is."""
    return _disabled_reason
