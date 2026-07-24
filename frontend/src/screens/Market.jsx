// The Market screen (rollout step 4): inflation as FLAT-or-VARIABLE
// per-year schedules (the owner's "variable rent growth"), custom
// indices, general vacancy, credit loss, and the MLP grid + per-MLP
// detail editor. Apply = PUT the whole document; the API revalidates.
import React, { useEffect, useState } from "react";
import { ApiError } from "../api.js";
import {
  FREE_RENT_PROFILE_COLUMNS, OVERRIDE_COLUMNS, PGR_ACCOUNTS,
  RENEWAL_RULES, RENEW_UNITS, RENT_UNITS, STEP_COLUMNS, TIMING_BASES,
  TI_UNITS, UPON_EXPIRATION, VACANCY_METHODS, YEAR_RATE_COLUMNS,
  cleanRows, deepClone, flatSchedule, isFlat, newMlpTemplate,
} from "../model.js";
import {
  Check, Field, NumInput, Optional, RecoveriesEditor, RowsEditor, Select,
  TextInput,
} from "../components/editors.jsx";

const MARKET_KEYS = ["inflation", "general_vacancy", "credit_loss",
                     "market_leasing_profiles", "free_rent_profiles"];

export default function Market({ name, document, saveDocument, setError }) {
  const [draft, setDraft] = useState(null);
  const [selectedMlp, setSelectedMlp] = useState(0);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!document) { setDraft(null); return; }
    const slice = {};
    MARKET_KEYS.forEach((key) => { slice[key] = deepClone(document[key]); });
    setDraft(slice);
  }, [document]);

  if (!document || !draft) return <div className="sub">Loading…</div>;

  const dirty = MARKET_KEYS.some((key) =>
    JSON.stringify(draft[key]) !== JSON.stringify(document[key]));

  const apply = async () => {
    setSaving(true);
    setError(null);
    try {
      await saveDocument({ ...document, ...assembleMarket(draft) });
    } catch (error) {
      setError(error instanceof ApiError ? error
               : new Error(String(error)));
    } finally {
      setSaving(false);
    }
  };

  const set = (key, value) =>
    setDraft((previous) => ({ ...previous, [key]: value }));
  const setInflation = (key, value) =>
    set("inflation", { ...draft.inflation, [key]: value });

  const mlps = draft.market_leasing_profiles ?? [];
  const structureNames =
    (document.recovery_structures ?? []).map((s) => s.name);
  const profileNames =
    (draft.free_rent_profiles ?? []).map((p) => p.name);

  return (
    <div>
      <h1>Market</h1>
      <div className="sub">
        {name} · inflation / vacancy / MLPs (§3.4-3.8) · Apply PUTs the
        whole document
      </div>
      <div className="toolbar">
        <div className="spacer" />
        <button className="action secondary" disabled={!dirty || saving}
                onClick={() => {
                  const slice = {};
                  MARKET_KEYS.forEach((key) => {
                    slice[key] = deepClone(document[key]); });
                  setDraft(slice);
                }}>
          Discard edits
        </button>
        <button className="action" disabled={!dirty || saving}
                onClick={apply}>
          {saving ? "Saving…" : "Apply edits (PUT)"}
        </button>
      </div>

      <div className="panel">
        <h2>Inflation (§3.5) — flat rate or a variable per-year schedule</h2>
        <div className="toolbar" style={{ marginBottom: 8 }}>
          <Field label="Timing basis">
            <Select value={draft.inflation.timing_basis}
                    options={TIMING_BASES} width={140}
                    onChange={(v) => setInflation("timing_basis", v)} />
          </Field>
          <Field label="Inflation month (blank = none)">
            <NumInput value={draft.inflation.inflation_month}
                      onChange={(v) =>
                        setInflation("inflation_month",
                                     v === "" ? null : v)} />
          </Field>
        </div>
        <div className="series-grid">
          <SeriesEditor label="General rate" required
                        value={draft.inflation.general_rate}
                        onChange={(v) => setInflation("general_rate", v)} />
          <SeriesEditor label="Market rent rate (blank = general)"
                        value={draft.inflation.market_rent_rate}
                        onChange={(v) =>
                          setInflation("market_rent_rate", v)} />
          <SeriesEditor label="Expense rate (blank = general)"
                        value={draft.inflation.expense_rate}
                        onChange={(v) => setInflation("expense_rate", v)} />
          <SeriesEditor label="CPI rate (blank = general)"
                        value={draft.inflation.cpi_rate}
                        onChange={(v) => setInflation("cpi_rate", v)} />
        </div>
        <h2 style={{ marginTop: 12 }}>Custom indices</h2>
        {(draft.inflation.custom_indices ?? []).map((index, i) => (
          <div key={i} className="optional">
            <div className="toolbar" style={{ marginBottom: 4 }}>
              <Field label="Index name">
                <TextInput value={index.name}
                           onChange={(v) => updateIndex(setInflation,
                             draft, i, { ...index, name: v })} />
              </Field>
              <button className="row-remove"
                      onClick={() => setInflation("custom_indices",
                        draft.inflation.custom_indices
                          .filter((_, j) => j !== i))}>
                × remove index
              </button>
            </div>
            <RowsEditor columns={YEAR_RATE_COLUMNS} rows={index.rates ?? []}
                        onChange={(rows) => updateIndex(setInflation,
                          draft, i, { ...index, rates: rows })} />
          </div>
        ))}
        <button className="row-add"
                onClick={() => setInflation("custom_indices",
                  [...(draft.inflation.custom_indices ?? []),
                   { name: "New Index", rates: [] }])}>
          + Add custom index
        </button>
      </div>

      <VacancyEditor label="General vacancy (§3.4)" withReduce
                     value={draft.general_vacancy}
                     onChange={(v) => set("general_vacancy", v)} />
      <VacancyEditor label="Credit loss (§3.4)"
                     value={draft.credit_loss}
                     onChange={(v) => set("credit_loss", v)} />

      <div className="panel">
        <h2>Market leasing profiles (§3.6) — click a row for its detail</h2>
        <table className="grid">
          <thead>
            <tr><th>Name</th><th className="num">Term</th>
                <th className="num">Renewal %</th>
                <th className="num">Vacant mo.</th>
                <th className="num">Free new</th>
                <th className="num">Free renew</th>
                <th>Upon exp.</th><th /></tr>
          </thead>
          <tbody>
            {mlps.map((mlp, i) => (
              <tr key={i} className={i === selectedMlp
                ? "selected clickable" : "clickable"}
                  onClick={() => setSelectedMlp(i)}>
                <td>{mlp.name}</td>
                <td className="num">{mlp.term_months}</td>
                <td className="num">{mlp.renewal_probability}</td>
                <td className="num">{mlp.months_vacant}</td>
                <td className="num">{mlp.free_rent_months_new ?? 0}</td>
                <td className="num">{mlp.free_rent_months_renew ?? 0}</td>
                <td>{mlp.upon_expiration ?? "market"}</td>
                <td>
                  <button className="row-remove"
                          onClick={(e) => {
                            e.stopPropagation();
                            set("market_leasing_profiles",
                                mlps.filter((_, j) => j !== i));
                            setSelectedMlp(0);
                          }}>×</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <button className="row-add"
                onClick={() => set("market_leasing_profiles",
                                   [...mlps, newMlpTemplate()])}>
          + Add profile
        </button>
        {mlps[selectedMlp] && (
          <MlpDetail mlp={mlps[selectedMlp]}
                     structureNames={structureNames}
                     profileNames={profileNames}
                     mlpNames={mlps.map((m) => m.name)}
                     onChange={(next) =>
                       set("market_leasing_profiles",
                           mlps.map((m, i) =>
                             i === selectedMlp ? next : m))} />
        )}
      </div>

      <div className="panel">
        <h2>Free-rent profiles (§3.8)</h2>
        <RowsEditor columns={FREE_RENT_PROFILE_COLUMNS}
                    rows={draft.free_rent_profiles ?? []}
                    template={{ abate_base_rent: true }}
                    onChange={(rows) => set("free_rent_profiles", rows)} />
      </div>
    </div>
  );
}

function updateIndex(setInflation, draft, i, next) {
  setInflation("custom_indices",
    draft.inflation.custom_indices.map((index, j) =>
      j === i ? next : index));
}

/** Flat-or-variable YearRate series (the owner's named need). */
function SeriesEditor({ label, value, onChange, required = false }) {
  const mode = value == null ? "default" : isFlat(value) ? "flat"
             : "variable";
  const modes = required ? ["flat", "variable"]
                         : ["default", "flat", "variable"];
  return (
    <div className="optional">
      <div className="toolbar" style={{ marginBottom: 4 }}>
        <Field label={label}>
          <Select value={mode} options={modes} width={110}
                  onChange={(next) => {
                    if (next === "default") onChange(null);
                    else if (next === "flat") {
                      onChange(flatSchedule(value?.[0]?.rate ?? 0, value));
                    } else {
                      onChange(value?.length ? value
                        : [{ year: 1, rate: 0 }]);
                    }
                  }} />
        </Field>
        {mode === "flat" && (
          <Field label="Rate % (all years)">
            <NumInput value={value[0].rate}
                      onChange={(v) => onChange(flatSchedule(v, value))} />
          </Field>
        )}
      </div>
      {mode === "variable" && (
        <RowsEditor columns={YEAR_RATE_COLUMNS} rows={value}
                    onChange={onChange} />
      )}
    </div>
  );
}

function VacancyEditor({ label, value, onChange, withReduce = false }) {
  const block = value ?? { method: "none", rate: [],
                           include_in_pgr_accounts: [],
                           tenant_overrides: [] };
  const set = (key, v) => onChange({ ...block, [key]: v });
  return (
    <div className="panel">
      <h2>{label}</h2>
      <div className="toolbar" style={{ marginBottom: 6 }}>
        <Field label="Method">
          <Select value={block.method} options={VACANCY_METHODS}
                  width={240} onChange={(v) => set("method", v)} />
        </Field>
        {withReduce && (
          <Check label="Reduce by absorption & turnover vacancy"
                 checked={block.reduce_by_absorption_turnover ?? true}
                 onChange={(v) =>
                   set("reduce_by_absorption_turnover", v)} />
        )}
      </div>
      {block.method !== "none" && (
        <>
          <h3 style={{ fontSize: 11, color: "var(--muted)" }}>
            Rate % by year</h3>
          <RowsEditor columns={YEAR_RATE_COLUMNS} rows={block.rate ?? []}
                      onChange={(rows) => set("rate", rows)} />
          <h3 style={{ fontSize: 11, color: "var(--muted)" }}>
            Included PGR accounts (percent_of_scheduled_base_plus adds)</h3>
          <div>
            {PGR_ACCOUNTS.map((account) => (
              <Check key={account} label={account}
                     checked={(block.include_in_pgr_accounts ?? [])
                       .includes(account)}
                     onChange={(on) => set("include_in_pgr_accounts",
                       on ? [...(block.include_in_pgr_accounts ?? []),
                             account]
                          : (block.include_in_pgr_accounts ?? [])
                              .filter((a) => a !== account))} />
            ))}
          </div>
          <h3 style={{ fontSize: 11, color: "var(--muted)" }}>
            Tenant overrides (exclusion)</h3>
          <RowsEditor columns={OVERRIDE_COLUMNS}
                      rows={block.tenant_overrides ?? []}
                      template={{ exclude: true }}
                      onChange={(rows) => set("tenant_overrides", rows)} />
        </>
      )}
    </div>
  );
}

/** The per-MLP drill-in detail. */
function MlpDetail({ mlp, onChange, structureNames, profileNames,
                     mlpNames }) {
  const set = (key, value) => onChange({ ...mlp, [key]: value });
  const renew = mlp.market_base_rent_renew ?? {};
  const renewIsPct = renew.pct_of_new !== undefined
    && renew.pct_of_new !== null && renew.amount === undefined;
  return (
    <div className="detail" style={{ marginTop: 10 }}>
      <h3>Detail — {mlp.name}</h3>
      <div className="toolbar" style={{ marginBottom: 4 }}>
        <Field label="Name"><TextInput value={mlp.name}
          onChange={(v) => set("name", v)} /></Field>
        <Field label="Term (mo)"><NumInput value={mlp.term_months}
          onChange={(v) => set("term_months", v)} /></Field>
        <Field label="Renewal %"><NumInput
          value={mlp.renewal_probability}
          onChange={(v) => set("renewal_probability", v)} /></Field>
        <Field label="Months vacant"><NumInput value={mlp.months_vacant}
          onChange={(v) => set("months_vacant", v)} /></Field>
        <Field label="Free mo (new)"><NumInput
          value={mlp.free_rent_months_new}
          onChange={(v) => set("free_rent_months_new", v)} /></Field>
        <Field label="Free mo (renew)"><NumInput
          value={mlp.free_rent_months_renew}
          onChange={(v) => set("free_rent_months_renew", v)} /></Field>
      </div>
      <div className="toolbar" style={{ marginBottom: 4 }}>
        <Field label="Market rent (new)"><NumInput
          value={mlp.market_base_rent_new?.amount}
          onChange={(v) => set("market_base_rent_new",
            { ...mlp.market_base_rent_new, amount: v })} /></Field>
        <Field label="Unit"><Select
          value={mlp.market_base_rent_new?.unit} options={RENT_UNITS}
          onChange={(v) => set("market_base_rent_new",
            { ...mlp.market_base_rent_new, unit: v })} /></Field>
        <Field label="Renew basis"><Select
          value={renewIsPct ? "pct_of_new" : "amount"}
          options={["pct_of_new", "amount"]} width={110}
          onChange={(v) => set("market_base_rent_renew",
            v === "pct_of_new" ? { pct_of_new: 100.0 }
            : { amount: 0.0, unit: "dollars_per_area_per_year" })} />
        </Field>
        {renewIsPct ? (
          <Field label="Renew % of new"><NumInput value={renew.pct_of_new}
            onChange={(v) => set("market_base_rent_renew",
              { pct_of_new: v })} /></Field>
        ) : (
          <>
            <Field label="Renew amount"><NumInput value={renew.amount}
              onChange={(v) => set("market_base_rent_renew",
                { ...renew, amount: v })} /></Field>
            <Field label="Renew unit"><Select value={renew.unit}
              options={RENEW_UNITS}
              onChange={(v) => set("market_base_rent_renew",
                { ...renew, unit: v })} /></Field>
          </>
        )}
      </div>
      <div className="toolbar" style={{ marginBottom: 4 }}>
        <MoneyRateField label="TI (new)" value={mlp.ti_new}
                        onChange={(v) => set("ti_new", v)} />
        <MoneyRateField label="TI (renew)" value={mlp.ti_renew}
                        onChange={(v) => set("ti_renew", v)} />
        <Field label="LC new (% of rent)"><NumInput
          value={mlp.lc_new?.pct}
          onChange={(v) => set("lc_new", v === "" ? null : { pct: v })} />
        </Field>
        <Field label="LC renew (% of rent)"><NumInput
          value={mlp.lc_renew?.pct}
          onChange={(v) =>
            set("lc_renew", v === "" ? null : { pct: v })} /></Field>
      </div>
      <div className="toolbar" style={{ marginBottom: 4 }}>
        <Field label="Upon expiration"><Select
          value={mlp.upon_expiration ?? "market"} options={UPON_EXPIRATION}
          width={110} onChange={(v) => set("upon_expiration", v)} /></Field>
        <Field label="Intelligent renewals"><Select
          value={mlp.intelligent_renewals ?? "market"}
          options={RENEWAL_RULES} width={110}
          onChange={(v) => set("intelligent_renewals", v)} /></Field>
        <Check label="Term growth" checked={mlp.term_growth ?? true}
               onChange={(v) => set("term_growth", v)} />
        <Field label="Free-rent profile"><Select
          value={mlp.free_rent_profile} options={profileNames} blank
          onChange={(v) => set("free_rent_profile", v)} /></Field>
        <Field label="Chained profile"><Select
          value={mlp.chained_profile} options={mlpNames} blank
          onChange={(v) => set("chained_profile", v)} /></Field>
      </div>
      <h3>Speculative-term recoveries</h3>
      <RecoveriesEditor value={mlp.recoveries}
                        structureNames={structureNames}
                        onChange={(v) => set("recoveries", v)} />
      <h3>Rent increases (steps)</h3>
      <RowsEditor columns={STEP_COLUMNS} rows={mlp.rent_increases ?? []}
                  onChange={(rows) =>
                    set("rent_increases", rows.length ? rows : null)} />
    </div>
  );
}

function MoneyRateField({ label, value, onChange }) {
  return (
    <>
      <Field label={`${label} amount (blank = none)`}>
        <NumInput value={value?.amount}
                  onChange={(v) => onChange(v === "" ? null
                    : { amount: v,
                        unit: value?.unit ?? "dollars_per_area" })} />
      </Field>
      {value != null && (
        <Field label={`${label} unit`}>
          <Select value={value.unit} options={TI_UNITS} width={130}
                  onChange={(v) => onChange({ ...value, unit: v })} />
        </Field>
      )}
    </>
  );
}

/** Draft slice -> model slice: coerce the editable collections. */
export function assembleMarket(draft) {
  const out = deepClone(draft);
  const inflation = out.inflation;
  inflation.inflation_month = numberish(inflation.inflation_month);
  for (const key of ["general_rate", "market_rent_rate", "expense_rate",
                     "cpi_rate"]) {
    if (inflation[key] != null) {
      inflation[key] = cleanRows(inflation[key], YEAR_RATE_COLUMNS);
      if (!inflation[key].length && key !== "general_rate") {
        inflation[key] = null;
      }
    }
  }
  inflation.custom_indices = (inflation.custom_indices ?? [])
    .filter((index) => (index.name ?? "").trim())
    .map((index) => ({ name: index.name,
                       rates: cleanRows(index.rates ?? [],
                                        YEAR_RATE_COLUMNS) }));
  for (const key of ["general_vacancy", "credit_loss"]) {
    const block = out[key];
    if (!block) continue;
    block.rate = cleanRows(block.rate ?? [], YEAR_RATE_COLUMNS);
    block.tenant_overrides = cleanRows(block.tenant_overrides ?? [],
                                       OVERRIDE_COLUMNS);
  }
  out.market_leasing_profiles = (out.market_leasing_profiles ?? [])
    .map(assembleMlp);
  out.free_rent_profiles = cleanRows(out.free_rent_profiles ?? [],
                                     FREE_RENT_PROFILE_COLUMNS);
  return out;
}

function assembleMlp(mlp) {
  const next = coerceNumbersShallow(deepClone(mlp));
  if (next.rent_increases) {
    next.rent_increases = cleanRows(next.rent_increases, STEP_COLUMNS);
    if (!next.rent_increases.length) next.rent_increases = null;
  }
  return next;
}

function numberish(value) {
  if (value === "" || value === null || value === undefined) return null;
  const number = Number(value);
  return Number.isNaN(number) ? value : number;
}

function coerceNumbersShallow(value) {
  if (typeof value === "string" && value !== "" &&
      !Number.isNaN(Number(value))) return Number(value);
  if (Array.isArray(value)) return value.map(coerceNumbersShallow);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value)
      .map(([key, item]) => [key, coerceNumbersShallow(item)]));
  }
  return value;
}
