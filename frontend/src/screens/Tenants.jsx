// The Tenants screen — the mockup's persistent split pane: the editable
// rent-roll grid left, the selected lease's detail right. Edits build a
// NEW document and PUT it whole (the API revalidates everything and
// returns structured §5.4 errors on failure; success invalidates the
// cached run). The front-end computes nothing — it reshapes the
// document the API returned.
import React, { useMemo, useState } from "react";
import { ApiError } from "../api.js";
import { EM_DASH, money } from "../format.js";

const GRID_COLUMNS = [
  ["tenant_name", "Tenant", "text"],
  ["suite", "Suite", "text"],
  ["area", "Area (SF)", "number"],
  ["lease_type", "Type", "text"],
  ["status", "Status", "text"],
  ["start_date", "Start", "text"],
  ["end_date", "End", "text"],
  ["term_months", "Term (mo)", "number"],
  ["base_rent_amount", "Rent", "number"],
  ["base_rent_unit", "Rent unit", "text"],
  ["upon_expiration", "Upon expiration", "text"],
  ["market_leasing_profile", "MLP", "text"],
];

export default function Tenants({ name, document, saveDocument, setError }) {
  const [selected, setSelected] = useState(0);
  const [edits, setEdits] = useState({});      // "row.column" -> raw text
  const [saving, setSaving] = useState(false);

  const leases = document?.rent_roll ?? [];
  const rows = useMemo(() => leases.map(flattenLease), [leases]);

  if (!document) return <div className="sub">Loading property…</div>;

  const dirty = Object.keys(edits).length > 0;

  const cellValue = (rowIndex, column) =>
    edits[`${rowIndex}.${column}`] ?? displayValue(rows[rowIndex]?.[column]);

  const onEdit = (rowIndex, column, text) =>
    setEdits((previous) => ({ ...previous,
                              [`${rowIndex}.${column}`]: text }));

  const apply = async () => {
    setSaving(true);
    setError(null);
    try {
      const nextRentRoll = leases.map((lease, i) =>
        unflattenLease(lease, i, edits));
      await saveDocument({ ...document, rent_roll: nextRentRoll });
      setEdits({});
    } catch (error) {
      setError(error instanceof ApiError ? error
               : new Error(String(error)));
    } finally {
      setSaving(false);
    }
  };

  const lease = leases[selected];

  return (
    <div>
      <h1>Tenants</h1>
      <div className="sub">
        {name} · {leases.length} leases · edits PUT the whole document
        (revalidated by the API; a save invalidates the calculated run)
      </div>
      <div className="toolbar">
        <div className="spacer" />
        <button className="action secondary" disabled={!dirty || saving}
                onClick={() => setEdits({})}>
          Discard edits
        </button>
        <button className="action" disabled={!dirty || saving}
                onClick={apply}>
          {saving ? "Saving…" : "Apply edits (PUT)"}
        </button>
      </div>
      <div className="split">
        <div className="panel scroll-x scroll-y">
          <table className="grid">
            <thead>
              <tr>
                {GRID_COLUMNS.map(([, label]) => (
                  <th key={label}>{label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i}
                    className={i === selected ? "selected clickable"
                                              : "clickable"}
                    onClick={() => setSelected(i)}>
                  {GRID_COLUMNS.map(([column, , kind]) => (
                    <td key={column}
                        className={kind === "number" ? "num" : ""}>
                      <input value={cellValue(i, column)}
                             onChange={(e) =>
                               onEdit(i, column, e.target.value)} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="panel detail">
          {lease ? <LeaseDetail lease={lease} /> :
            <div className="sub">Select a lease.</div>}
        </div>
      </div>
    </div>
  );
}

function LeaseDetail({ lease }) {
  return (
    <div>
      <h1 style={{ fontSize: 14 }}>{lease.tenant_name}</h1>
      <div className="sub">
        Suite {lease.suite ?? EM_DASH} · {lease.lease_type} ·{" "}
        {lease.status}
      </div>
      <h3>Terms</h3>
      <dl className="kv">
        <dt>Area</dt><dd>{money(lease.area)} SF</dd>
        <dt>Start</dt><dd>{lease.start_date}</dd>
        <dt>End / term</dt>
        <dd>{lease.end_date ?? `${lease.term_months} months`}</dd>
        <dt>Base rent</dt>
        <dd>{money(lease.base_rent?.amount, 2)}{" "}
            {lease.base_rent?.unit}</dd>
        <dt>Upon expiration</dt><dd>{lease.upon_expiration}</dd>
        <dt>MLP</dt><dd>{lease.market_leasing_profile ?? EM_DASH}</dd>
      </dl>
      <h3>Rent steps ({lease.rent_steps?.length ?? 0})</h3>
      {lease.rent_steps?.length ? (
        <table className="grid">
          <thead>
            <tr><th>When</th><th className="num">Amount</th>
                <th className="num">% incr.</th><th>Unit</th></tr>
          </thead>
          <tbody>
            {lease.rent_steps.map((step, i) => (
              <tr key={i}>
                <td>{step.date ?? `month ${step.month_offset}`}</td>
                <td className="num">{step.amount != null
                  ? money(step.amount, 2) : EM_DASH}</td>
                <td className="num">{step.pct_increase != null
                  ? `${step.pct_increase}%` : EM_DASH}</td>
                <td>{step.unit ?? EM_DASH}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <div className="sub">None.</div>}
      <h3>Recoveries</h3>
      <dl className="kv">
        <dt>Method</dt><dd>{lease.recoveries?.method ?? "net"}</dd>
        {lease.recoveries?.structure_ref && (
          <><dt>Structure</dt><dd>{lease.recoveries.structure_ref}</dd></>
        )}
      </dl>
      {lease.notes && (
        <>
          <h3>Notes</h3>
          <div className="sub">{lease.notes}</div>
        </>
      )}
      <h3>Rollover generations (engine-projected)</h3>
      <div className="flag">
        FLAGGED API GAP (owner decision pending): the per-generation
        rollover economics (renewal weight, blended rent, TI, LC pct/rate
        — the Freeport E inspection surface) live on the engine's
        <code> result.segments</code>, which no API endpoint exposes yet.
        Streamlit's panel reads it in-process; the web UI needs a small
        additive endpoint (e.g. <code>GET /api/tenants/generations</code>).
        Not fabricated here — awaiting approval to extend api/.
      </div>
    </div>
  );
}

// ---- flatten/unflatten (the §5.2 base-rent convention) --------------

function flattenLease(lease) {
  return {
    ...lease,
    base_rent_amount: lease.base_rent?.amount ?? null,
    base_rent_unit: lease.base_rent?.unit ?? null,
  };
}

function displayValue(value) {
  return value === null || value === undefined ? "" : String(value);
}

/** Rebuild lease `i` from its edits; blank -> null so the schema's own
    validators judge it (the API revalidates the whole document). */
function unflattenLease(lease, rowIndex, edits) {
  const next = { ...lease, base_rent: { ...lease.base_rent } };
  for (const [editKey, text] of Object.entries(edits)) {
    const [row, column] = splitKey(editKey);
    if (row !== rowIndex) continue;
    const value = text.trim() === "" ? null : coerce(column, text.trim());
    if (column === "base_rent_amount") next.base_rent.amount = value;
    else if (column === "base_rent_unit") next.base_rent.unit = value;
    else next[column] = value;
  }
  return next;
}

function splitKey(editKey) {
  const dot = editKey.indexOf(".");
  return [Number(editKey.slice(0, dot)), editKey.slice(dot + 1)];
}

const NUMERIC_COLUMNS = new Set(["area", "term_months",
                                 "base_rent_amount"]);

function coerce(column, text) {
  if (!NUMERIC_COLUMNS.has(column)) return text;
  const value = Number(text);
  // a non-numeric string passes through so the API's validator names it
  return Number.isNaN(value) ? text : value;
}
