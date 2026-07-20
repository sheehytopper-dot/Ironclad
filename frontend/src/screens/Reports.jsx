// The Reports screen — picker from GET /api/reports, unit/period
// toggles, the dense frame table (Cash Flow rendered with the
// meta.extra.tree account hierarchy), export buttons hitting
// /api/export/*. The on-screen numbers ARE the API payload (display
// formatting only).
import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import FrameTable from "../components/FrameTable.jsx";

const UNITS = ["total", "per_sf", "per_month", "per_occupied_sf"];
const PERIODS = ["monthly", "quarterly", "annual", "fiscal"];

export default function Reports({ name, calc, setError }) {
  const [entries, setEntries] = useState([]);
  const [key, setKey] = useState("");
  const [unit, setUnit] = useState("total");
  const [period, setPeriod] = useState("fiscal");
  const [contractualOnly, setContractualOnly] = useState(false);
  const [payload, setPayload] = useState(null);

  useEffect(() => {
    if (!calc) { setEntries([]); setPayload(null); return; }
    api.listReports(name)
      .then((body) => {
        setEntries(body.reports);
        if (body.reports.length && !body.reports.some((e) => e.key === key)) {
          setKey(body.reports[0].key);
        }
      })
      .catch(setError);
  }, [calc, name]);          // eslint-disable-line react-hooks/exhaustive-deps

  const entry = entries.find((e) => e.key === key);

  useEffect(() => {
    if (!entry || !calc) return;
    const params = {};
    if (entry.supports_unit) params.unit = unit;
    if (entry.supports_period) params.period = period;
    if (entry.number === 11 || entry.number === 12) {
      params.contractual_only = contractualOnly;
    }
    api.getReport(entry.key, name, params)
      .then(setPayload)
      .catch(setError);
  }, [entry, unit, period, contractualOnly, name, calc, setError]);

  if (!calc) {
    return (
      <div>
        <h1>Reports</h1>
        <div className="sub">{name}</div>
        <div className="note-banner">
          Press <strong>Calculate</strong> to render reports.
        </div>
      </div>
    );
  }

  const exportParams = {};
  if (entry?.supports_unit) exportParams.unit = unit;
  if (entry?.supports_period) exportParams.period = period;

  return (
    <div>
      <h1>Reports</h1>
      <div className="sub">{name} · spec §7 catalog via the API</div>
      <div className="toolbar">
        <div>
          <label>Report</label>
          <select value={key} onChange={(e) => setKey(e.target.value)}>
            {entries.map((e) => (
              <option key={e.key} value={e.key}>
                #{e.number} {e.label}
              </option>
            ))}
          </select>
        </div>
        {entry?.supports_unit && (
          <div>
            <label>Unit ($)</label>
            <select value={unit} onChange={(e) => setUnit(e.target.value)}>
              {UNITS.map((u) => <option key={u}>{u}</option>)}
            </select>
          </div>
        )}
        {entry?.supports_period && (
          <div>
            <label>Period</label>
            <select value={period}
                    onChange={(e) => setPeriod(e.target.value)}>
              {PERIODS.map((p) => <option key={p}>{p}</option>)}
            </select>
          </div>
        )}
        {(entry?.number === 11 || entry?.number === 12) && (
          <div>
            <label>Scope</label>
            <select value={contractualOnly ? "contractual" : "all"}
                    onChange={(e) =>
                      setContractualOnly(e.target.value === "contractual")}>
              <option value="all">All tenancy (with provenance)</option>
              <option value="contractual">Contractual only</option>
            </select>
          </div>
        )}
        <div className="spacer" />
        <button className="action secondary"
                onClick={() => window.open(
                  api.exportReportUrl(entry.key, name, exportParams))}>
          Export this view
        </button>
        <button className="action"
                onClick={() => window.open(api.exportPackageUrl(name))}>
          Export §8 package
        </button>
      </div>
      {entry?.note && <div className="sub">{entry.note}</div>}
      {payload?.meta?.extra?.miss_count !== undefined && (
        <div className="note-banner">
          Line-years beyond tolerance:{" "}
          <strong>{payload.meta.extra.miss_count}</strong>
          {payload.meta.extra.skipped_accounts?.length > 0 &&
            ` · skipped (no ledger line match): ${
              payload.meta.extra.skipped_accounts.join(", ")}`}
        </div>
      )}
      {payload && (
        <div className="panel">
          <FrameTable frame={payload.frame} meta={payload.meta}
                      tree={payload.meta?.extra?.tree ?? null}
                      indexHeader={payload.meta?.extra?.tree
                        ? "Account" : ""} />
        </div>
      )}
    </div>
  );
}
