// IronClad front-end (NEXT_STEPS_WEB_FRONTEND.md, rollout step 3).
// Dev run model (Step 0 W2): the Vite dev server PROXIES /api to the
// locally running FastAPI (uvicorn api.main:app --port 8000) — no CORS.
// Production: `npm run build` emits static files; serving them from
// uvicorn (StaticFiles mount at /) is a flagged api/ addition, pending.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
