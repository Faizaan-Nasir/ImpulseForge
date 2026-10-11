const base = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
export async function api(path, options = {}) {
  const response = await fetch(`${base}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(body.detail)
      ? body.detail.map((x) => `${x.loc.join(".")}: ${x.msg}`).join("; ")
      : body.detail;
    throw new Error(
      body.message || detail || `Request failed (${response.status})`,
    );
  }
  return body;
}
export const post = (path, data = {}, options = {}) =>
  api(path, { ...options, method: "POST", body: JSON.stringify(data) });
export async function allAttempts(runId, options = {}) {
  const items = [];
  let history;
  do {
    history = await api(
      `/v1/runs/${runId}/attempts?offset=${items.length}&limit=1000`,
      options,
    );
    if (!history.items.length && items.length < history.total)
      throw new Error("Attempt history ended before all rows were retrieved");
    items.push(...history.items);
  } while (items.length < history.total);
  return { ...history, items };
}
export const sleep = (ms, signal) =>
  new Promise((resolve, reject) => {
    if (signal?.aborted)
      return reject(new DOMException("Aborted", "AbortError"));
    const abort = () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", abort);
      resolve();
    }, ms);
    signal?.addEventListener("abort", abort, { once: true });
  });
