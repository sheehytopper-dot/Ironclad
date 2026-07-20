// IronClad — the web front-end shell (rollout step 3: the three designed
// screens against the running API). The front-end computes NO financial
// numbers; nulls render as em-dashes; structured errors render readably.
import React, { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api.js";
import Dashboard from "./screens/Dashboard.jsx";
import Reports from "./screens/Reports.jsx";
import Tenants from "./screens/Tenants.jsx";

const INPUT_TABS = ["Property", "Market", "Revenues", "Expenses", "Tenants",
                    "Investment", "Valuation"];
const OUTPUT_TABS = ["Reports", "Dashboard", "Audit"];
// rollout step 3: only the three designed screens are live
const LIVE = new Set(["Dashboard", "Reports", "Tenants"]);

export default function App() {
  const [properties, setProperties] = useState([]);
  const [name, setName] = useState("");
  const [document_, setDocument] = useState(null);
  const [calc, setCalc] = useState(null);        // {summary, applicability}
  const [stale, setStale] = useState(false);
  const [screen, setScreen] = useState("Dashboard");   // D5 default-active
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.listProperties()
      .then((body) => {
        setProperties(body.properties);
        if (body.properties.length) setName(body.properties[0].name);
      })
      .catch(setError);
  }, []);

  const loadDocument = useCallback((propertyName) => {
    if (!propertyName) return;
    setError(null);
    setCalc(null);
    setStale(false);
    api.getProperty(propertyName)
      .then((body) => setDocument(body.document))
      .catch(setError);
  }, []);

  useEffect(() => { loadDocument(name); }, [name, loadDocument]);

  const calculate = useCallback(() => {
    setBusy(true);
    setError(null);
    api.calculate(name)
      .then((body) => { setCalc(body); setStale(false); })
      .catch(setError)
      .finally(() => setBusy(false));
  }, [name]);

  // a successful PUT invalidates the server-side run — mirror that here
  const saveDocument = useCallback(async (nextDocument) => {
    const body = await api.putProperty(name, nextDocument);
    const reloaded = await api.getProperty(name);
    setDocument(reloaded.document);
    setCalc(null);
    setStale(true);
    return body;
  }, [name]);

  const screenProps = { name, document: document_, calc, calculate,
                        saveDocument, setError };

  return (
    <div className="app">
      <nav className="sidebar">
        <div className="brand">IRON<span>CLAD</span></div>
        <div className="controls">
          <select value={name} onChange={(e) => setName(e.target.value)}>
            {properties.map((p) => (
              <option key={p.name} value={p.name}>{p.name}</option>
            ))}
          </select>
          <button className="calc" onClick={calculate}
                  disabled={busy || !name}>
            {busy ? "Calculating…" : "Calculate"}
          </button>
          {stale && (
            <div className="stale">
              Edited — results invalidated. Recalculate.
            </div>
          )}
        </div>
        <div className="section">Inputs</div>
        {INPUT_TABS.map((tab) => (
          <button key={tab} className={navClass(tab, screen)}
                  disabled={!LIVE.has(tab)}
                  onClick={() => setScreen(tab)}>
            {tab}{!LIVE.has(tab) ? " ·" : ""}
          </button>
        ))}
        <div className="section">Outputs</div>
        {OUTPUT_TABS.map((tab) => (
          <button key={tab} className={navClass(tab, screen)}
                  disabled={!LIVE.has(tab)}
                  onClick={() => setScreen(tab)}>
            {tab}{!LIVE.has(tab) ? " ·" : ""}
          </button>
        ))}
      </nav>
      <main className="main">
        {error && <ErrorBanner error={error} onClose={() => setError(null)} />}
        {screen === "Dashboard" && <Dashboard {...screenProps} />}
        {screen === "Reports" && <Reports {...screenProps} />}
        {screen === "Tenants" && <Tenants {...screenProps} />}
      </main>
    </div>
  );
}

function navClass(tab, screen) {
  return tab === screen ? "nav active" : "nav";
}

/** The §5.4 structured error surface — summary + per-field problems +
    the schema reference; never a raw dump. */
function ErrorBanner({ error, onClose }) {
  const problems = error instanceof ApiError ? error.problems : [];
  const reference = error instanceof ApiError ? error.reference : "";
  return (
    <div className="error-banner" onClick={onClose} title="Click to dismiss">
      <strong>{error.message}</strong>
      {problems.length > 0 && (
        <ul>
          {problems.map((p, i) => (
            <li key={i}>
              <code>{p.field}</code>: {p.message}
              {p.got != null ? ` (got ${p.got})` : ""}
            </li>
          ))}
        </ul>
      )}
      {reference && <div>Reference: {reference}</div>}
    </div>
  );
}
