# IronClad web front-end (rollout step 3)

React + Vite (Step 0 W1, owner-approved 2026-07-20), styled from the
`design/Ironclad_dc.html` mockup's design language. The front-end
computes **no financial numbers** — every value comes from the API at
full precision; `src/format.js` (the Tier-1 rules ported from
`ui/format.py`) is display-only, and null renders as an em-dash, never 0.

## Run — ONE COMMAND (W2, wired)

From the repo root, after a front-end build exists:

```
cd frontend && npm install && npm run build && cd ..
.venv\Scripts\python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000** — uvicorn serves the built app at `/` and
the API under `/api/*`. Rebuild (`npm run build`) after front-end
changes.

Dev alternative (hot reload): keep uvicorn running and, in a second
terminal, `cd frontend && npm run dev` → http://localhost:5173 (the Vite
proxy forwards /api — no CORS).

Properties are the `.icprop.json` files in `data/properties/`
(clorox_northlake and freeport are staged for the review; a per-name
`<name>.expected_annual_cash_flow.csv` enables Benchmark #24).

## Test / build

```
npm test           # display-formatting + document-assembly rules
npm run build      # production bundle -> frontend/dist/
```

## Screens (rollout step 4)

- **Dashboard / Reports** — read-only output screens (step 3).
- **Tenants** — FULLY drill-in editable: click a rent-roll row → the
  split-pane editor for that lease's complete nested detail (rent steps,
  CPI, free rent, misc items, recoveries, TI/LC, security deposit,
  upon-expiration + MLP link); Apply PUTs the whole document; the
  rollover-generations panel is LIVE via `/api/tenants/generations`.
- **Market** — inflation as flat OR variable per-year schedules, custom
  indices, general vacancy, credit loss, the MLP grid + per-MLP detail.
- Property / Revenues / Expenses / Investment / Valuation — next
  (after owner review of the editing pattern).
