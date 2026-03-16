/**
 * State management + event bus for the pricing calculator.
 *
 * State shape:
 *   { items: [ { id, serviceName, selections, subSelections, quantity, hoursPerMonth, cost, meters, error } ] }
 */

let nextId = 1;

const state = {
  items: [],
};

// Simple EventTarget-based event bus
const bus = new EventTarget();

function emit(name, detail) {
  bus.dispatchEvent(new CustomEvent(name, { detail }));
}

function on(name, fn) {
  bus.addEventListener(name, fn);
}

// ── Item CRUD ────────────────────────────────────────────────

function createItem(serviceName) {
  const item = {
    id: nextId++,
    serviceName,
    selections: {},
    subSelections: {},
    quantity: 1,
    hoursPerMonth: 730,
    hoursUnit: 'hours',   // 'hours' | 'days' | 'months' — display unit for duration
    cascadeData: null, // last cascade response
    cost: null,        // monthly cost number
    meters: null,      // meter breakdown array
    error: null,
    loading: false,
    metersCache: null,     // MetersResponse.groups — all meter data (all type/term)
    metersCacheKey: null,  // cache key: `${region}|${product}|${sku}`
    upfrontCost: null,     // Reservation total term cost (not monthly)
  };
  state.items.push(item);
  emit('item-added', { item });
  return item;
}

function getItem(id) {
  return state.items.find(i => i.id === id);
}

function updateItem(id, patch) {
  const item = getItem(id);
  if (!item) return;
  Object.assign(item, patch);
  emit('item-updated', { item });
}

function removeItem(id) {
  const idx = state.items.findIndex(i => i.id === id);
  if (idx === -1) return;
  state.items.splice(idx, 1);
  emit('item-removed', { id });
  emit('total-changed');
}

function getTotalCost() {
  return state.items.reduce((sum, item) => sum + (item.cost || 0), 0);
}

function getTotalUpfrontCost() {
  return state.items.reduce((sum, item) => sum + (item.upfrontCost || 0), 0);
}

export { state, bus, emit, on, createItem, getItem, updateItem, removeItem, getTotalCost, getTotalUpfrontCost };
