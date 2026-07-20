// The dense hairline table over a split-orient API frame. Values are the
// API's (full precision); formatting is display-only (src/format.js).
// For Cash Flow, `tree` (meta.extra.tree from the API) drives the
// account indentation, bold subtotals, and grand-total rules.
import React from "react";
import { cell, isNegative, money, unitDecimals } from "../format.js";

export default function FrameTable({ frame, meta = {}, tree = null,
                                     indexHeader = "" }) {
  if (!frame) return null;
  const monetary = meta.monetary ?? false;
  const decimals = monetary ? unitDecimals(meta.unit) : 0;

  const rowClass = (rowIndex) => {
    if (!tree) return "";
    const node = tree[rowIndex];
    if (!node) return "";
    if (node.grand_total) return "grand";
    if (node.is_subtotal) return "subtotal";
    return "";
  };
  const indexLabel = (label, rowIndex) => {
    if (!tree) return label;
    const node = tree[rowIndex];
    const pad = node ? " ".repeat(4 * node.level) : "";
    return pad + label;
  };
  const formatCell = (value, columnName) => {
    if (value === null || value === undefined) return "—";
    if (typeof value !== "number") return String(value);
    return monetary ? money(value, decimals) : cell(value, columnName);
  };

  return (
    <div className="scroll-x scroll-y">
      <table className="grid">
        <thead>
          <tr>
            <th>{indexHeader}</th>
            {frame.columns.map((column) => (
              <th key={String(column)} className="num">{String(column)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {frame.data.map((values, i) => (
            <tr key={i} className={rowClass(i)}>
              <td>{indexLabel(String(frame.index[i]), i)}</td>
              {values.map((value, j) => (
                <td key={j}
                    className={`num${isNegative(value) ? " neg" : ""}`}>
                  {formatCell(value, frame.columns[j])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
