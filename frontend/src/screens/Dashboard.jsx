// The Dashboard screen — KPI cards + charts + top tenants, every value
// from the API (calculate summary, executive-summary #2,
// valuation-and-return-summary #8, cash-flow #1 annual, occupancy #15,
// lease-expiration #12, lease-summary #11). Nulls render as em-dashes.
import React, { useEffect, useState } from "react";
import { api, frameRows } from "../api.js";
import { EM_DASH, isNegative, money, percent } from "../format.js";
import FrameTable from "../components/FrameTable.jsx";

const ACCENT = "#3f3d8a";
const ACCENT_2 = "#8a97c9";
const NEG = "#c0392b";
const POS = "#1f8a5b";

export default function Dashboard({ name, calc, calculate, setError }) {
  const [reports, setReports] = useState(null);

  useEffect(() => {
    if (!calc) { setReports(null); return; }
    const wanted = [
      ["exec", "executive-summary", {}],
      ["cash", "cash-flow", { period: "annual" }],
      ["occupancy", "occupancy", { period: "monthly" }],
      ["expiration", "lease-expiration", {}],
      ["tenants", "lease-summary", {}],
    ];
    if (calc.applicability?.valuation) {
      wanted.push(["valuation", "valuation-and-return-summary", {}]);
    }
    Promise.all(wanted.map(([, key, params]) =>
      api.getReport(key, name, params)))
      .then((payloads) => {
        const byName = {};
        wanted.forEach(([alias], i) => { byName[alias] = payloads[i]; });
        setReports(byName);
      })
      .catch(setError);
  }, [calc, name, setError]);

  if (!calc) {
    return (
      <div>
        <h1>Dashboard</h1>
        <div className="sub">{name}</div>
        <div className="note-banner">
          Press <strong>Calculate</strong> to populate the dashboard.
        </div>
      </div>
    );
  }
  if (!reports) return <div className="sub">Loading reports…</div>;

  const execValues = metricMap(reports.exec, "metric", "value");
  const valuation = reports.valuation
    ? metricMap(reports.valuation, "metric", "value") : {};

  const cards = [
    ["Year-1 NOI", money(calc.summary.year1_noi)],
    ["Year-1 Occupancy", percent(calc.summary.year1_occupancy_pct, 1)],
    ["Going-in Cap Rate", percent(execValues["Going-in Cap Rate (%)"], 2)],
    ["Purchase Price", money(execValues["Purchase Price"])],
    ["Unleveraged PV", money(valuation["Unleveraged PV"])],
    ["IRR (unleveraged)", percent(valuation["Unleveraged IRR (%)"], 2)],
  ];

  return (
    <div>
      <h1>Dashboard</h1>
      <div className="sub">{name} · all values from the engine via the API</div>
      <div className="kpis">
        {cards.map(([label, value]) => (
          <div className="kpi" key={label}>
            <div className="label">{label}</div>
            <div className="value">{value ?? EM_DASH}</div>
          </div>
        ))}
      </div>
      <div className="charts">
        <NoiChart cash={reports.cash} />
        <OccupancyChart occupancy={reports.occupancy} />
      </div>
      <ExpirationChart expiration={reports.expiration} />
      <div className="panel">
        <h2>Top tenants — contractual annual base rent (report #11)</h2>
        <TopTenants tenants={reports.tenants} />
      </div>
    </div>
  );
}

function metricMap(payload, keyColumn, valueColumn) {
  const { rows } = frameRows(payload?.frame);
  const map = {};
  rows.forEach((row) => { map[row[keyColumn]] = row[valueColumn]; });
  return map;
}

/** Simple SVG grouped bars — NOI + CFBDS per analysis year (#1 annual). */
function NoiChart({ cash }) {
  const frame = cash?.frame;
  if (!frame) return null;
  const noiRow = frame.index.indexOf("Net Operating Income");
  const cfRow = frame.index.indexOf("Cash Flow Before Debt Service");
  const years = frame.columns;
  const noi = frame.data[noiRow] ?? [];
  const cf = frame.data[cfRow] ?? [];
  const peak = Math.max(1, ...noi.map(absOr0), ...cf.map(absOr0));
  const width = 460; const height = 190; const base = 160;
  const group = width / years.length;
  return (
    <div className="panel">
      <h2>Annual NOI &amp; CFBDS (the ledger's own annual view)</h2>
      <svg width="100%" viewBox={`0 0 ${width} ${height}`}>
        {years.map((year, i) => {
          const x = i * group;
          return (
            <g key={String(year)}>
              <Bar x={x + group * 0.15} value={noi[i]} peak={peak}
                   base={base} width={group * 0.3} color={ACCENT} />
              <Bar x={x + group * 0.5} value={cf[i]} peak={peak}
                   base={base} width={group * 0.3} color={ACCENT_2} />
              <text x={x + group / 2} y={base + 16} textAnchor="middle"
                    fontSize="9" fill="#5a6a7e">{String(year)}</text>
            </g>
          );
        })}
      </svg>
      <div className="chart-legend">
        <span className="swatch" style={{ background: ACCENT }} /> NOI
        <span className="swatch" style={{ background: ACCENT_2 }} /> CFBDS
      </div>
    </div>
  );
}

function Bar({ x, value, peak, base, width, color }) {
  const v = value ?? 0;
  const h = Math.abs(v) / peak * (base - 20);
  const y = v >= 0 ? base - h : base;
  return <rect x={x} y={y} width={width} height={h}
               fill={v < 0 ? NEG : color} rx="1" />;
}

function absOr0(value) { return value === null ? 0 : Math.abs(value); }

/** Monthly occupancy as an SVG polyline (#15 monthly). */
function OccupancyChart({ occupancy }) {
  const { rows } = frameRows(occupancy?.frame);
  if (!rows.length) return null;
  const values = rows.map((row) => row.occupancy ?? 0);
  const width = 460; const height = 190; const base = 160;
  const step = width / Math.max(1, values.length - 1);
  const points = values
    .map((v, i) => `${(i * step).toFixed(1)},${(base - v * (base - 20)).toFixed(1)}`)
    .join(" ");
  return (
    <div className="panel">
      <h2>Occupancy (monthly)</h2>
      <svg width="100%" viewBox={`0 0 ${width} ${height}`}>
        <line x1="0" y1={base} x2={width} y2={base}
              stroke="#dbe2ec" strokeWidth="1" />
        <line x1="0" y1={base - (base - 20)} x2={width} y2={base - (base - 20)}
              stroke="#dbe2ec" strokeDasharray="3 3" strokeWidth="1" />
        <polyline points={points} fill="none" stroke={POS}
                  strokeWidth="1.6" />
        <text x="2" y={base - (base - 20) - 4} fontSize="9"
              fill="#8a97a8">100%</text>
      </svg>
      <div className="chart-legend">
        {String(rows[0].__index)} → {String(rows[rows.length - 1].__index)}
      </div>
    </div>
  );
}

/** Expiring SF by fiscal year, colored by provenance (#12). */
function ExpirationChart({ expiration }) {
  const { rows } = frameRows(expiration?.frame);
  if (!rows.length) return null;
  const years = [...new Set(rows.map((row) => row.fiscal_year))].sort();
  const bars = years.map((year) => ({
    year,
    contractual: sumWhere(rows, year, "Contractual"),
    speculative: sumWhere(rows, year, "Speculative"),
  }));
  const peak = Math.max(1, ...bars.map((b) => b.contractual + b.speculative));
  const width = 940; const height = 170; const base = 140;
  const group = width / bars.length;
  return (
    <div className="panel">
      <h2>Lease expirations — SF by fiscal year (report #12)</h2>
      <svg width="100%" viewBox={`0 0 ${width} ${height}`}>
        {bars.map((bar, i) => {
          const total = bar.contractual + bar.speculative;
          const hC = bar.contractual / peak * (base - 20);
          const hS = bar.speculative / peak * (base - 20);
          const x = i * group + group * 0.25;
          return (
            <g key={bar.year}>
              <rect x={x} y={base - hC} width={group * 0.5} height={hC}
                    fill={ACCENT} rx="1" />
              <rect x={x} y={base - hC - hS} width={group * 0.5} height={hS}
                    fill={ACCENT_2} rx="1" />
              <text x={x + group * 0.25} y={base + 14} textAnchor="middle"
                    fontSize="9" fill="#5a6a7e">{bar.year}</text>
              {total > 0 && (
                <text x={x + group * 0.25} y={base - hC - hS - 4}
                      textAnchor="middle" fontSize="8" fill="#8a97a8">
                  {money(total)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <div className="chart-legend">
        <span className="swatch" style={{ background: ACCENT }} /> Contractual
        <span className="swatch" style={{ background: ACCENT_2 }} /> Speculative
      </div>
    </div>
  );
}

function sumWhere(rows, year, status) {
  return rows
    .filter((row) => row.fiscal_year === year && row.status === status)
    .reduce((total, row) => total + (row.expiring_sf ?? 0), 0);
}

/** Top 10 tenants by contractual annual base rent (#11) — client-side
    SORT is presentation, not math. */
function TopTenants({ tenants }) {
  const { rows } = frameRows(tenants?.frame);
  const top = rows
    .filter((row) => row.status === "Contractual")
    .sort((a, b) => (b.annual_base_rent ?? 0) - (a.annual_base_rent ?? 0))
    .slice(0, 10);
  const columns = ["tenant", "suite", "area", "lease_end",
                   "annual_base_rent", "base_rent_psf_yr"];
  const frame = {
    columns,
    index: top.map((_, i) => i + 1),
    data: top.map((row) => columns.map((column) => row[column] ?? null)),
  };
  return <FrameTable frame={frame} meta={{ monetary: false }}
                     indexHeader="#" />;
}
