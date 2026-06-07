"""Test fixtures.

If a real `.env` is present at the repo root, we load it so live-smoke
tests can authenticate against the real Supabase / Vertex / Firecrawl.

For unit tests that stub the network entirely, we still set safe defaults
for any var the .env didn't provide — so `from app.db import ...` etc.
import without crashing.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Add the api root to sys.path so `import main`, `app.*` resolves
_API_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_API_ROOT))

# Load real .env (repo root) — but only if a value isn't already set in env
_REPO_ROOT = _API_ROOT.parent.parent
_ENV_FILE = _REPO_ROOT / ".env"
if _ENV_FILE.is_file():
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value

# Safety defaults — only kick in when .env didn't supply them
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon")
os.environ.setdefault("GCP_PROJECT_ID", "test-gcp")
os.environ.setdefault("VERTEX_LOCATION", "global")
os.environ.setdefault("FIRECRAWL_API_KEY", "test-firecrawl")
