// The Tenants screen (rollout step 4 — FULLY drill-in editable): the
// rent-roll grid left; clicking a row opens THAT lease's complete nested
// editor right (rent steps, CPI, free rent, misc items, recoveries,
// TI/LC, security deposit, upon-expiration + MLP link). Apply = PUT the
// whole document (the API revalidates; 422 problems render per-field);
// the rollover-generations panel reads the owner-approved
// /api/tenants/generations endpoint. The front-end computes NO numbers.
import React, { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api.js";
import { EM_DASH, money } from "../format.js";
import {
  CPI_METHODS, DEPOSIT_UNITS, LEASE_STATUSES, LEASE_TYPES,
  MISC_ITEM_COLUMNS, RENT_UNITS, STEP_COLUMNS, TI_UNITS, UPON_EXPIRATION,
  cleanRows, deepClone,
} from "../model.js";
import {
  Check, Field, NumInput, Optional, RecoveriesEditor, RowsEditor, Select,
  TextInput,
} from "../components/editors.jsx";

const GRID_COLUMNS = [
  ["tenant_name", "Tenant"], ["suite", "Suite"], ["area", "Area (SF)"],
  ["lease_type", "Type"], ["status", "Status"], ["start_date", "Start"],
  ["end_date", "End"], ["term_months", "Term"],
  ["base_rent_amount", "Rent"], ["base_rent_unit", "Rent unit"],
  ["upon_expiration", "Upon exp."], ["market_leasing_profile", "MLP"],
];

export default function Tenants({ name, document, calc, saveDocument,
                                  setError }) {
  const [selected, setSelected] = useState(0);
  const [draft, setDraft] = useState(null);     // deep copy of the lease
  const [saving, setSaving] = useState(false);

  const leases = document?.rent_roll ?? [];
  const mlpNames = useMemo(
    () => (document?.market_leasing_profiles ?? []).map((p) => p.name),
    [document]);
  const structureNames = useMemo(
    () => (document?.recovery_structures ?? []).map((s) => s.name),
    [document]);
  const profileNames = useMemo(
    () => (document?.free_rent_profiles ?? []).map((p) => p.name),
    [document]);

  useEffect(() => {                     // (re)load the draft on selection
    setDraft(leases[selected] ? deepClone(leases[selected]) : null);
  }, [document, selected]);             // eslint-disable-line

  if (!document) return <div className="sub">Loading property…</div>;

  const dirty = draft && leases[selected] &&
    JSON.stringify(draft) !== JSON.stringify(leases[selected]);

  const apply = async () => {
    setSaving(true);
    setError(null);
    try {
      const nextRentRoll = leases.map((lease, i) =>
        i === selected ? assembleLease(draft) : lease);
      await saveDocument({ ...document, rent_roll: nextRentRoll });
    } catch (error) {
      setError(error instanceof ApiError ? error
               : new Error(String(error)));
    } finally {
      setSaving(false);
    }
  };

  const addLease = async () => {
    const template = {
      tenant_name: "New Tenant", area: 1000, lease_type: "office",
      start_date: "2026-01-01", term_months: 60,
      base_rent: { amount: 0.0, unit: "dollars_per_area_per_year" },
      upon_expiration: "vacate",
    };
    try {
      await saveDocument({ ...document,
                           rent_roll: [...leases, template] });
      setSelected(leases.length);
    } catch (error) { setError(error); }
  };

  const removeLease = async () => {
    try {
      await saveDocument({
        ...document,
        rent_roll: leases.filter((_, i) => i !== selected) });
      setSelected(0);
    } catch (error) { setError(error); }
  };

  return (
    <div>
      <h1>Tenants</h1>
      <div className="sub">
        {name} · {leases.length} leases · click a row to edit its full
        detail; Apply PUTs the whole document (API-revalidated)
      </div>
      <div className="toolbar">
        <button className="action secondary" onClick={addLease}>
          + Add lease
        </button>
        <button className="action secondary" onClick={removeLease}
                disabled={!leases.length}>
          Remove selected
        </button>
        <div className="spacer" />
        <button className="action secondary" disabled={!dirty || saving}
                onClick={() => setDraft(deepClone(leases[selected]))}>
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
              <tr>{GRID_COLUMNS.map(([, label]) =>
                <th key={label}>{label}</th>)}</tr>
            </thead>
            <tbody>
              {leases.map((lease, i) => {
                const row = i === selected && draft ? draft : lease;
                return (
                  <tr key={i} className={i === selected
                    ? "selected clickable" : "clickable"}
                      onClick={() => setSelected(i)}>
                    <td>{row.tenant_name}</td>
                    <td>{row.suite ?? EM_DASH}</td>
                    <td className="num">{money(row.area)}</td>
                    <td>{row.lease_type}</td>
                    <td>{row.status ?? "contract"}</td>
                    <td>{row.start_date}</td>
                    <td>{row.end_date ?? EM_DASH}</td>
                    <td className="num">{row.term_months ?? EM_DASH}</td>
                    <td className="num">
                      {money(row.base_rent?.amount, 2)}
                    </td>
                    <td>{row.base_rent?.unit}</td>
                    <td>{row.upon_expiration}</td>
                    <td>{row.market_leasing_profile ?? EM_DASH}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="panel detail scroll-y">
          {draft ? (
            <LeaseEditor draft={draft} setDraft={setDraft}
                         mlpNames={mlpNames}
                         structureNames={structureNames}
                         profileNames={profileNames} />
          ) : <div className="sub">Select a lease.</div>}
          {draft && (
            <Generations name={name} calc={calc}
                         tenant={leases[selected]?.tenant_name} />
          )}
        </div>
      </div>
    </div>
  );
}

/** The complete nested lease editor over the draft copy. */
function LeaseEditor({ draft, setDraft, mlpNames, structureNames,
                       profileNames }) {
  const set = (key, value) =>
    setDraft((previous) => ({ ...previous, [key]: value }));
  const setRent = (key, value) =>
    setDraft((previous) => ({
      ...previous,
      base_rent: { ...previous.base_rent, [key]: value } }));

  return (
    <div>
      <h1 style={{ fontSize: 14 }}>{draft.tenant_name}</h1>
      <h3>Identity &amp; term</h3>
      <div className="toolbar" style={{ marginBottom: 4 }}>
        <Field label="Tenant"><TextInput value={draft.tenant_name}
          onChange={(v) => set("tenant_name", v)} /></Field>
        <Field label="Suite"><TextInput value={draft.suite} width={60}
          onChange={(v) => set("suite", v || null)} /></Field>
        <Field label="Area (SF)"><NumInput value={draft.area}
          onChange={(v) => set("area", v)} /></Field>
        <Field label="Type"><Select value={draft.lease_type}
          options={LEASE_TYPES} width={100}
          onChange={(v) => set("lease_type", v)} /></Field>
        <Field label="Status"><Select value={draft.status ?? "contract"}
          options={LEASE_STATUSES} width={110}
          onChange={(v) => set("status", v)} /></Field>
      </div>
      <div className="toolbar" style={{ marginBottom: 4 }}>
        <Field label="Start (YYYY-MM-DD)"><TextInput
          value={draft.start_date} width={110}
          onChange={(v) => set("start_date", v)} /></Field>
        <Field label="End (or blank)"><TextInput value={draft.end_date}
          width={110}
          onChange={(v) => set("end_date", v || null)} /></Field>
        <Field label="…or term (months)"><NumInput
          value={draft.term_months}
          onChange={(v) => set("term_months", v === "" ? null : v)} />
        </Field>
      </div>
      <div className="toolbar" style={{ marginBottom: 4 }}>
        <Field label="Base rent"><NumInput
          value={draft.base_rent?.amount}
          onChange={(v) => setRent("amount", v)} /></Field>
        <Field label="Unit"><Select value={draft.base_rent?.unit}
          options={RENT_UNITS}
          onChange={(v) => setRent("unit", v)} /></Field>
        <Field label="Upon expiration"><Select
          value={draft.upon_expiration} options={UPON_EXPIRATION}
          width={110} onChange={(v) => set("upon_expiration", v)} /></Field>
        <Field label="MLP"><Select value={draft.market_leasing_profile}
          options={mlpNames} blank
          onChange={(v) => set("market_leasing_profile", v)} /></Field>
      </div>

      <h3>Rent steps</h3>
      <RowsEditor columns={STEP_COLUMNS} rows={draft.rent_steps ?? []}
                  onChange={(rows) => set("rent_steps", rows)} />

      <h3>CPI</h3>
      <Optional label="CPI adjustments" value={draft.cpi}
                template={{ method: "full_cpi",
                            first_increase_month: "anniversary",
                            frequency_months: 12 }}
                onChange={(v) => set("cpi", v)}>
        <div className="toolbar" style={{ marginBottom: 0 }}>
          <Field label="Method"><Select value={draft.cpi?.method}
            options={CPI_METHODS} width={130}
            onChange={(v) => setSub(setDraft, "cpi", "method", v)} /></Field>
          <Field label="Pct (of/plus)"><NumInput value={draft.cpi?.pct}
            onChange={(v) =>
              setSub(setDraft, "cpi", "pct", v === "" ? null : v)} /></Field>
          <Field label="First increase (# / anniversary)"><TextInput
            value={draft.cpi?.first_increase_month} width={90}
            onChange={(v) =>
              setSub(setDraft, "cpi", "first_increase_month",
                     /^\d+$/.test(v) ? Number(v) : v)} /></Field>
          <Field label="Every (months)"><NumInput
            value={draft.cpi?.frequency_months} width={60}
            onChange={(v) =>
              setSub(setDraft, "cpi", "frequency_months", v)} /></Field>
          <Field label="Cap %"><NumInput value={draft.cpi?.cap_pct}
            onChange={(v) =>
              setSub(setDraft, "cpi", "cap_pct",
                     v === "" ? null : v)} /></Field>
          <Field label="Floor %"><NumInput value={draft.cpi?.floor_pct}
            onChange={(v) =>
              setSub(setDraft, "cpi", "floor_pct",
                     v === "" ? null : v)} /></Field>
        </div>
      </Optional>

      <h3>Free rent</h3>
      <Optional label="Free rent" value={draft.free_rent}
                template={{ months: 0, timing: "front" }}
                onChange={(v) => set("free_rent", v)}>
        <div className="toolbar" style={{ marginBottom: 0 }}>
          <Field label="Months"><NumInput value={draft.free_rent?.months}
            onChange={(v) => setSub(setDraft, "free_rent", "months", v)} />
          </Field>
          <Field label="Timing"><Select value={draft.free_rent?.timing}
            options={["front", "custom"]} width={90}
            onChange={(v) => setSub(setDraft, "free_rent", "timing", v)} />
          </Field>
          <Field label="Custom months (1,13,…)"><TextInput
            value={(draft.free_rent?.custom_months ?? []).join(",")}
            onChange={(v) => setSub(setDraft, "free_rent", "custom_months",
              v.trim() ? v.split(",").map((s) => Number(s.trim()))
                       : null)} /></Field>
          <Field label="Profile"><Select value={draft.free_rent?.profile}
            options={profileNames} blank
            onChange={(v) => setSub(setDraft, "free_rent", "profile", v)} />
          </Field>
        </div>
      </Optional>

      <h3>Miscellaneous items</h3>
      <RowsEditor columns={MISC_ITEM_COLUMNS}
                  rows={draft.miscellaneous_items ?? []}
                  template={{ free_rent_abates: false }}
                  onChange={(rows) =>
                    set("miscellaneous_items", rows)} />

      <h3>Recoveries</h3>
      <RecoveriesEditor value={draft.recoveries}
                        structureNames={structureNames}
                        onChange={(v) => set("recoveries", v)} />

      <h3>Contract-term TI / LC</h3>
      <Optional label="Leasing costs" value={draft.leasing_costs}
                template={{}}
                onChange={(v) => set("leasing_costs", v)}>
        <div className="toolbar" style={{ marginBottom: 0 }}>
          <Field label="TI amount"><NumInput
            value={draft.leasing_costs?.ti?.amount}
            onChange={(v) =>
              setSub(setDraft, "leasing_costs", "ti",
                     v === "" ? null
                     : { amount: v,
                         unit: draft.leasing_costs?.ti?.unit
                               ?? "dollars_per_area" })} /></Field>
          <Field label="TI unit"><Select
            value={draft.leasing_costs?.ti?.unit ?? "dollars_per_area"}
            options={TI_UNITS} width={130}
            onChange={(v) => setSub(setDraft, "leasing_costs", "ti",
              { ...(draft.leasing_costs?.ti ?? { amount: 0 }),
                unit: v })} /></Field>
          <Field label="LC % of rent"><NumInput
            value={draft.leasing_costs?.lc?.pct}
            onChange={(v) =>
              setSub(setDraft, "leasing_costs", "lc",
                     v === "" ? null : { pct: v })} /></Field>
        </div>
      </Optional>

      <h3>Security deposit</h3>
      <Optional label="Security deposit" value={draft.security_deposit}
                template={{ amount: 0, unit: "months_of_rent",
                            refunded_at_expiration: true }}
                onChange={(v) => set("security_deposit", v)}>
        <div className="toolbar" style={{ marginBottom: 0 }}>
          <Field label="Amount"><NumInput
            value={draft.security_deposit?.amount}
            onChange={(v) =>
              setSub(setDraft, "security_deposit", "amount", v)} /></Field>
          <Field label="Unit"><Select
            value={draft.security_deposit?.unit} options={DEPOSIT_UNITS}
            width={140}
            onChange={(v) =>
              setSub(setDraft, "security_deposit", "unit", v)} /></Field>
          <Check label="Refunded at expiration"
                 checked={draft.security_deposit?.refunded_at_expiration}
                 onChange={(v) =>
                   setSub(setDraft, "security_deposit",
                          "refunded_at_expiration", v)} />
        </div>
      </Optional>
      {draft.notes && (
        <>
          <h3>Notes</h3>
          <div className="sub">{draft.notes}</div>
        </>
      )}
    </div>
  );
}

function setSub(setDraft, section, key, value) {
  setDraft((previous) => ({
    ...previous,
    [section]: { ...(previous[section] ?? {}), [key]: value } }));
}

/** Draft -> model lease: coerce the editable collections (blank -> null,
    numbers), preserving everything else as-is for the API to judge. */
function assembleLease(draft) {
  const lease = deepClone(draft);
  lease.area = numberish(lease.area);
  lease.term_months = numberish(lease.term_months);
  if (lease.base_rent) lease.base_rent.amount =
    numberish(lease.base_rent.amount);
  lease.rent_steps = cleanRows(lease.rent_steps ?? [], STEP_COLUMNS);
  lease.miscellaneous_items = cleanRows(lease.miscellaneous_items ?? [],
                                        MISC_ITEM_COLUMNS);
  for (const key of ["cpi", "free_rent", "security_deposit",
                     "recoveries"]) {
    if (lease[key]) lease[key] = coerceNumbers(lease[key]);
  }
  if (lease.leasing_costs && lease.leasing_costs.ti === null &&
      lease.leasing_costs.lc === null) {
    // an empty TI/LC block means "none"
    const { ti_category, lc_category } = lease.leasing_costs;
    if (!ti_category && !lc_category) lease.leasing_costs = null;
  }
  if (lease.leasing_costs) lease.leasing_costs =
    coerceNumbers(lease.leasing_costs);
  return lease;
}

function numberish(value) {
  if (value === "" || value === null || value === undefined) return null;
  const number = Number(value);
  return Number.isNaN(number) ? value : number;
}

/** Recursively coerce numeric-looking strings the inputs produced. */
function coerceNumbers(value) {
  if (typeof value === "string" && value !== "" &&
      !Number.isNaN(Number(value))) return Number(value);
  if (Array.isArray(value)) return value.map(coerceNumbers);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value)
      .map(([key, item]) => [key, coerceNumbers(item)]));
  }
  return value;
}

/** The Freeport E surface, now live over HTTP. */
function Generations({ name, calc, tenant }) {
  const [rows, setRows] = useState(null);
  useEffect(() => {
    setRows(null);
    if (!calc || !tenant) return;
    api.generations(name, tenant)
      .then((body) => setRows(body.rows))
      .catch(() => setRows(null));
  }, [name, calc, tenant]);
  return (
    <div>
      <h3>Rollover generations (engine-projected — read-only)</h3>
      {!calc ? (
        <div className="sub">Calculate to view the projected
          rollover/absorption generations for this lease.</div>
      ) : !rows ? (
        <div className="sub">No resolved chain in the last run
          (recalculate after edits).</div>
      ) : (
        <table className="grid">
          <thead>
            <tr><th>Start</th><th>End</th><th>Provenance</th>
                <th className="num">Weight</th>
                <th className="num">Rent/mo</th>
                <th className="num">Free</th><th>TI</th><th>LC</th></tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                <td>{row.start}</td><td>{row.end}</td>
                <td>{row.provenance}</td>
                <td className="num">{row.renewal_weight ?? EM_DASH}</td>
                <td className="num">
                  {row.initial_rent_monthly != null
                    ? money(row.initial_rent_monthly, 2) : EM_DASH}
                </td>
                <td className="num">{row.free_rent_months ?? EM_DASH}</td>
                <td>{row.ti || EM_DASH}</td>
                <td>{row.lc || EM_DASH}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
