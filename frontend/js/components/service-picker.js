/**
 * Service picker — renders the product catalog navigation area.
 *
 * Layout: left family sidebar + right product card grid.
 * Supports family filtering, "Popular" virtual category, and search.
 */

import { createItem } from '../state.js';
import { fetchCatalog, fetchProductSearch } from '../api.js';

let catalog = null;         // full catalog data
let activeFamily = null;    // current selected family key, null = "popular"
let searchMode = false;     // whether we're in search results mode

// DOM references (set during init)
let sidebarEl, gridEl, searchInput, searchClear;

// ── Rendering ────────────────────────────────────────────────

function renderSidebar() {
  if (!catalog) return;

  const items = [
    { key: null, label: 'Popular' },
    ...catalog.families
      .sort((a, b) => a.order - b.order)
      .map(f => ({ key: f.key, label: f.label })),
  ];

  sidebarEl.innerHTML = items.map(item => `
    <button class="family-item ${item.key === activeFamily ? 'active' : ''}"
            data-family="${item.key ?? ''}">
      ${item.label}
    </button>
  `).join('');
}

function renderCards(services) {
  if (!services || services.length === 0) {
    gridEl.innerHTML = `
      <div class="catalog-empty">
        <p>No products found.</p>
      </div>
    `;
    return;
  }

  gridEl.innerHTML = services.map(svc => `
    <div class="product-card">
      <div class="product-card-header">
        <span class="product-card-icon">${getServiceIcon(svc.icon)}</span>
        <span class="product-card-name">${svc.service_name}</span>
      </div>
      <p class="product-card-desc">${svc.description}</p>
      <button class="btn btn-outline btn-add-estimate" data-service="${svc.service_name}">
        Add to estimate
      </button>
    </div>
  `).join('');
}

function getServiceIcon(iconKey) {
  // Simple icon mapping — returns an SVG or emoji fallback
  const icons = {
    'virtual-machines': '<svg width="20" height="20" viewBox="0 0 18 18"><rect x="1" y="4" width="16" height="10" rx="1" fill="none" stroke="#0078d4" stroke-width="1.5"/><line x1="5" y1="14" x2="5" y2="16" stroke="#0078d4" stroke-width="1.5"/><line x1="13" y1="14" x2="13" y2="16" stroke="#0078d4" stroke-width="1.5"/><line x1="3" y1="16" x2="15" y2="16" stroke="#0078d4" stroke-width="1.5"/></svg>',
    'storage-accounts': '<svg width="20" height="20" viewBox="0 0 18 18"><ellipse cx="9" cy="5" rx="7" ry="2.5" fill="none" stroke="#0078d4" stroke-width="1.5"/><path d="M2 5v8c0 1.38 3.13 2.5 7 2.5s7-1.12 7-2.5V5" fill="none" stroke="#0078d4" stroke-width="1.5"/><ellipse cx="9" cy="9" rx="7" ry="2.5" fill="none" stroke="#0078d4" stroke-width="1.5"/></svg>',
    'sql-database': '<svg width="20" height="20" viewBox="0 0 18 18"><ellipse cx="9" cy="4" rx="6" ry="2.5" fill="none" stroke="#0078d4" stroke-width="1.5"/><path d="M3 4v10c0 1.38 2.69 2.5 6 2.5s6-1.12 6-2.5V4" fill="none" stroke="#0078d4" stroke-width="1.5"/></svg>',
  };
  return icons[iconKey] || '<svg width="20" height="20" viewBox="0 0 18 18"><rect x="2" y="2" width="14" height="14" rx="3" fill="none" stroke="#0078d4" stroke-width="1.5"/></svg>';
}

function getServicesForFamily(familyKey) {
  if (!catalog) return [];
  if (familyKey === null || familyKey === '') {
    // Popular: collect all services with popular=true, preserve family order
    return catalog.families
      .sort((a, b) => a.order - b.order)
      .flatMap(f => f.services.filter(s => s.popular));
  }
  const family = catalog.families.find(f => f.key === familyKey);
  return family ? family.services : [];
}

// ── Event Handlers ───────────────────────────────────────────

function onFamilyClick(e) {
  const btn = e.target.closest('.family-item');
  if (!btn) return;

  const key = btn.dataset.family || null;
  activeFamily = key;
  searchMode = false;
  searchInput.value = '';
  searchClear.classList.add('hidden');

  renderSidebar();
  renderCards(getServicesForFamily(activeFamily));
}

function onAddClick(e) {
  const btn = e.target.closest('.btn-add-estimate');
  if (!btn) return;
  const serviceName = btn.dataset.service;
  createItem(serviceName);

  // Scroll to estimate panel
  const panel = document.getElementById('estimate-panel');
  if (panel) {
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

let searchTimer = null;

function onSearchInput() {
  const query = searchInput.value.trim();

  if (searchTimer) clearTimeout(searchTimer);

  if (!query) {
    // Exit search mode, restore family view
    searchMode = false;
    searchClear.classList.add('hidden');
    sidebarEl.querySelectorAll('.family-item').forEach(el => el.disabled = false);
    renderSidebar();
    renderCards(getServicesForFamily(activeFamily));
    return;
  }

  searchClear.classList.remove('hidden');

  // Debounce 300ms
  searchTimer = setTimeout(async () => {
    searchMode = true;
    // Deselect sidebar
    sidebarEl.querySelectorAll('.family-item').forEach(el => el.classList.remove('active'));

    try {
      const data = await fetchProductSearch(query);
      renderCards(data.results);
    } catch (err) {
      if (err.name === 'AbortError') return;
      gridEl.innerHTML = `<div class="catalog-empty"><p>Search failed: ${err.message}</p></div>`;
    }
  }, 300);
}

function onSearchClear() {
  searchInput.value = '';
  onSearchInput();
  searchInput.focus();
}

// ── Init ─────────────────────────────────────────────────────

export async function renderServicePicker() {
  sidebarEl = document.getElementById('family-sidebar');
  gridEl = document.getElementById('product-grid');
  searchInput = document.getElementById('search-input');
  searchClear = document.getElementById('search-clear');

  // Show loading state
  gridEl.innerHTML = '<div class="catalog-empty"><p>Loading products...</p></div>';

  // Bind events
  sidebarEl.addEventListener('click', onFamilyClick);
  gridEl.addEventListener('click', onAddClick);
  searchInput.addEventListener('input', onSearchInput);
  searchClear.addEventListener('click', onSearchClear);

  // Load catalog
  try {
    catalog = await fetchCatalog();
    activeFamily = null; // start with Popular
    renderSidebar();
    renderCards(getServicesForFamily(null));
  } catch (err) {
    gridEl.innerHTML = `<div class="catalog-empty"><p>Failed to load product catalog.</p></div>`;
  }
}
