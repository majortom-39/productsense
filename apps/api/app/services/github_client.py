"""GitHub OAuth + REST client.

Two responsibilities:

1.  OAuth round-trip — exchange the `code` returned by GitHub's authorize
    flow for an access_token, fetch the user's login, persist the
    encrypted token in `github_connections`.

2.  Repo digest fetch — given a connection + repo full_name, pull the
    pieces we need (README, package files, top-level tree) and turn them
    into a markdown digest for the asset manager.

We deliberately stay narrow: no webhooks, no fork awareness, no large
file handling. The digest is a snapshot Maya can ground tech advice on.
For per-file detail the coding agent (Claude Code / Cursor) reads the
repo locally via MCP — that's the right division of labor.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.config import settings
from app.db import require_admin
from app.services import assets as asset_svc
from app.services.ingestors.base import truncate_to_tokens, approx_token_count


# ─── Fernet token encryption ──────────────────────────────────────────────


def _fernet():
    """Lazy-init a Fernet cipher from the env key. Returns None when no
    key is configured — caller stores tokens in plaintext (dev only,
    LOUD warning at startup).
    """
    key = settings.asset_encryption_key.strip()
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(key.encode())
    except Exception as e:
        print(f"[github_client] WARN: bad ASSET_ENCRYPTION_KEY — tokens stored plain. ({e})")
        return None


def encrypt_token(token: str) -> str:
    f = _fernet()
    if f is None:
        return token
    return f.encrypt(token.encode()).decode()


def decrypt_token(blob: str) -> str:
    f = _fernet()
    if f is None:
        return blob
    try:
        return f.decrypt(blob.encode()).decode()
    except Exception:
        # Stored as plaintext on a dev box without a key
        return blob


# ─── OAuth round-trip ─────────────────────────────────────────────────────


GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


async def exchange_code_for_token(code: str) -> dict:
    """POST to GitHub's token endpoint. Returns the raw token payload
    ({access_token, scope, token_type}). Raises on non-200 / missing token."""
    if not settings.github_oauth_client_id or not settings.github_oauth_client_secret:
        raise RuntimeError("GitHub OAuth not configured — set GITHUB_OAUTH_CLIENT_ID/SECRET in .env")

    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_oauth_client_id,
                "client_secret": settings.github_oauth_client_secret,
                "code": code,
                "redirect_uri": settings.github_oauth_redirect_uri,
            },
        )
        r.raise_for_status()
        body = r.json()
    if "access_token" not in body:
        raise RuntimeError(f"GitHub token exchange failed: {body}")
    return body


async def fetch_user_login(access_token: str) -> str:
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(
            GITHUB_USER_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )
        r.raise_for_status()
        return r.json()["login"]


async def save_connection(*, user_id: str, code: str) -> dict:
    """Full OAuth completion: exchange code → fetch login → upsert row."""
    token_data = await exchange_code_for_token(code)
    access_token = token_data["access_token"]
    scope = token_data.get("scope", "")
    login = await fetch_user_login(access_token)

    db = require_admin()
    payload = {
        "user_id": user_id,
        "github_user_login": login,
        "access_token_enc": encrypt_token(access_token),
        "scope": scope,
    }
    # Upsert on (user_id, github_user_login)
    existing = (
        db.table("github_connections")
        .select("*")
        .eq("user_id", user_id)
        .eq("github_user_login", login)
        .maybe_single()
        .execute()
    )
    if existing and existing.data:
        row = (
            db.table("github_connections")
            .update(payload)
            .eq("id", existing.data["id"])
            .execute()
        )
    else:
        row = db.table("github_connections").insert(payload).execute()
    out = (row.data or [{}])[0]
    # Don't return the encrypted token to the caller — strip it.
    out.pop("access_token_enc", None)
    return out


def list_connections_for_user(user_id: str) -> list[dict]:
    db = require_admin()
    rows = (
        db.table("github_connections")
        .select("id,github_user_login,scope,created_at,updated_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return rows.data or []


def get_connection(connection_id: str) -> Optional[dict]:
    db = require_admin()
    row = (
        db.table("github_connections")
        .select("*")
        .eq("id", connection_id)
        .maybe_single()
        .execute()
    )
    return row.data if row else None


def delete_connection(connection_id: str) -> None:
    db = require_admin()
    db.table("github_connections").delete().eq("id", connection_id).execute()


# ─── Repo API ─────────────────────────────────────────────────────────────


GITHUB_API = "https://api.github.com"


async def list_repos(connection_id: str) -> list[dict]:
    """List the user's repos (max 100 most-recently-pushed). Used by the
    Settings UI's repo picker. Returns a slim {full_name, description,
    default_branch, private, language} per row."""
    conn = get_connection(connection_id)
    if not conn:
        raise ValueError("connection not found")
    token = decrypt_token(conn["access_token_enc"])
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(
            f"{GITHUB_API}/user/repos?per_page=100&sort=pushed",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        r.raise_for_status()
        repos = r.json()
    return [
        {
            "full_name": r["full_name"],
            "description": r.get("description"),
            "default_branch": r.get("default_branch") or "main",
            "private": r.get("private", False),
            "language": r.get("language"),
            "pushed_at": r.get("pushed_at"),
        }
        for r in repos
    ]


async def fetch_repo_tree(
    connection_id: str, repo_full_name: str, branch: str = "main"
) -> list[dict]:
    """Get the full tree for a branch. Returns a list of {path, type, size}.
    Uses git/trees with recursive=1 — capped by GitHub at 100k entries.
    """
    conn = get_connection(connection_id)
    if not conn:
        raise ValueError("connection not found")
    token = decrypt_token(conn["access_token_enc"])
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(
            f"{GITHUB_API}/repos/{repo_full_name}/git/trees/{branch}?recursive=1",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        r.raise_for_status()
        data = r.json()
    return data.get("tree", [])


async def fetch_file(
    connection_id: str, repo_full_name: str, path: str, branch: str = "main"
) -> Optional[str]:
    """Fetch a single file's text content (decoded from base64). Returns
    None if missing / binary / oversized."""
    conn = get_connection(connection_id)
    if not conn:
        return None
    token = decrypt_token(conn["access_token_enc"])
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(
            f"{GITHUB_API}/repos/{repo_full_name}/contents/{path}",
            params={"ref": branch},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()
    if data.get("encoding") != "base64" or not data.get("content"):
        return None
    try:
        raw = base64.b64decode(data["content"])
        return raw.decode("utf-8")
    except Exception:
        return None


# ─── Repo digest builder ──────────────────────────────────────────────────


# Files we always pull when present — these are the highest-signal context
# for a senior PM trying to understand "what is this project."
_PRIORITY_FILES = [
    "README.md", "README", "README.rst", "README.txt",
    "package.json", "pyproject.toml", "requirements.txt",
    "Gemfile", "go.mod", "Cargo.toml", "composer.json",
    "Dockerfile", "docker-compose.yml",
    ".productsense/prd.md",
]

# Top-level dirs we surface in the tree summary
_INTERESTING_DIRS = {
    "src", "app", "apps", "lib", "components", "pages",
    "routes", "api", "server", "backend", "frontend", "web",
    "supabase", "prisma", "migrations", "tests", "test",
}


def _summarize_tree(tree: list[dict]) -> str:
    """Build a markdown summary of the repo tree: file counts by top-level
    dir + a compact listing of interesting paths."""
    if not tree:
        return "_(empty repo)_"

    by_dir: dict[str, int] = {}
    interesting: list[str] = []
    for entry in tree:
        path = entry.get("path", "")
        if not path or entry.get("type") != "blob":
            continue
        top = path.split("/", 1)[0]
        by_dir[top] = by_dir.get(top, 0) + 1
        if top in _INTERESTING_DIRS and path.count("/") <= 2:
            interesting.append(path)

    lines = ["## Top-level structure", ""]
    for d, count in sorted(by_dir.items(), key=lambda kv: -kv[1])[:20]:
        is_dir = "/" if d in _INTERESTING_DIRS or count > 1 else ""
        lines.append(f"- `{d}{is_dir}` — {count} file(s)")

    if interesting:
        lines.append("\n## Notable paths\n")
        for p in sorted(interesting)[:50]:
            lines.append(f"- `{p}`")
    return "\n".join(lines)


async def ingest_repo(
    *,
    project_id: str,
    connection_id: str,
    repo_full_name: str,
    branch: str = "main",
) -> dict:
    """Build a repo digest asset for a project. Creates a new
    project_assets row OR updates the existing one referenced by the
    project_repo_links row. Returns the asset row."""
    db = require_admin()

    # Reuse or create the asset row up front so the UI has something to
    # poll for status updates.
    existing_link = (
        db.table("project_repo_links")
        .select("*")
        .eq("project_id", project_id)
        .maybe_single()
        .execute()
    )
    link_row = existing_link.data if existing_link else None

    if link_row and link_row.get("asset_id"):
        asset_id = link_row["asset_id"]
        asset_svc.update(
            asset_id,
            status="processing",
            display_name=repo_full_name,
            source_ref=repo_full_name,
            error_text=None,
        )
    else:
        new_asset = asset_svc.create(
            project_id=project_id,
            asset_type="repo",
            source_kind="github_repo",
            source_ref=repo_full_name,
            display_name=repo_full_name,
        )
        asset_id = new_asset["id"]
        asset_svc.update(asset_id, status="processing")

    try:
        tree = await fetch_repo_tree(connection_id, repo_full_name, branch)
        tree_md = _summarize_tree(tree)

        # Pull the top-priority files in parallel-friendly order. We do
        # them sequentially to keep rate-limit pressure predictable.
        section_blocks: list[str] = []
        for filename in _PRIORITY_FILES:
            content = await fetch_file(connection_id, repo_full_name, filename, branch)
            if not content:
                continue
            excerpt = content[:6000]   # ~1500 tokens per file at most
            if len(content) > 6000:
                excerpt += "\n\n_(file truncated)_"
            section_blocks.append(f"### `{filename}`\n\n```\n{excerpt}\n```")
            if len(section_blocks) >= 4:
                break   # 4 files max — keep total digest tight

        body_md = (
            f"# {repo_full_name}\n\n"
            f"_GitHub repo · branch `{branch}` · {len(tree)} files_\n\n"
            f"{tree_md}\n\n"
        )
        if section_blocks:
            body_md += "## Key files\n\n" + "\n\n".join(section_blocks)

        digest = truncate_to_tokens(body_md)
        asset_svc.update(
            asset_id,
            status="ready",
            digest_md=digest,
            digest_tokens=approx_token_count(digest),
            metadata={
                "repo_full_name": repo_full_name,
                "branch": branch,
                "n_files": len(tree),
                "key_files_included": len(section_blocks),
            },
            error_text=None,
        )

        # Upsert the link row
        link_payload = {
            "project_id": project_id,
            "github_connection_id": connection_id,
            "repo_full_name": repo_full_name,
            "branch": branch,
            "asset_id": asset_id,
            "last_synced_at": datetime.now(timezone.utc).isoformat(),
        }
        if link_row:
            db.table("project_repo_links").update(link_payload).eq("id", link_row["id"]).execute()
        else:
            db.table("project_repo_links").insert(link_payload).execute()

        return asset_svc.get(asset_id) or {}
    except Exception as e:
        asset_svc.update(asset_id, status="error", error_text=str(e)[:1000])
        raise
