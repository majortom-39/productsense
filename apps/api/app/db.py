"""Supabase client setup.

Two clients:
- `supabase_anon` — uses anon key, RLS-enforced. For requests on behalf of a user.
- `supabase_admin` — service role, bypasses RLS. For agent backend writes.

The admin client should NEVER be exposed to the web client.
"""
from supabase import Client, create_client

from app.config import settings


def _build_client(key: str) -> Client | None:
    if not settings.supabase_url or not key:
        return None
    return create_client(settings.supabase_url, key)


# Public client for end-user-scoped operations (RLS enforced)
supabase_anon: Client | None = _build_client(settings.supabase_anon_key)

# Admin client for agent backend (RLS bypassed)
supabase_admin: Client | None = _build_client(settings.supabase_service_role_key)


def require_admin() -> Client:
    if supabase_admin is None:
        raise RuntimeError(
            "Supabase admin client not configured. "
            "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env"
        )
    return supabase_admin
