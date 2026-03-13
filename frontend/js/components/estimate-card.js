/**
 * Estimate card component — renders a single VM configuration card
 * with cascading dropdowns, quantity inputs, and meter breakdown.
 */

import { getItem, updateItem, removeItem, emit } from '../state.js';
import { fetchCascade, fetchCalculator, fetchPreload } from '../api.js';

// ── Static vs dynamic dimension sets ────────────────────────
// Static dimensions always show all options from preload data.
// Dynamic dimensions are filtered by cascade responses.
const STATIC_MAIN = new Set(['armRegionName']);
const STATIC_SUBS = new Set(['os', 'tier', 'category']);

// ── Service defaults (applied on card creation) ─────────────
const SERVICE_DEFAULTS = {
  'Virtual Machines': {
    selections: { armRegionName: 'eastus' },
    subSelections: { os: 'Linux', tier: 'Standard' },
  },
};

// ── Savings option mapping ──────────────────────────────────

const SAVINGS_OPTIONS = [
  { label: 'Pay as you go', type: 'Consumption', term: null },
  { label: '1 Year Reserved', type: 'Reservation', term: '1 Year' },
  { label: '3 Year Reserved', type: 'Reservation', term: '3 Years' },
  { label: '1 Year Savings Plan', type: 'SavingsPlanConsumption', term: '1 Year' },
  { label: '3 Year Savings Plan', type: 'SavingsPlanConsumption', term: '3 Years' },
];

function savingsKey(type, term) {
  return `${type}|${term || ''}`;
}

// Build a lookup from type+term → index
const savingsLookup = new Map(
  SAVINGS_OPTIONS.map((opt, i) => [savingsKey(opt.type, opt.term), i])
);

// ── Debounce helper ─────────────────────────────────────────

const debounceTimers = new Map();
function debounce(key, fn, ms = 300) {
  clearTimeout(debounceTimers.get(key));
  debounceTimers.set(key, setTimeout(fn, ms));
}

// ── Format currency ─────────────────────────────────────────

const fmt = new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD',
  minimumFractionDigits: 2, maximumFractionDigits: 2,
});

// ── Card class ──────────────────────────────────────────────

export class EstimateCard {
  constructor(itemId) {
    this.itemId = itemId;
    this.el = document.createElement('div');
    this.el.className = 'estimate-card';
    this.el.dataset.itemId = itemId;
    this.meterOpen = false;
    this.collapsed = false;
    this.preloadData = null;
    this.render();
    this.initCard();
  }

  async initCard() {
    // Apply service-specific defaults
    const defaults = SERVICE_DEFAULTS[this.item.serviceName];
    if (defaults) {
      const item = this.item;
      Object.assign(item.selections, defaults.selections);
      Object.assign(item.subSelections, defaults.subSelections);
      updateItem(this.itemId, item);
    }

    try {
      this.preloadData = await fetchPreload(this.item.serviceName);
      this.render();          // Render static dropdowns immediately
      this.triggerCascade();  // Fetch dynamic dimensions
    } catch (err) {
      this.triggerCascade();  // Preload failed → fall back to full cascade
    }
  }

  get item() { return getItem(this.itemId); }

  // ── Render ──────────────────────────────────────────────

  render() {
    const item = this.item;
    if (!item) return;

    const cost = item.cost != null ? fmt.format(item.cost) : '—';
    const costClass = item.cost != null ? 'card-cost' : 'card-cost pending';
    const chevron = this.collapsed ? '▸' : '▾';
    const discountBadge = this.renderDiscountBadge(item);

    this.el.classList.toggle('collapsed', this.collapsed);

    this.el.innerHTML = `
      <div class="card-loading ${item.loading ? '' : 'hidden'}">
        <div class="spinner"></div>
      </div>
      <div class="card-header">
        <button class="card-collapse-toggle" data-action="toggle-collapse" title="${this.collapsed ? 'Expand' : 'Collapse'}">
          <span class="chevron">${chevron}</span>
        </button>
        <div class="card-title">
          <span class="card-title-icon">🖥️</span>
          ${item.serviceName} #${item.id}
        </div>
        <div class="card-actions">
          <span class="${costClass}">${cost}/mo</span>
          ${discountBadge}
          <button class="btn btn-danger btn-sm btn-delete">✕ Remove</button>
        </div>
      </div>
      <div class="card-body">
        ${this.renderDropdowns(item)}
        ${this.renderError(item)}
        ${this.renderQuantity(item)}
        ${this.renderMeters(item)}
      </div>
    `;

    this.bindEvents();
  }

  renderDropdowns(item) {
    const preload = this.preloadData;
    const data = item.cascadeData;

    // Nothing at all yet
    if (!preload && !data) {
      return '<div class="form-group full-width"><span class="form-hint">Loading options...</span></div>';
    }

    let html = '';

    // ── Static dimensions (always from preload, full option set) ──

    // 1. Region — static
    const regionSource = preload || data;
    const regionDim = regionSource.dimensions.find(d => d.field === 'armRegionName');
    if (regionDim) {
      html += this.selectGroup('Region', 'armRegionName', regionDim.options, item.selections.armRegionName, false);
    }

    // 2-4. Static sub-dimensions (os, tier, category) — from preload
    const preloadProductDim = (preload || data)?.dimensions.find(d => d.field === 'productName');
    if (preloadProductDim?.sub_dimensions) {
      const staticSubs = preloadProductDim.sub_dimensions
        .filter(sd => STATIC_SUBS.has(sd.field))
        .sort((a, b) => a.order - b.order);
      for (const sd of staticSubs) {
        html += this.selectGroup(sd.label, `sub:${sd.field}`, sd.options, item.subSelections[sd.field], false);
      }
    }

    // ── Dynamic dimensions (from cascadeData, filtered by selections) ──

    // 5. Instance Series — dynamic sub-dimension
    const cascadeProductDim = data?.dimensions.find(d => d.field === 'productName');
    if (cascadeProductDim?.sub_dimensions) {
      const dynamicSubs = cascadeProductDim.sub_dimensions
        .filter(sd => !STATIC_SUBS.has(sd.field) && sd.field !== 'deployment')
        .sort((a, b) => a.order - b.order);
      for (const sd of dynamicSubs) {
        html += this.selectGroup(sd.label, `sub:${sd.field}`, sd.options, item.subSelections[sd.field], item.loading);
      }
    } else if (!data) {
      // Cascade not yet returned — show disabled placeholder for instance_series
      html += this.selectGroup('Instance Series', 'sub:instance_series', [], null, true);
    }

    // 6. SKU (skuName) — dynamic
    if (data) {
      const skuDim = data.dimensions.find(d => d.field === 'skuName');
      if (skuDim) {
        html += this.selectGroup('Instance', 'skuName', skuDim.options, item.selections.skuName, item.loading);
      }
    } else {
      html += this.selectGroup('Instance', 'skuName', [], null, true);
    }

    // 7. Savings option — dynamic
    if (data) {
      html += this.renderSavingsDropdown(item, data);
    } else {
      html += this.selectGroup('Savings Option', 'savings', [], null, true);
    }

    return html;
  }

  selectGroup(label, name, options, selected, disabled) {
    const opts = (options || []).map(o => {
      const sel = o === selected ? ' selected' : '';
      return `<option value="${this.escHtml(o)}"${sel}>${this.escHtml(o)}</option>`;
    }).join('');

    return `
      <div class="form-group">
        <label class="form-label">${label}</label>
        <select class="form-select" data-field="${name}" ${disabled ? 'disabled' : ''}>
          <option value="">— Select —</option>
          ${opts}
        </select>
      </div>
    `;
  }

  renderSavingsDropdown(item, data) {
    const typeDim = data.dimensions.find(d => d.field === 'type');
    const termDim = data.dimensions.find(d => d.field === 'term');
    const availableTypes = new Set(typeDim?.options || []);
    const availableTerms = new Set(termDim?.options || []);

    // Build available savings options
    const available = SAVINGS_OPTIONS.filter(opt => {
      if (!availableTypes.has(opt.type)) return false;
      if (opt.term && !availableTerms.has(opt.term)) return false;
      return true;
    });

    // Current selection
    const currentType = item.selections.type || 'Consumption';
    const currentTerm = item.selections.term || null;
    const currentKey = savingsKey(currentType, currentTerm);

    const opts = available.map((opt, _) => {
      const key = savingsKey(opt.type, opt.term);
      const sel = key === currentKey ? ' selected' : '';
      return `<option value="${key}"${sel}>${opt.label}</option>`;
    }).join('');

    return `
      <div class="form-group">
        <label class="form-label">Savings Option</label>
        <select class="form-select" data-field="savings" ${item.loading ? 'disabled' : ''}>
          ${opts}
        </select>
      </div>
    `;
  }

  renderQuantity(item) {
    return `
      <div class="quantity-row">
        <div class="quantity-group">
          <label class="form-label">VMs</label>
          <input type="number" class="form-input" data-field="quantity"
                 value="${item.quantity}" min="1" step="1" ${item.loading ? 'disabled' : ''}>
        </div>
        <div class="quantity-group">
          <label class="form-label">Hours / month</label>
          <input type="number" class="form-input" data-field="hoursPerMonth"
                 value="${item.hoursPerMonth}" min="1" max="744" step="1" ${item.loading ? 'disabled' : ''}>
        </div>
      </div>
    `;
  }

  renderError(item) {
    if (!item.error) return '<div class="card-error hidden"></div>';
    return `
      <div class="card-error">
        <span>${this.escHtml(item.error)}</span>
        <button class="btn btn-sm btn-outline btn-retry">Retry</button>
      </div>
    `;
  }

  renderMeters(item) {
    if (!item.meters || item.meters.length === 0) return '';
    const arrowChar = this.meterOpen ? '▾' : '▸';
    const toggleClass = this.meterOpen ? 'meter-toggle open' : 'meter-toggle';
    const wrapClass = this.meterOpen ? 'meter-table-wrap' : 'meter-table-wrap hidden';

    const rows = item.meters.map(m => `
      <tr>
        <td>${this.escHtml(m.meter)}</td>
        <td>${this.escHtml(m.unit)}</td>
        <td class="num">${m.usage.toLocaleString()}</td>
        <td class="num">${fmt.format(m.monthly_cost)}</td>
      </tr>
    `).join('');

    return `
      <div class="meter-section">
        <button class="${toggleClass}" data-action="toggle-meters">
          <span class="arrow">${arrowChar}</span> Meter breakdown (${item.meters.length})
        </button>
        <div class="${wrapClass}">
          <table class="meter-table">
            <thead><tr><th>Meter</th><th>Unit</th><th>Usage</th><th>Cost</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>
    `;
  }

  renderDiscountBadge(item) {
    if (item.cost == null || !item.paygCost || item.paygCost <= 0) return '';
    const type = item.selections.type || 'Consumption';
    if (type === 'Consumption') return '';

    // For Reservation, monthly_cost is total term cost — convert to monthly
    let monthlyCost = item.cost;
    if (type === 'Reservation' && item.selections.term) {
      const months = item.selections.term === '3 Years' ? 36 : 12;
      monthlyCost = item.cost / months;
    }

    const discount = ((item.paygCost - monthlyCost) / item.paygCost) * 100;
    if (discount <= 0) return '';
    return `<span class="card-discount">~${Math.round(discount)}% discount</span>`;
  }

  escHtml(s) {
    if (!s) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // ── Events ──────────────────────────────────────────────

  bindEvents() {
    // Dropdowns
    this.el.querySelectorAll('.form-select').forEach(sel => {
      sel.addEventListener('change', (e) => this.onSelectChange(e));
    });

    // Quantity inputs
    this.el.querySelectorAll('.form-input[data-field="quantity"], .form-input[data-field="hoursPerMonth"]').forEach(inp => {
      inp.addEventListener('input', (e) => this.onQuantityChange(e));
    });

    // Collapse toggle
    const collapseBtn = this.el.querySelector('[data-action="toggle-collapse"]');
    if (collapseBtn) collapseBtn.addEventListener('click', () => {
      this.collapsed = !this.collapsed;
      this.el.classList.toggle('collapsed', this.collapsed);
      collapseBtn.title = this.collapsed ? 'Expand' : 'Collapse';
      collapseBtn.querySelector('.chevron').textContent = this.collapsed ? '▸' : '▾';
      emit('card-collapse-changed');
    });

    // Delete
    const delBtn = this.el.querySelector('.btn-delete');
    if (delBtn) delBtn.addEventListener('click', () => removeItem(this.itemId));

    // Retry
    const retryBtn = this.el.querySelector('.btn-retry');
    if (retryBtn) retryBtn.addEventListener('click', () => this.triggerCascade());

    // Meter toggle
    const meterBtn = this.el.querySelector('[data-action="toggle-meters"]');
    if (meterBtn) meterBtn.addEventListener('click', () => {
      this.meterOpen = !this.meterOpen;
      this.render();
    });
  }

  onSelectChange(e) {
    const field = e.target.dataset.field;
    const value = e.target.value;
    const item = this.item;
    if (!item) return;

    if (field === 'savings') {
      // Parse type|term
      const [type, term] = value.split('|');
      item.selections.type = type;
      item.selections.term = term || null;
      // Clear term from selections if empty
      if (!term) delete item.selections.term;
    } else if (field.startsWith('sub:')) {
      const subField = field.slice(4);
      if (value) {
        item.subSelections[subField] = value;
      } else {
        delete item.subSelections[subField];
      }
      // Clear productName when sub-dim changes (it will be auto-selected)
      delete item.selections.productName;
      // If a static sub-dim changed, also clear dynamic sub-dims downstream
      if (STATIC_SUBS.has(subField)) {
        delete item.subSelections.instance_series;
        delete item.selections.skuName;
      }
    } else {
      // Main dimension
      if (value) {
        item.selections[field] = value;
      } else {
        delete item.selections[field];
      }
      // If a static main dim changed (e.g. Region), clear dynamic downstream
      if (STATIC_MAIN.has(field)) {
        delete item.subSelections.instance_series;
        delete item.selections.skuName;
        delete item.selections.productName;
      }
    }

    // Clear downstream state
    item.cost = null;
    item.meters = null;
    item.error = null;
    updateItem(this.itemId, item);

    this.triggerCascade();
  }

  onQuantityChange(e) {
    const field = e.target.dataset.field;
    const value = parseFloat(e.target.value) || 0;
    const item = this.item;
    if (!item) return;

    item[field] = value;
    updateItem(this.itemId, item);

    debounce(`qty-${this.itemId}`, () => this.triggerCalculator(), 300);
  }

  // ── API calls ─────────────────────────────────────────

  async triggerCascade() {
    const item = this.item;
    if (!item) return;

    updateItem(this.itemId, { loading: true, error: null });
    this.render();

    try {
      const data = await fetchCascade(
        this.itemId,
        item.serviceName,
        item.selections,
        item.subSelections,
      );

      // Auto-select single options (skip static dimensions)
      let changed = false;
      for (const dim of data.dimensions) {
        if (dim.field === 'productName') {
          // Auto-select productName if sub-dims narrow to 1
          if (dim.options.length === 1 && item.selections.productName !== dim.options[0]) {
            item.selections.productName = dim.options[0];
            changed = true;
          }
          // Auto-select dynamic sub-dimensions with single option (skip static)
          if (dim.sub_dimensions) {
            for (const sd of dim.sub_dimensions) {
              if (STATIC_SUBS.has(sd.field)) continue;
              if (sd.options.length === 1 && item.subSelections[sd.field] !== sd.options[0]) {
                item.subSelections[sd.field] = sd.options[0];
                changed = true;
              }
            }
          }
        } else if (dim.field === 'term' || dim.field === 'type') {
          // Don't auto-select term or type
        } else if (STATIC_MAIN.has(dim.field)) {
          // Don't auto-select static main dimensions
        } else {
          // Auto-select dynamic main dims with single option
          if (dim.options.length === 1 && item.selections[dim.field] !== dim.options[0]) {
            item.selections[dim.field] = dim.options[0];
            changed = true;
          }
        }

        // Validate selection still valid — skip static dimensions
        if (dim.field !== 'productName' && !STATIC_MAIN.has(dim.field)) {
          const sel = item.selections[dim.field];
          if (sel && !dim.options.includes(sel)) {
            delete item.selections[dim.field];
            changed = true;
          }
        }
      }

      // Validate sub-selections — skip static sub-dimensions
      const productDim = data.dimensions.find(d => d.field === 'productName');
      if (productDim?.sub_dimensions) {
        for (const sd of productDim.sub_dimensions) {
          if (STATIC_SUBS.has(sd.field)) continue;
          const sel = item.subSelections[sd.field];
          if (sel && !sd.options.includes(sel)) {
            delete item.subSelections[sd.field];
            changed = true;
          }
        }
      }

      updateItem(this.itemId, { cascadeData: data, loading: false });
      this.render();

      // If auto-selection changed something, re-cascade
      if (changed) {
        this.triggerCascade();
        return;
      }

      // Try to calculate if fully configured
      this.triggerCalculator();

    } catch (err) {
      if (err.name === 'AbortError') return;
      updateItem(this.itemId, { loading: false, error: err.message });
      this.render();
    }
  }

  async triggerCalculator() {
    const item = this.item;
    if (!item) return;

    // Need at minimum: region, product, sku
    const { armRegionName, productName, skuName } = item.selections;
    if (!armRegionName || !productName || !skuName) {
      updateItem(this.itemId, { cost: null, meters: null });
      this.render();
      emit('total-changed');
      return;
    }

    const calcItem = {
      service_name: item.serviceName,
      region: armRegionName,
      product: productName,
      sku: skuName,
      type: item.selections.type || 'Consumption',
      term: item.selections.term || null,
      quantity: item.quantity || 1,
      hours_per_month: item.hoursPerMonth || 730,
    };

    try {
      const resp = await fetchCalculator(this.itemId, [calcItem]);
      if (resp.items.length > 0) {
        const result = resp.items[0];
        updateItem(this.itemId, {
          cost: result.monthly_cost,
          paygCost: result.payg_monthly_cost ?? null,
          meters: result.meters,
          error: null,
        });
      }
      this.render();
      emit('total-changed');
    } catch (err) {
      if (err.name === 'AbortError') return;
      // Don't overwrite cascade error; calculator errors are non-blocking
      console.warn('Calculator error:', err);
    }
  }
}
