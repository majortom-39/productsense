"""Centralized settings loaded from environment.

Use:
    from app.config import settings
    settings.supabase_url
"""
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # Vertex AI / Gemini
    gcp_project_id: str = ""
    vertex_location: str = "global"

    # Three model tiers used across the team. Override per-agent below.
    # Moved DEEP + MID tiers from gemini-3.1-pro to gemini-3.5-flash:
    # 3.5-flash supports thinking_level (medium default, can go high), is
    # faster + cheaper than Pro for the synthesis-heavy agents (Theo/Kai
    # /Nora/Hugo). Pro stays as Maya's model only.
    deep_model: str = "gemini-3.5-flash"          # Flash + HIGH thinking
    mid_model: str = "gemini-3.5-flash"           # Flash + MEDIUM thinking
    fast_model: str = "gemini-3-flash-preview"    # Flash (no extended thinking)

    # Maya — orchestrator. Always deep + HIGH (non-negotiable per founder).
    maya_model: str = "gemini-3.1-pro-preview"
    maya_thinking_level: str = "HIGH"

    # Default sub-agent model (used when an agent doesn't override).
    subagent_model: str = "gemini-3-flash-preview"

    # Where the Deep Agents harness may write transient artifacts — e.g. the
    # SummarizationMiddleware offloading evicted chat history. Deliberately kept
    # OUT of the read-only knowledge tree (skills + memory). Empty = a per-OS
    # temp dir is used. This data is redundant: the durable record is the
    # LangGraph checkpoint plus the product DB.
    agent_artifacts_dir: str = ""

    # Firecrawl
    firecrawl_api_key: str = ""

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173"]

    # GitHub OAuth (asset manager — connect repos as project context).
    # Register an OAuth App at https://github.com/settings/developers and
    # set the callback URL to <web_origin>/integrations/github/callback.
    # Both vars empty = feature stays disabled; the UI surfaces a "not
    # configured" message rather than a broken connect flow.
    github_oauth_client_id: str = ""
    github_oauth_client_secret: str = ""
    # Where to redirect after the OAuth round-trip. Must be a path on the
    # web app, NOT the API — the web app then calls /integrations/github/exchange.
    github_oauth_redirect_uri: str = "http://localhost:5176/integrations/github/callback"

    # Fernet key for encrypting at-rest secrets (GitHub access tokens).
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Empty = encryption disabled — tokens stored plain (dev-only).
    asset_encryption_key: str = ""

    # ─── Supabase direct postgres connection (for LangGraph checkpointer) ─
    # The Supabase REST API (PostgREST) we use everywhere else can't host
    # the LangGraph checkpointer — it needs a real postgres connection.
    # Get the URI from Supabase dashboard → Settings → Database → Connection
    # string (use the "Transaction" pooler URL — port 6543, format
    # `postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres`).
    # Empty = checkpointer disabled, app falls back to stateless graph
    # (today's behavior). No crash.
    supabase_db_url: str = ""

    # ─── LangSmith tracing ──────────────────────────────────────────────
    # LangChain auto-traces when these are present in os.environ. We load
    # them via pydantic-settings (so they live in .env alongside every other
    # secret) then re-export them to os.environ below — pydantic-settings
    # does NOT push to os.environ, but LangChain reads from there.
    # Empty key = tracing silently off (no crash, no traces).
    langsmith_tracing: str = ""
    langsmith_api_key: str = ""
    langsmith_project: str = "productsense"
    langsmith_endpoint: str = ""        # Optional — defaults to GCP US.
    langsmith_workspace_id: str = ""    # Optional — only for multi-workspace PATs.

    model_config = SettingsConfigDict(
        # Look up the .env from either the api/ working dir or the repo root
        env_file=("../../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()

# ─── Push LangSmith env vars to os.environ ──────────────────────────────
# LangChain reads LANGSMITH_* from os.environ directly. pydantic-settings
# does NOT do this for us — so we forward the values after load. Only set
# vars that have a value, otherwise we'd clobber any shell-exported ones
# with the empty default.
def _forward_to_environ(key: str, value: str) -> None:
    if value and not os.environ.get(key):
        os.environ[key] = value


_forward_to_environ("LANGSMITH_TRACING", settings.langsmith_tracing)
_forward_to_environ("LANGSMITH_API_KEY", settings.langsmith_api_key)
_forward_to_environ("LANGSMITH_PROJECT", settings.langsmith_project)
_forward_to_environ("LANGSMITH_ENDPOINT", settings.langsmith_endpoint)
_forward_to_environ("LANGSMITH_WORKSPACE_ID", settings.langsmith_workspace_id)
