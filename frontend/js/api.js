/**
 * API client for the explore endpoints.
 * Each call returns a promise. Supports AbortController for request cancellation.
 */

const BASE = '/api/v1/explore';
const PRODUCTS_BASE = '/api/v1/products';

// Track active controllers per item+type for cancellation
const controllers = new Map();

function getController(key) {
  const prev = controllers.get(key);
  if (prev) prev.abort();
  const ctrl = new AbortController();
  controllers.set(key, ctrl);
  return ctrl;
}

async function request(path, body, signal) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`API ${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json();
}

/**
 * Fetch cascade options for a given service + current selections.
 * @param {number} itemId - Used for abort key
 * @param {string} serviceName
 * @param {object} selections - main dimension selections
 * @param {object} subSelections - sub-dimension selections
 */
export async function fetchCascade(itemId, serviceName, selections, subSelections) {
  const ctrl = getController(`cascade-${itemId}`);
  return request('/cascade', {
    service_name: serviceName,
    selections,
    sub_selections: subSelections,
  }, ctrl.signal);
}

// ── Preload cache ──────────────────────────────────────────
// Stores Promise<response> per service name so concurrent callers share one request.
const preloadCache = new Map();

/**
 * Fetch (or return cached) cascade response with empty selections for a service.
 * Used to populate static dropdowns (Region, OS, Tier, Category).
 * @param {string} serviceName
 * @returns {Promise<object>} cascade response with all options
 */
export function fetchPreload(serviceName) {
  if (preloadCache.has(serviceName)) {
    return preloadCache.get(serviceName);
  }
  const promise = request('/cascade', {
    service_name: serviceName,
    selections: {},
    sub_selections: {},
  }).catch(err => {
    preloadCache.delete(serviceName);
    throw err;
  });
  preloadCache.set(serviceName, promise);
  return promise;
}

/**
 * Calculate price for one or more items.
 * @param {number} itemId - Used for abort key
 * @param {Array} items - CalculatorItem[]
 */
export async function fetchCalculator(itemId, items) {
  const ctrl = getController(`calc-${itemId}`);
  return request('/calculator', { items }, ctrl.signal);
}

/**
 * Fetch all meter groups (all type/term combos) for a specific configuration.
 * Returns MetersResponse with groups containing tiered pricing data.
 * @param {number} itemId - Used for abort key
 * @param {string} serviceName
 * @param {string} region
 * @param {string} product
 * @param {string} sku
 */
export async function fetchMeters(itemId, serviceName, region, product, sku) {
  const ctrl = getController(`meters-${itemId}`);
  return request('/meters', {
    service_name: serviceName,
    region,
    product,
    sku,
  }, ctrl.signal);
}

// ── Service Config ───────────────────────────────────────────

/**
 * Fetch default configuration for a service (selections, sub_selections, etc.).
 * @param {string} serviceName
 */
export async function fetchServiceConfig(serviceName) {
  const res = await fetch(`${BASE}/service-config/${encodeURIComponent(serviceName)}`);
  if (!res.ok) throw new Error(`Config ${res.status}`);
  return res.json();
}

// ── Product Catalog ──────────────────────────────────────────

let catalogCache = null;

/**
 * Fetch (or return cached) product catalog.
 */
export async function fetchCatalog() {
  if (catalogCache) return catalogCache;
  const res = await fetch(`${PRODUCTS_BASE}/catalog`);
  if (!res.ok) throw new Error(`Catalog ${res.status}`);
  catalogCache = await res.json();
  return catalogCache;
}

/**
 * Search products by keyword.
 * @param {string} query
 */
export async function fetchProductSearch(query) {
  const res = await fetch(`${PRODUCTS_BASE}/search?q=${encodeURIComponent(query)}`);
  if (!res.ok) throw new Error(`Search ${res.status}`);
  return res.json();
}
