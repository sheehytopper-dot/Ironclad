// The API client. The contract is GET /api/docs; frames arrive
// split-orient ({columns, index, data}) at full precision with NaN
// already null. Errors arrive as the structured §5.4 shape
// {error: {summary, problems: [{field, message, got}], reference}} and
// are thrown as ApiError — the UI renders them readably, never a dump.

export class ApiError extends Error {
  constructor(summary, problems = [], reference = "") {
    super(summary);
    this.problems = problems;
    this.reference = reference;
  }
}

async function request(path, options = {}) {
  const response = await fetch(path, options);
  if (response.ok) return response.json();
  let body = null;
  try {
    body = await response.json();
  } catch {
    throw new ApiError(`API error ${response.status} on ${path}.`);
  }
  const error = body?.error ?? {};
  throw new ApiError(error.summary ?? `API error ${response.status}.`,
                     error.problems ?? [], error.reference ?? "");
}

export const api = {
  listProperties: () => request("/api/properties"),
  getProperty: (name) => request(`/api/properties/${name}`),
  putProperty: (name, document) =>
    request(`/api/properties/${name}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(document),
    }),
  calculate: (name) => request(`/api/calculate/${name}`, { method: "POST" }),
  listReports: (name) => request(`/api/reports?name=${name}`),
  getReport: (key, name, params = {}) => {
    const query = new URLSearchParams({ name, ...params });
    return request(`/api/reports/${key}?${query}`);
  },
  generations: (name, tenant) =>
    request(`/api/tenants/generations?${new URLSearchParams({ name, tenant })}`),
  gvBasis: (name, month) =>
    request(`/api/audit/gv-basis?name=${name}&month=${month}`),
  recoveryDrill: (name, params = {}) =>
    request(`/api/audit/recovery-drill?${new URLSearchParams({ name, ...params })}`),
  composition: (name, account, month) =>
    request(`/api/audit/composition?${new URLSearchParams({ name, account, month })}`),
  exportPackageUrl: (name) => `/api/export/package?name=${name}`,
  exportReportUrl: (key, name, params = {}) =>
    `/api/export/report/${key}?${new URLSearchParams({ name, ...params })}`,
};

/** split-orient frame JSON → array of row objects + the column list. */
export function frameRows(frame) {
  if (!frame) return { columns: [], rows: [] };
  const rows = frame.data.map((values, i) => {
    const row = { __index: frame.index[i] };
    frame.columns.forEach((column, j) => { row[column] = values[j]; });
    return row;
  });
  return { columns: frame.columns, rows };
}
