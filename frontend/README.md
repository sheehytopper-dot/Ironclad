# IronClad web front-end (rollout step 3)

React + Vite (Step 0 W1, owner-approved 2026-07-20), styled from the
`design/Ironclad_dc.html` mockup's design language. The front-end
computes **no financial numbers** — every value comes from the API at
full precision; `src/format.js` (the Tier-1 rules ported from
`ui/format.py`) is display-only, and null renders as an em-dash, never 0.

## Run (dev — Step 0 W2)

Two terminals from the repo root:

```
# 1. the API (serves the frozen engine)
.venv\Scripts\python -m uvicorn api.main:app --host 127.0.0.1 --port 8000

# 2. the front-end (proxies /api to :8000 — no CORS)
cd frontend
npm install        # first time only
npm run dev        # open http://localhost:5173
```

Properties are the `.icprop.json` files in `data/properties/`
(clorox_northlake and freeport are staged for the review).

## Test / build

```
npm test           # the ported display-formatting rules (node --test)
npm run build      # production bundle -> frontend/dist/
```

Serving `dist/` from uvicorn (the W2 production model) is a pending
`api/` addition — flagged, not yet wired.

## Screens (this rollout step)

Dashboard, Reports, Tenants — the mockup's three designed screens. The
other seven tabs are listed in the sidebar but disabled. The Tenants
rollover-generations panel is a FLAGGED placeholder: the data
(`result.segments`) has no API endpoint yet — an owner-approved additive
endpoint is required (see the panel's note).
