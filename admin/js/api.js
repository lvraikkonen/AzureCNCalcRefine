/**
 * Admin API client — wraps all /api/v1/admin/* endpoints.
 */

const BASE = "/api/v1/admin";

function authHeaders() {
  const token = sessionStorage.getItem("admin_token");
  if (token) return { Authorization: `Bearer ${token}` };
  return {};
}

async function apiFetch(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json", ...authHeaders() },
    ...options,
  });
  if (res.status === 401 || res.status === 403) {
    sessionStorage.removeItem("admin_token");
    window.location.hash = "#/login";
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const body = await res.text();
    let detail = body;
    try { detail = JSON.parse(body)?.detail ?? body; } catch (_) {}
    throw new Error(typeof detail === "object" ? JSON.stringify(detail) : detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

// ── Service Configs ──────────────────────────────────────────────────────────

export const listConfigs = (params = {}) => {
  const q = new URLSearchParams(params).toString();
  return apiFetch(`/configs${q ? "?" + q : ""}`);
};

export const getConfig = (serviceName) =>
  apiFetch(`/configs/${encodeURIComponent(serviceName)}`);

export const createConfig = (body) =>
  apiFetch("/configs", { method: "POST", body: JSON.stringify(body) });

export const updateConfig = (serviceName, body) =>
  apiFetch(`/configs/${encodeURIComponent(serviceName)}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });

export const publishConfig = (serviceName, body = {}) =>
  apiFetch(`/configs/${encodeURIComponent(serviceName)}/publish`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const archiveConfig = (serviceName) =>
  apiFetch(`/configs/${encodeURIComponent(serviceName)}`, { method: "DELETE" });

export const revertConfig = (serviceName, version, body = {}) =>
  apiFetch(`/configs/${encodeURIComponent(serviceName)}/revert/${version}`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const getConfigHistory = (serviceName) =>
  apiFetch(`/configs/${encodeURIComponent(serviceName)}/history`);

export const validateConfig = (serviceName, config) =>
  apiFetch(`/configs/${encodeURIComponent(serviceName)}/validate`, {
    method: "POST",
    body: JSON.stringify({ config }),
  });

// ── Catalog ──────────────────────────────────────────────────────────────────

export const listFamilies = () => apiFetch("/catalog/families");

export const createFamily = (body) =>
  apiFetch("/catalog/families", { method: "POST", body: JSON.stringify(body) });

export const updateFamily = (key, body) =>
  apiFetch(`/catalog/families/${encodeURIComponent(key)}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });

export const deleteFamily = (key) =>
  apiFetch(`/catalog/families/${encodeURIComponent(key)}`, { method: "DELETE" });

export const createServiceEntry = (body) =>
  apiFetch("/catalog/services", { method: "POST", body: JSON.stringify(body) });

export const updateServiceEntry = (serviceName, body) =>
  apiFetch(`/catalog/services/${encodeURIComponent(serviceName)}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });

export const deleteServiceEntry = (serviceName) =>
  apiFetch(`/catalog/services/${encodeURIComponent(serviceName)}`, { method: "DELETE" });

export const reorderCatalog = (body) =>
  apiFetch("/catalog/reorder", { method: "POST", body: JSON.stringify(body) });

// ── Import ───────────────────────────────────────────────────────────────────

export const importJsonFiles = (overwrite = false) =>
  apiFetch("/import/json-files", {
    method: "POST",
    body: JSON.stringify({ overwrite }),
  });
