# API

FastAPI backend hosting Maya + sub-agents.

## Quick start (dev)

```bash
cd apps/api
uv venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
uvicorn main:app --reload --port 8000
```

(Or use plain `pip install -e ".[dev]"` if you prefer pip.)

## Auth for Vertex AI

For local dev:
```bash
gcloud auth application-default login
gcloud config set project <your-gcp-project-id>
```

For deployed environments: set `GOOGLE_APPLICATION_CREDENTIALS` to a service-account JSON key.

## Health check

```bash
curl http://localhost:8000/health
```

## Layout

```
apps/api/
├── main.py                # FastAPI app
└── app/
    ├── config.py          # Pydantic-settings, loads ../../.env
    ├── db.py              # Supabase clients (anon + admin)
    ├── routes/            # FastAPI routers
    │   ├── health.py
    │   ├── projects.py
    │   └── maya.py
    ├── agents/            # 8 sub-agents (Phase 3+)
    └── services/          # gemini, firecrawl, prompts (Phase 2+)
```
