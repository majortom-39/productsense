# Web

Founder-facing React app. Vite + Tailwind + shadcn/ui.

## Quick start

```bash
cp ../../.env.example ../../.env       # at the monorepo root
# fill in VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY, VITE_API_URL

pnpm install                           # at the monorepo root
pnpm dev:web                           # or: pnpm --filter web dev
```

Opens at `http://localhost:5173`.

## Layout (planned)

```
apps/web/src/
├── main.tsx              # Entry; QueryClient + Router
├── App.tsx               # Top-level shell
├── pages/
│   ├── Auth.tsx          # Sign-in (Phase 1)
│   └── Workspace.tsx     # Sidebar + chat + workspace tabs (Phase 1+)
├── components/
│   ├── chat/             # Chat panel, message bubble, tool-call chip
│   ├── workspace/        # Tabs shell + Research/PRD/Decisions/Sprint tabs
│   ├── sidebar/          # Project switcher + user menu
│   └── ui/               # shadcn primitives
├── lib/
│   ├── api.ts            # FastAPI client
│   ├── supabase.ts       # Supabase client
│   └── utils.ts          # cn() and helpers
└── index.css             # Tailwind base + theme tokens
```

## Reference UI

The visual baseline is the preview at `Productsense v.0/frontend/src/pages/Preview.tsx`. Port the JSX structure into `components/` here, but wire to real backend data — not the mock data file.
