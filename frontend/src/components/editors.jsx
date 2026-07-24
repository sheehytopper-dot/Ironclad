// Shared drill-in editor building blocks (rollout step 4). Pure
// presentation over PropertyModel JSON — assembly rules live in
// src/model.js; validation is the API's (PUT the whole document).
import React from "react";
import { RECOVERY_METHODS } from "../model.js";

/** label + any input */
export function Field({ label, children }) {
  return (
    <div>
      <label>{label}</label>
      {children}
    </div>
  );
}

export function TextInput({ value, onChange, width = 130 }) {
  return <input type="text" style={{ width }}
                className="editor-input"
                value={value ?? ""}
                onChange={(e) => onChange(e.target.value)} />;
}

export function NumInput({ value, onChange, width = 90 }) {
  return <input type="text" inputMode="decimal" style={{ width }}
                className="editor-input num"
                value={value ?? ""}
                onChange={(e) => onChange(e.target.value)} />;
}

export function Select({ value, onChange, options, blank = false,
                         width = 170 }) {
  return (
    <select className="editor-input" style={{ width }} value={value ?? ""}
            onChange={(e) => onChange(e.target.value || null)}>
      {blank && <option value="">—</option>}
      {options.map((option) => (
        <option key={String(option)} value={option}>{String(option)}</option>
      ))}
    </select>
  );
}

export function Check({ label, checked, onChange }) {
  return (
    <label className="check">
      <input type="checkbox" checked={!!checked}
             onChange={(e) => onChange(e.target.checked)} /> {label}
    </label>
  );
}

/** An enable/disable wrapper: unchecked -> the value is null. */
export function Optional({ label, value, template, onChange, children }) {
  return (
    <div className="optional">
      <Check label={label} checked={value !== null && value !== undefined}
             onChange={(on) => onChange(on ? (value ?? template) : null)} />
      {value !== null && value !== undefined && children}
    </div>
  );
}

/** The generic editable grid: configured columns, add/remove rows,
    unconfigured keys preserved (nested detail survives). */
export function RowsEditor({ columns, rows, onChange, template = {} }) {
  const update = (rowIndex, key, value) => {
    const next = rows.map((row, i) =>
      i === rowIndex ? { ...row, [key]: value } : row);
    onChange(next);
  };
  return (
    <div className="scroll-x">
      <table className="grid">
        <thead>
          <tr>
            {columns.map(({ key, label }) => <th key={key}>{label}</th>)}
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map(({ key, kind, options }) => (
                <td key={key} className={kind === "number" ? "num" : ""}>
                  {kind === "select" ? (
                    <Select value={row[key]} options={options} blank
                            width="100%"
                            onChange={(value) => update(i, key, value)} />
                  ) : kind === "bool" ? (
                    <input type="checkbox" checked={!!row[key]}
                           onChange={(e) =>
                             update(i, key, e.target.checked)} />
                  ) : (
                    <input value={row[key] ?? ""}
                           onChange={(e) =>
                             update(i, key, e.target.value)} />
                  )}
                </td>
              ))}
              <td>
                <button className="row-remove" title="Remove row"
                        onClick={() =>
                          onChange(rows.filter((_, j) => j !== i))}>
                  ×
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button className="row-add"
              onClick={() => onChange([...rows, { ...template }])}>
        + Add row
      </button>
    </div>
  );
}

/** The RecoveryAssignment editor — shared by lease detail and MLP detail
    (§3.7: system method + refs). */
export function RecoveriesEditor({ value, onChange, structureNames }) {
  const rec = value ?? { method: "net" };
  const set = (key, v) => onChange({ ...rec, [key]: v });
  return (
    <div className="toolbar" style={{ marginBottom: 0 }}>
      <Field label="Method">
        <Select value={rec.method} options={RECOVERY_METHODS}
                onChange={(v) => set("method", v)} width={130} />
      </Field>
      <Field label="Stop $/SF">
        <NumInput value={rec.stop_amount_per_area}
                  onChange={(v) => set("stop_amount_per_area",
                                       v === "" ? null : v)} />
      </Field>
      <Field label="Base year">
        <NumInput value={rec.base_year}
                  onChange={(v) => set("base_year", v === "" ? null : v)} />
      </Field>
      <Field label="Gross-up %">
        <NumInput value={rec.base_year_gross_up_pct}
                  onChange={(v) => set("base_year_gross_up_pct",
                                       v === "" ? null : v)} />
      </Field>
      <Field label="Fixed $/SF">
        <NumInput value={rec.fixed_amount_per_area}
                  onChange={(v) => set("fixed_amount_per_area",
                                       v === "" ? null : v)} />
      </Field>
      <Field label="Structure">
        <Select value={rec.structure_ref} options={structureNames} blank
                onChange={(v) => set("structure_ref", v)} />
      </Field>
    </div>
  );
}
