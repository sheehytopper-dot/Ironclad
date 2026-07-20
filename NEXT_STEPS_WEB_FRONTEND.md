# NEXT STEPS — THE WEB FRONT-END PIVOT (FastAPI + Claude Design UI)

**DRAFT — PLAN ONLY, awaiting owner review of this document and the
Step 0 decisions below (Iron Rule 2). No `api/` or front-end code, no
`engine/` change, and no Streamlit removal until Topper signs off.**

**The pivot (owner decision, 2026-07-19):** the Streamlit UI cannot
reproduce the Claude Design mockup's layout and interaction model. The
application moves to a real web front-end — built from the Claude Design
export (`design/Ironclad.dc.html`, to be dropped into the repo by the
owner) — talking to the frozen engine through a FastAPI API. This
**activates the FastAPI layer spec §2.1 always listed** and Step 0 D1
deferred ("deferred until something real needs it — a second client");
the second client has arrived. DEVIATIONS §26 gets an addendum saying so
when the API lands.

## 1. Architecture and the extended boundary

```
engine/   (frozen, headless — pydantic models, calc, reports, export, intake)
   ▲                ▲
   │ imports        │ imports
api/      (NEW — FastAPI; serializes engine output, readable errors)
   ▲
   │ HTTP (localhost, JSON + file downloads)
frontend/ (NEW — the web UI built from design/Ironclad.dc.html)
```

**Iron Rule 1 EXTENDS to the new stack:**

- `engine/` stays FROZEN: `git log 62617f1..HEAD -- engine/` must remain
  EMPTY through this pivot. If an endpoint or screen seems to need an
  engine change, STOP and flag it as an owner decision.
- `api/` and `frontend/` import the engine; the engine never imports
  either; neither lives under `engine/`.
- The four by-design golden reds stay red (137/47 Gate 2, 33/12 Gate 3
  capital).
- The pure, browser-free `ui/` modules (`ui/reports_registry.py`,
  `ui/convert.py`, `ui/format.py`, the pure halves of `ui/state.py` and
  the tab modules' `apply_*`/composition functions) are REUSABLE by the
  API — importing them does not modify them (see Step 0 W7).

## 2. Streamlit disposition: FROZEN, not deleted

`ui/` and `app.py` are kept **runnable as the fallback** (and as the
working reference for every behavior the new stack must reproduce) until
the new front-end passes the relocated Gate 5 acceptance (§5 below).
Nothing under `ui/` or `app.py` is modified or removed in this pivot;
retirement is a separate owner-approved commit after parity. The pinned
`streamlit==1.58.0` stays in pyproject until then.

## 3. The FastAPI surface (mapping to EXISTING functions — no new math)

Every endpoint is a thin serializer over an engine/report/export/intake
function that already exists and is already tested. The API computes
nothing.

| Endpoint | Engine function(s) | Notes |
|---|---|---|
| `GET /api/properties` | scan `data/properties/` | name + path list |
| `GET /api/properties/{name}` | `load_property` | the `.icprop.json` document as JSON |
| `PUT /api/properties/{name}` | validate via `PropertyModel` + `save_property` | whole-document revalidation (the `updated_model` funnel semantics); 422 with the readable-error JSON on failure |
| `POST /api/import/rent-roll` | `import_rent_roll` | multipart xlsx → Contractual leases as JSON + `ImportResult.notes` (never a silent skip); `RentRollImportError` text verbatim in the error JSON |
| `POST /api/calculate/{name}` | `run_property` | RunResult cached SERVER-SIDE (see W4); response = compact summary (year-1 metrics, applicability flags: valuation/sensitivity/loans/resale/benchmark-CSV) |
| `GET /api/reports` | the report registry | applicable entries for the cached run |
| `GET /api/reports/{key}?unit=&period=&…` | the §7 builders (via the registry) | the builder's frame serialized (below) + meta; options (contractual_only, loan_index) as query params |
| `GET /api/audit/composition?account=&month=` | the audit composition functions | rows + caption |
| `GET /api/audit/gv-basis?month=` / `GET /api/audit/recovery-drill?…` | the two D6 panels' pure functions | the Freeport B / Cedar Alt B surfaces carry over |
| `GET /api/export/package` / `GET /api/export/report/{key}` | `build_package` / `export_report` | xlsx file responses — the Phase 4 machinery, nothing rewritten |

**Frame serialization:** `DataFrame.to_dict(orient="split")`-shaped JSON
(`columns` / `index` / `data`) with **full-precision floats** — display
formatting is the front-end's job (the Tier-1 rules — thousands
separators, accounting parens, unit decimals — port to the front-end
formatter; the API never rounds). Period indexes/labels serialize as
strings.

**§5.4 readable errors carry over, structured:** every 4xx returns

```json
{"error": {"summary": "…is not a valid PropertyModel (2 problems)",
           "problems": [{"field": "property.analysis_term_years",
                         "message": "Input should be greater than or equal to 1",
                         "got": "0"}],
           "reference": "docs/SCHEMA_GUIDE.md"}}
```

— never a pydantic dump or a traceback. Engine refusals
(NotImplementedError) return their message verbatim in `summary` (the
stale-message list still applies — surfaced as-is, engine-frozen).
Build detail: `ui/state._readable_validation_error` is refactored-by-copy
into a structured producer the API and (unchanged) Streamlit text both
derive from.

## 4. Verification discipline (carried over, stated honestly)

- **API ⇄ builder reconciliation:** every report endpoint's test
  deserializes the response and asserts the numbers EQUAL the builder's
  frame for the same toggles (the Step-6 frame-equality discipline, now
  through HTTP via FastAPI's TestClient). §25 applies: toggle changes
  must change the payload; known golden literals (Clorox NOI
  2,596,319.40; Freeport benchmark 170; the GV panel and Cedar-drill
  literals) anchor the endpoints.
- Intake/error tests: the structured error JSON carries field path +
  offending value + fix; no "Traceback"/"pydantic" anywhere in a
  response body.
- **The front-end itself is NOT cent-level unit-testable** — it renders
  what the API returns. Its correctness rests on (a) API-correctness
  (the tests above), (b) the relocated Gate 5 acceptance (§5), and
  (c) owner visual review against the mockup. Stated plainly: there is
  no §25 oracle for pixels; there IS one for every number the pixels
  show.

## 5. RELOCATED ACCEPTANCE — the new Gate 5

The Streamlit Gate 5 criteria apply unchanged to the new stack:

1. **Clorox Northlake rebuilt FROM SCRATCH through the new front-end**
   (no JSON editing) → the built model's fiscal cash flow is
   engine-to-engine **IDENTICAL** to the committed fixture output
   (§25-discriminating: any mis-entered field fails it).
2. The **Freeport load-and-drive exercise**: open the 29-lease golden,
   calculate, drill one recovery number to tenant level, export the
   package; friction points filed.
3. Audit drill-down reaches per-tenant/per-month composition for any
   account; both intake surfaces with readable errors; unit/period
   toggles honored; #11/#12 provenance; the three D6-amendment
   inspection surfaces render on the goldens.
4. `git log 62617f1..HEAD -- engine/` EMPTY.

Gate 5 remains an **owner declaration**. Streamlit retires only after it
passes (§2).

## 6. Rollout order

1. **Step 0** (below) + the owner drops `design/Ironclad.dc.html` into
   the repo.
2. **The API core**: properties/calculate/reports endpoints + the
   reconciliation test harness (TestClient) — provable without any
   front-end.
3. **The three designed screens end-to-end** — Dashboard, Reports,
   Tenants (the screens the mockup actually designed): front-end + API +
   engine proving the full path, including one editing surface (Tenants)
   and one report surface (Reports). Owner reviews against the mockup.
4. The remaining seven tabs (Property, Market, Revenues, Expenses,
   Investment, Valuation, Audit), reusing the proven patterns; the
   D6-amendment panels port with the Audit tab.
5. Intake + export surfaces wired into the front-end; the relocated
   Gate 5 run; Streamlit retirement (owner-approved).

## 7. Step 0 — owner-gated decisions (sign-off before ANY build)

- **W1 — front-end framework.** The mockup export is not in the repo yet,
  so this is a conditional recommendation to be CONFIRMED by inspecting
  `design/Ironclad.dc.html` on arrival: **if the export is a
  self-contained static HTML/CSS/JS page (the usual Claude Design export
  shape), build directly on it — static HTML + vanilla JS + `fetch()`
  against the API, no build toolchain** (a single-user local tool; no
  node/npm dependency for the owner to maintain). If the export turns
  out to be a React artifact, use Vite + React and keep the export's
  components. Named risk either way: the Tenants editing grids are the
  most interaction-heavy surface — if vanilla JS proves inadequate
  there, escalating that ONE screen to a small framework is a contained,
  flagged decision, not a silent rewrite.
- **W2 — run/launch model.** **Recommended:** one command —
  `uvicorn api.main:app` — serving the JSON API under `/api/*` and the
  front-end as static files at `/`, bound to `localhost` (a
  `scripts/run_app` convenience wrapper). No separate front-end server,
  no proxy.
- **W3 — auth.** **Recommended: none.** Single-user local tool per spec
  (§1.2 excludes multi-user/portfolio server); bind to 127.0.0.1 only.
- **W4 — RunResult serialization.** **Recommended: lazy.** `calculate`
  caches the RunResult server-side (in-process, keyed by property) and
  returns a compact summary + applicability flags; each report/audit
  endpoint reads the cached result and serializes only what that screen
  needs. Serializing a whole RunResult eagerly (a 144-month multi-tenant
  ledger + audits + schedules) is wasted payload and a maintenance
  surface.
- **W5 — Streamlit-kept-until-parity.** Confirm §2: frozen, runnable
  fallback; retirement is a separate owner-approved commit after the
  relocated Gate 5 passes.
- **W6 — the relocated acceptance.** Confirm §5 as the new Gate 5 (same
  rigor, new UI; owner-declared).
- **W7 — reuse of the pure `ui/` modules.** **Recommended:** the API
  imports the browser-free `ui/` modules as-is (registry, converters,
  pure state/audit functions) — zero duplication, `ui/` untouched;
  physically relocating them to a shared package happens in the
  Streamlit-retirement commit, not before (one move, once, when the
  fallback goes away).

**Status:** drafted 2026-07-19 on the owner's pivot decision. **Awaiting
owner review + Step 0 sign-off + the mockup file. No build until then.**
