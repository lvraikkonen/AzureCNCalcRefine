/**
 * Estimate card component — renders a single VM configuration card
 * with cascading dropdowns, quantity inputs, and meter breakdown.
 */

import { getItem, updateItem, removeItem, emit } from '../state.js';
import { fetchCascade, fetchPreload, fetchMeters, fetchServiceConfig } from '../api.js';
import { calculateLocalPrice, calculatePerMeterPrice, getAvailableSavingsOptions } from '../pricing.js';
import { buildGroupedRegions, getRegionDisplay } from '../regions.js';

// ── Static vs dynamic dimension sets ────────────────────────
// Static dimensions always show all options from preload data.
// Dynamic dimensions are filtered by cascade responses.
const STATIC_MAIN = new Set(['armRegionName']);
const DEFAULT_STATIC_SUBS = new Set(['os', 'tier', 'category']);
const DEFAULT_HIDDEN_SUBS = new Set(['deployment']);

// ── Service defaults (applied on card creation) ─────────────
const SERVICE_DEFAULTS = {
  'Virtual Machines': {
    selections: { armRegionName: 'eastus' },
    subSelections: { os: 'Linux', tier: 'Standard' },
  },
};

// ── Service icon mapping ─────────────────────────────────────
const SERVICE_ICONS = {
  'Virtual Machines': '🖥️',
  'App Service': '🌐',
  'Power BI Embedded': '📊',
  'Azure Firewall': '🛡️',
  'Event Grid': '⚡',
  'Service Bus': '🚌',
};

// ── Savings option mapping ──────────────────────────────────

const SAVINGS_OPTIONS = [
  { label: 'Pay as you go', type: 'Consumption', term: null },
  { label: '1 Year Reserved', type: 'Reservation', term: '1 Year' },
  { label: '3 Year Reserved', type: 'Reservation', term: '3 Years' },
  { label: '5 Year Reserved', type: 'Reservation', term: '5 Years' },
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
    // Fetch service config and preload in parallel
    const [configResult, preloadResult] = await Promise.allSettled([
      fetchServiceConfig(this.item.serviceName),
      fetchPreload(this.item.serviceName),
    ]);

    // Apply defaults from config API, with hardcoded fallback
    const item = this.item;
    let defaults = SERVICE_DEFAULTS[item.serviceName];
    if (configResult.status === 'fulfilled') {
      const configData = configResult.value;
      // Store service config for per-service behavior
      item.serviceConfig = {
        quantity_label: configData.quantity_label || 'VMs',
        quantity_model: configData.quantity_model || 'instances_x_hours',
        static_subs: configData.static_subs || null,
        hidden_subs: configData.hidden_subs || [],
        dimension_labels: configData.dimension_labels || {},
        hidden_dimensions: configData.hidden_dimensions || [],
        meter_free_quota: configData.meter_free_quota || {},
        meter_labels: configData.meter_labels || {},
        meter_order: configData.meter_order || [],
      };
      if (configData.defaults) {
        const cfg = configData.defaults;
        defaults = {
          selections: cfg.selections || {},
          subSelections: cfg.sub_selections || {},
        };
        if (cfg.hours_per_month) {
          item.hoursPerMonth = cfg.hours_per_month;
        }
      }
    }

    if (defaults) {
      Object.assign(item.selections, defaults.selections || {});
      Object.assign(item.subSelections, defaults.subSelections || {});
      updateItem(this.itemId, item);
    }

    // Use preload data if available
    if (preloadResult.status === 'fulfilled') {
      this.preloadData = preloadResult.value;
      this.render();
    }

    this.triggerCascade();
  }

  get item() { return getItem(this.itemId); }

  get staticSubs() {
    const cfg = this.item?.serviceConfig;
    return cfg?.static_subs ? new Set(cfg.static_subs) : DEFAULT_STATIC_SUBS;
  }

  get hiddenSubs() {
    const cfg = this.item?.serviceConfig;
    return cfg?.hidden_subs ? new Set(cfg.hidden_subs) : DEFAULT_HIDDEN_SUBS;
  }

  get quantityLabel() {
    return this.item?.serviceConfig?.quantity_label || 'VMs';
  }

  get quantityModel() {
    return this.item?.serviceConfig?.quantity_model || 'instances_x_hours';
  }

  getDimensionLabel(field, defaultLabel) {
    const labels = this.item?.serviceConfig?.dimension_labels;
    return labels?.[field] || defaultLabel;
  }

  isDimensionHidden(field) {
    const hidden = this.item?.serviceConfig?.hidden_dimensions;
    return hidden?.includes(field) || false;
  }

  get serviceIcon() {
    return SERVICE_ICONS[this.item?.serviceName] || '📦';
  }

  // ── Render ──────────────────────────────────────────────

  render() {
    const item = this.item;
    if (!item) return;

    const cost = item.cost != null ? fmt.format(item.cost) : '—';
    const costClass = item.cost != null ? 'card-cost' : 'card-cost pending';
    const chevron = this.collapsed ? '▸' : '▾';
    const discountBadge = this.renderDiscountBadge(item);

    this.el.classList.toggle('collapsed', this.collapsed);

    const headerSummary = this.renderHeaderSummary(item);
    const upfrontHtml = this.renderHeaderUpfront(item);

    this.el.innerHTML = `
      <div class="card-loading ${item.loading ? '' : 'hidden'}">
        <div class="spinner"></div>
      </div>
      <div class="card-header">
        <button class="card-collapse-toggle" data-action="toggle-collapse" title="${this.collapsed ? 'Expand' : 'Collapse'}">
          <span class="chevron">${chevron}</span>
        </button>
        <div class="card-title-area">
          <div class="card-title">
            <span class="card-title-icon">${this.serviceIcon}</span>
            <span class="card-title-text" data-action="edit-name" title="Click to rename">${this.escHtml(item.customName || `${item.serviceName} #${item.id}`)}</span>
            <button class="card-edit-name-btn" data-action="edit-name" title="Rename">✎</button>
          </div>
          ${headerSummary}
        </div>
        <div class="card-actions">
          <div class="card-cost-group">
            ${upfrontHtml}
            <span class="${costClass}">${cost}/mo</span>
          </div>
          ${discountBadge}
          <button class="btn btn-danger btn-sm btn-delete">✕ Remove</button>
        </div>
      </div>
      <div class="card-body">
        ${this.renderDropdowns(item)}
        ${this.renderError(item)}
        ${this.renderQuantity(item)}
        ${this.renderMeters(item)}
        ${this.renderPriceSummary(item)}
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

    // 1. Region — static, grouped by country/geography
    const regionSource = preload || data;
    const regionDim = regionSource.dimensions.find(d => d.field === 'armRegionName');
    if (regionDim) {
      html += this.selectRegionGroup(regionDim.options, item.selections.armRegionName);
    }

    // 2+. Static sub-dimensions (os, tier, category, etc.) — from preload
    // Skip if productName dimension is hidden (Pattern B: no sub-dimensions)
    const productHidden = this.isDimensionHidden('productName');
    const staticSubSet = this.staticSubs;
    const hiddenSubSet = this.hiddenSubs;
    const preloadProductDim = (preload || data)?.dimensions.find(d => d.field === 'productName');
    let tierSelected = null;
    if (!productHidden && preloadProductDim?.sub_dimensions) {
      const staticSubs = preloadProductDim.sub_dimensions
        .filter(sd => staticSubSet.has(sd.field) && !hiddenSubSet.has(sd.field))
        .sort((a, b) => a.order - b.order);
      for (const sd of staticSubs) {
        html += this.selectGroup(sd.label, `sub:${sd.field}`, sd.options, item.subSelections[sd.field], false);
        if (sd.field === 'tier') tierSelected = item.subSelections[sd.field] || null;
      }
    }

    // Tier section header — show selected tier as a header above the Instance dropdown
    if (tierSelected) {
      html += `<div class="tier-section-header">${this.escHtml(tierSelected)}</div>`;
    }

    // ── Dynamic dimensions (from cascadeData, filtered by selections) ──

    // Dynamic sub-dimensions (e.g. instance_series for VM) — skip if productName hidden
    const cascadeProductDim = data?.dimensions.find(d => d.field === 'productName');
    if (!productHidden && cascadeProductDim?.sub_dimensions) {
      const dynamicSubs = cascadeProductDim.sub_dimensions
        .filter(sd => !staticSubSet.has(sd.field) && !hiddenSubSet.has(sd.field))
        .sort((a, b) => a.order - b.order);
      for (const sd of dynamicSubs) {
        html += this.selectGroup(sd.label, `sub:${sd.field}`, sd.options, item.subSelections[sd.field], item.loading);
      }
    } else if (!productHidden && !data) {
      // Cascade not yet returned — show disabled placeholder for dynamic sub-dims
      // Only show placeholder if this service has dynamic sub-dims (e.g. VM has instance_series)
      const allSubs = preloadProductDim?.sub_dimensions || [];
      const dynamicPlaceholders = allSubs.filter(sd => !staticSubSet.has(sd.field) && !hiddenSubSet.has(sd.field));
      for (const sd of dynamicPlaceholders) {
        html += this.selectGroup(sd.label, `sub:${sd.field}`, [], null, true);
      }
    }

    // 6. SKU (skuName) — dynamic
    const skuLabel = this.getDimensionLabel('skuName', 'Instance');
    if (data) {
      const skuDim = data.dimensions.find(d => d.field === 'skuName');
      if (skuDim) {
        html += this.selectGroup(skuLabel, 'skuName', skuDim.options, item.selections.skuName, item.loading);
      }
    } else {
      html += this.selectGroup(skuLabel, 'skuName', [], null, true);
    }

    // 7. Savings option — radio buttons
    html += this.renderSavingsRadio(item);

    return html;
  }

  selectGroup(label, name, options, selected, disabled) {
    const opts = (options || []).map(o => {
      const sel = o === selected ? ' selected' : '';
      return `<option value="${this.escHtml(o)}"${sel}>${this.escHtml(o)}</option>`;
    }).join('');

    // Only show placeholder when no value is selected
    const placeholder = selected ? '' : '<option value="">— Select —</option>';

    return `
      <div class="form-group">
        <label class="form-label">${label}</label>
        <select class="form-select" data-field="${name}" ${disabled ? 'disabled' : ''}>
          ${placeholder}
          ${opts}
        </select>
      </div>
    `;
  }

  selectRegionGroup(options, selected) {
    const grouped = buildGroupedRegions(options || []);
    let opts = '';
    for (const { group, regions } of grouped) {
      opts += `<optgroup label="${this.escHtml(group)}">`;
      for (const r of regions) {
        const sel = r.slug === selected ? ' selected' : '';
        opts += `<option value="${this.escHtml(r.slug)}"${sel}>${this.escHtml(r.display)}</option>`;
      }
      opts += '</optgroup>';
    }

    const placeholder = selected ? '' : '<option value="">— Select —</option>';

    return `
      <div class="form-group">
        <label class="form-label">Region</label>
        <select class="form-select" data-field="armRegionName">
          ${placeholder}
          ${opts}
        </select>
      </div>
    `;
  }

  renderSavingsRadio(item) {
    // Determine available options from metersCache (with discount) or cascade (without)
    let options;
    if (item.metersCache) {
      options = getAvailableSavingsOptions(
        item.metersCache, item.quantity || 1, item.hoursPerMonth || 730,
        { meterQuantities: item.meterQuantities, quantityModel: this.quantityModel, meterFreeOffsets: this.computeMeterFreeOffsets(item) },
      );
    } else if (item.cascadeData) {
      const data = item.cascadeData;
      const typeDim = data.dimensions.find(d => d.field === 'type');
      const termDim = data.dimensions.find(d => d.field === 'term');
      const availableTypes = new Set(typeDim?.options || []);
      const availableTerms = new Set(termDim?.options || []);
      options = SAVINGS_OPTIONS
        .filter(opt => {
          if (!availableTypes.has(opt.type)) return false;
          if (opt.term && !availableTerms.has(opt.term)) return false;
          return true;
        })
        .map(opt => ({ ...opt, discountPercent: null }));
    } else {
      return '';
    }

    if (options.length === 0) return '';

    const currentType = item.selections.type || 'Consumption';
    const currentTerm = item.selections.term || null;
    const currentKey = savingsKey(currentType, currentTerm);
    const radioName = `savings-${this.itemId}`;
    const disabled = item.loading ? ' disabled' : '';

    // Group by type
    const payg = options.filter(o => o.type === 'Consumption');
    const sp = options.filter(o => o.type === 'SavingsPlanConsumption');
    const ri = options.filter(o => o.type === 'Reservation');

    // No savings options available — hide the entire section (PAYG is implicit)
    if (sp.length === 0 && ri.length === 0) return '';

    let html = '<div class="savings-section">';

    // PAYG — standalone
    for (const opt of payg) {
      const key = savingsKey(opt.type, opt.term);
      const checked = key === currentKey ? ' checked' : '';
      html += `
        <label class="savings-radio">
          <input type="radio" name="${radioName}" value="${key}"${checked}${disabled}>
          <span class="savings-label">${this.escHtml(opt.label)}</span>
        </label>`;
    }

    // Savings Plan group
    if (sp.length > 0) {
      html += '<div class="savings-group">';
      html += '<div class="savings-group-title">Savings plan</div>';
      for (const opt of sp) {
        const key = savingsKey(opt.type, opt.term);
        const checked = key === currentKey ? ' checked' : '';
        const discount = opt.discountPercent != null
          ? `<span class="savings-discount">~${opt.discountPercent}% discount</span>`
          : '';
        html += `
          <label class="savings-radio">
            <input type="radio" name="${radioName}" value="${key}"${checked}${disabled}>
            <span class="savings-label">${this.escHtml(opt.label)}</span>
            ${discount}
          </label>`;
      }
      html += '</div>';
    }

    // Reservation group
    if (ri.length > 0) {
      html += '<div class="savings-group">';
      html += '<div class="savings-group-title">Reservations</div>';
      for (const opt of ri) {
        const key = savingsKey(opt.type, opt.term);
        const checked = key === currentKey ? ' checked' : '';
        const discount = opt.discountPercent != null
          ? `<span class="savings-discount">~${opt.discountPercent}% discount</span>`
          : '';
        html += `
          <label class="savings-radio">
            <input type="radio" name="${radioName}" value="${key}"${checked}${disabled}>
            <span class="savings-label">${this.escHtml(opt.label)}</span>
            ${discount}
          </label>`;
      }
      html += '</div>';
    }

    html += '</div>';
    return html;
  }

  renderQuantity(item) {
    // Per-meter quantity model — render a table with per-meter inputs
    if (this.quantityModel === 'per_meter') {
      return this.renderPerMeterQuantity(item);
    }

    const type = item.selections.type || 'Consumption';
    const isConsumption = type === 'Consumption';
    const disabled = item.loading ? ' disabled' : '';

    let html = '<div class="quantity-row">';

    // Quantity (VMs / Instances / etc.)
    html += `
      <div class="quantity-group">
        <label class="form-label">${this.escHtml(this.quantityLabel)}</label>
        <input type="number" class="form-input" data-field="quantity"
               value="${item.quantity}" min="1" step="1"${disabled}>
      </div>`;

    // Duration only for Consumption (PAYG)
    if (isConsumption) {
      const unit = item.hoursUnit || 'hours';
      const displayValue = this.hoursToDisplay(item.hoursPerMonth, unit);
      html += `
        <div class="quantity-group quantity-duration">
          <label class="form-label">Duration</label>
          <div class="duration-input-group">
            <input type="number" class="form-input" data-field="duration"
                   value="${displayValue}" min="0" step="any"${disabled}>
            <select class="form-select duration-unit" data-field="hoursUnit"${disabled}>
              <option value="hours"${unit === 'hours' ? ' selected' : ''}>Hours</option>
              <option value="days"${unit === 'days' ? ' selected' : ''}>Days</option>
              <option value="months"${unit === 'months' ? ' selected' : ''}>Months</option>
            </select>
          </div>
        </div>`;
    }

    html += '</div>';
    return html;
  }

  renderPerMeterQuantity(item) {
    if (!item.metersCache) {
      return '<div class="quantity-row"><span class="form-hint">Select configuration to see meters...</span></div>';
    }

    // Get unique meter names from Consumption groups for quantity inputs
    const type = item.selections.type || 'Consumption';
    const term = item.selections.term || null;
    let matched = item.metersCache.filter(g => g.type === type);
    if (term) matched = matched.filter(g => g.term === term);
    // If no groups match selected type/term, fall back to Consumption
    if (matched.length === 0) {
      matched = item.metersCache.filter(g => g.type === 'Consumption');
    }

    // Deduplicate by meter name + unit (defensive: backend already deduplicates)
    const seen = new Set();
    const meterInfos = [];
    for (const g of matched) {
      const dedupKey = `${g.meter}|${g.unit}`;
      if (!seen.has(dedupKey)) {
        seen.add(dedupKey);
        meterInfos.push({ name: g.meter, unit: g.unit, tiers: g.tiers });
      }
    }

    if (meterInfos.length === 0) return '';

    const disabled = item.loading ? ' disabled' : '';
    const meterQty = item.meterQuantities || {};
    const hourlyDetails = item.meterHourlyDetails || {};
    const dailyDetails = item.meterDailyDetails || {};

    let html = '<div class="per-meter-quantity">';

    // Sort meters by meter_order config (substring match)
    const meterOrder = item.serviceConfig?.meter_order || [];
    if (meterOrder.length > 0) {
      meterInfos.sort((a, b) => {
        const ai = meterOrder.findIndex(p => a.name.includes(p));
        const bi = meterOrder.findIndex(p => b.name.includes(p));
        return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
      });
    }

    const freeOffsets = this.computeMeterFreeOffsets(item);
    const meterLabels = item.serviceConfig?.meter_labels || {};

    for (const m of meterInfos) {
      const isHourly = m.unit === '1 Hour' || m.unit === '1/Hour';
      const isDaily = m.unit === '1 Day' || m.unit === '1/Day';
      const isMonthly = m.unit === '1/Month';
      const unitPrice = m.tiers?.[0]?.unit_price ?? 0;
      // Compute this meter's cost for display (applying free offset if any)
      const usage = meterQty[m.name] ?? 0;
      const freeAmount = freeOffsets[m.name] || 0;
      const effectiveUsage = Math.max(0, usage - freeAmount);
      const meterCost = this.computeSingleMeterCost(m.tiers, effectiveUsage);

      const displayName = this.getMeterDisplayName(m.name, meterLabels);

      html += `<div class="per-meter-section">`;
      html += `<div class="per-meter-header">${this.escHtml(displayName)}</div>`;

      // Free tier hint: cross-meter free allocation takes priority over API-based free tier
      if (freeAmount > 0) {
        const freeUnitLabel = m.unit === '1M' ? ' Million' : m.unit === '10K' ? ' × 10K' : '';
        html += `<div class="per-meter-free-hint"><span class="free-amount">${freeAmount.toLocaleString()}${freeUnitLabel}</span><span class="free-label"> Free ${this.escHtml(displayName)}</span></div>`;
      } else {
        const freeTierInfo = this.getFreeTierInfo(m.tiers, m.unit);
        if (freeTierInfo) {
          html += `<div class="per-meter-free-hint"><span class="info-icon">ⓘ</span> ${this.escHtml(freeTierInfo)}</div>`;
        }
      }

      html += '<div class="per-meter-input-row">';

      if (isHourly) {
        // Hourly meter: units × hours × price = cost
        const details = hourlyDetails[m.name] || { units: 0, hours: 730 };
        html += `
          <div class="per-meter-field">
            <input type="number" class="form-input per-meter-hourly-units" data-meter="${this.escHtml(m.name)}"
                   value="${details.units}" min="0" step="1"${disabled}>
            <span class="per-meter-field-label">${this.escHtml(this.getUnitLabel(m.name))}</span>
          </div>
          <span class="per-meter-op">×</span>
          <div class="per-meter-field">
            <input type="number" class="form-input per-meter-hourly-hours" data-meter="${this.escHtml(m.name)}"
                   value="${details.hours}" min="0" step="any"${disabled}>
            <span class="per-meter-field-label">Hours</span>
          </div>
          <span class="per-meter-op">×</span>
          <div class="per-meter-field">
            <span class="per-meter-price">${fmt.format(unitPrice)}</span>
            <span class="per-meter-field-label">Per ${this.escHtml(this.getUnitLabel(m.name))} Hour</span>
          </div>`;
      } else if (isDaily) {
        // Daily meter: units × days × price = cost
        const details = dailyDetails[m.name] || { units: 0, days: 31 };
        html += `
          <div class="per-meter-field">
            <input type="number" class="form-input per-meter-daily-units" data-meter="${this.escHtml(m.name)}"
                   value="${details.units}" min="0" step="1"${disabled}>
            <span class="per-meter-field-label">${this.escHtml(this.getUnitLabel(m.name))}</span>
          </div>
          <span class="per-meter-op">×</span>
          <div class="per-meter-field">
            <input type="number" class="form-input per-meter-daily-days" data-meter="${this.escHtml(m.name)}"
                   value="${details.days}" min="0" step="1"${disabled}>
            <span class="per-meter-field-label">Days</span>
          </div>
          <span class="per-meter-op">×</span>
          <div class="per-meter-field">
            <span class="per-meter-price">${fmt.format(unitPrice)}</span>
            <span class="per-meter-field-label">Per day</span>
          </div>`;
      } else if (isMonthly) {
        // Monthly fixed-fee meter: units × price/mo = cost
        const baseQty = meterQty[m.name] ?? 0;
        html += `
          <div class="per-meter-field">
            <input type="number" class="form-input per-meter-input" data-meter="${this.escHtml(m.name)}"
                   value="${baseQty}" min="0" step="1"${disabled}>
            <span class="per-meter-field-label">${this.escHtml(this.getUnitLabel(m.name))}</span>
          </div>
          <span class="per-meter-op">×</span>
          <div class="per-meter-field">
            <span class="per-meter-price">${fmt.format(unitPrice)}/mo</span>
          </div>`;
      } else {
        // Volume meter: quantity input with optional unit conversion (GB/TB)
        const baseQty = meterQty[m.name] ?? 0;
        const volumeUnits = item.meterVolumeUnits || {};
        const isGB = m.unit === '1 GB';
        const displayUnit = isGB ? (volumeUnits[m.name] || 'GB') : null;
        const displayQty = displayUnit === 'TB' ? baseQty / 1024 : baseQty;

        html += `
          <div class="per-meter-field">
            <input type="number" class="form-input per-meter-input" data-meter="${this.escHtml(m.name)}"
                   value="${displayQty}" min="0" step="any"${disabled}>`;
        if (isGB) {
          html += `
            <select class="form-select per-meter-volume-unit" data-meter="${this.escHtml(m.name)}"${disabled}>
              <option value="GB"${displayUnit === 'GB' ? ' selected' : ''}>GB</option>
              <option value="TB"${displayUnit === 'TB' ? ' selected' : ''}>TB</option>
            </select>`;
        }
        html += `
            <span class="per-meter-field-label">${this.escHtml(this.getVolumeLabel(m.name, m.unit))}</span>
          </div>`;
      }

      // Cost display
      html += `
        <span class="per-meter-eq">=</span>
        <span class="per-meter-cost">${fmt.format(meterCost)}</span>
      `;

      html += '</div></div>';  // close input-row and section
    }

    html += '</div>';
    return html;
  }

  /**
   * Return the display label for a meter name using endsWith matching (longest key wins).
   * e.g. "Standard Unit" with labels {"Unit": "Units"} → "Units"
   */
  getMeterDisplayName(meterName, labels) {
    let bestKey = '', bestLabel = meterName;
    for (const [suffix, label] of Object.entries(labels)) {
      if (meterName.endsWith(suffix) && suffix.length > bestKey.length) {
        bestKey = suffix;
        bestLabel = label;
      }
    }
    return bestLabel;
  }

  /**
   * Compute free offsets for meters that have a cross-meter free allocation.
   * e.g. SignalR: Standard Message free = Standard Unit units × days × 1M
   */
  computeMeterFreeOffsets(item) {
    const config = item.serviceConfig?.meter_free_quota;
    if (!config) return {};
    const offsets = {};
    for (const [meterName, def] of Object.entries(config)) {
      if (def.fixed != null) {
        offsets[meterName] = def.fixed;
      } else if (def.ref_meter) {
        offsets[meterName] = (item.meterQuantities?.[def.ref_meter] || 0) * (def.free_per_unit || 0);
      }
    }
    return offsets;
  }

  /** Compute cost for a single meter given its tiers and usage. */
  computeSingleMeterCost(tiers, usage) {
    if (!tiers || tiers.length === 0 || usage <= 0) return 0;
    const sorted = [...tiers].sort((a, b) => a.tier_min_units - b.tier_min_units);
    let total = 0;
    for (let i = 0; i < sorted.length; i++) {
      const tierStart = sorted[i].tier_min_units;
      const tierPrice = sorted[i].unit_price;
      if (usage <= tierStart) break;
      const tierEnd = i + 1 < sorted.length ? sorted[i + 1].tier_min_units : Infinity;
      total += (Math.min(usage, tierEnd) - tierStart) * tierPrice;
    }
    return total;
  }

  /** Extract a short unit label from meter name (e.g. "Standard Throughput Unit" → "Throughput Units") */
  getUnitLabel(meterName) {
    // Try to extract a meaningful label; fall back to "Units"
    const lower = meterName.toLowerCase();
    if (lower.includes('throughput')) return 'Throughput Units';
    if (lower.includes('deployment')) return 'Deployments';
    if (lower.includes('messaging unit')) return 'Messaging Units';
    if (lower.includes('base unit')) return 'Namespaces';
    if (lower.includes('listener unit')) return 'Listener Units';
    if (lower.includes('capacity unit')) return 'Capacity Units';
    return 'Units';
  }

  /** Get a short label for volume meter inputs instead of the full meter name. */
  getVolumeLabel(meterName, unit) {
    if (unit === '1M') return 'Million';
    if (unit === '10K') return '× 10K';
    if (unit === '100 Hours') return '× 100-Hour Blocks';
    if (unit === '1') {
      if (meterName.toLowerCase().includes('connection')) return 'Connections';
      return 'Units';
    }
    return unit;
  }

  /** Generate free-tier hint text if the first tier starts at 0 with price 0. */
  getFreeTierInfo(tiers, unit) {
    if (!tiers || tiers.length < 2) return null;
    const sorted = [...tiers].sort((a, b) => a.tier_min_units - b.tier_min_units);
    if (sorted[0].tier_min_units === 0 && sorted[0].unit_price === 0) {
      const freeAmount = sorted[1].tier_min_units;
      const unitLabel = (unit === '1 Hour' || unit === '1/Hour') ? 'hours'
                      : (unit === '1 Day' || unit === '1/Day') ? 'days'
                      : unit;
      return `The first ${freeAmount.toLocaleString()} ${unitLabel} per month are included.`;
    }
    return null;
  }

  hoursToDisplay(hours, unit) {
    if (unit === 'days') return +(hours / 24).toFixed(1);
    if (unit === 'months') return +(hours / 730).toFixed(2);
    return hours;
  }

  displayToHours(value, unit) {
    if (unit === 'days') return value * 24;
    if (unit === 'months') return value * 730;
    return value;
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

  renderHeaderSummary(item) {
    const sku = item.selections.skuName;
    if (!sku) return '';

    const type = item.selections.type || 'Consumption';
    const term = item.selections.term || null;

    let text;
    if (this.quantityModel === 'per_meter') {
      text = sku;
    } else {
      const qty = item.quantity || 1;
      text = `${qty} ${sku}`;

      // Duration for PAYG
      if (type === 'Consumption') {
        const unit = item.hoursUnit || 'hours';
        const displayValue = this.hoursToDisplay(item.hoursPerMonth, unit);
        const unitLabel = unit.charAt(0).toUpperCase() + unit.slice(1);
        text += ` \u00d7 ${displayValue} ${unitLabel}`;
      }
    }

    // Savings label
    text += ` (${this.getSavingsLabel(type, term)})`;

    return `<div class="card-summary-text">${this.escHtml(text)}</div>`;
  }

  renderHeaderUpfront(item) {
    const type = item.selections.type || 'Consumption';
    if (type !== 'Reservation' || item.upfrontCost == null) return '';
    return `<span class="card-cost-upfront">Upfront: ${fmt.format(item.upfrontCost)}</span>`;
  }

  getSavingsLabel(type, term) {
    if (type === 'Consumption') return 'Pay as you go';
    if (type === 'Reservation') return term ? `${term} Reserved` : 'Reserved';
    if (type === 'SavingsPlanConsumption') return term ? `${term} Savings Plan` : 'Savings Plan';
    return type;
  }

  renderPriceSummary(item) {
    if (item.cost == null) return '';

    const type = item.selections.type || 'Consumption';
    let html = '<div class="price-summary">';

    // Upfront for Reservation
    if (type === 'Reservation' && item.upfrontCost != null) {
      html += `
        <div class="price-summary-row">
          <span>Upfront cost</span>
          <span>${fmt.format(item.upfrontCost)}</span>
        </div>`;
    }

    // Monthly cost
    html += `
      <div class="price-summary-row price-summary-total">
        <span>Monthly cost</span>
        <span>${fmt.format(item.cost)}</span>
      </div>`;

    // PAYG equivalent for non-Consumption
    if (type !== 'Consumption' && item.paygCost != null) {
      html += `
        <div class="price-summary-row price-summary-payg">
          <span>PAYG equivalent</span>
          <span class="price-strikethrough">${fmt.format(item.paygCost)}</span>
        </div>`;
    }

    html += '</div>';
    return html;
  }

  renderDiscountBadge(item) {
    if (item.cost == null || !item.paygCost || item.paygCost <= 0) return '';
    const type = item.selections.type || 'Consumption';
    if (type === 'Consumption') return '';

    // item.cost is already monthly (calculateLocalPrice handles Reservation conversion)
    const discount = ((item.paygCost - item.cost) / item.paygCost) * 100;
    if (discount <= 0) return '';
    return `<span class="card-discount">~${Math.round(discount)}% discount</span>`;
  }

  escHtml(s) {
    if (!s) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // ── Inline rename ───────────────────────────────────────

  startEditName() {
    const titleText = this.el.querySelector('.card-title-text');
    const editBtn = this.el.querySelector('.card-edit-name-btn');
    if (!titleText) return;

    const item = this.item;
    const currentName = item.customName || `${item.serviceName} #${item.id}`;

    // Replace text span with an input
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'card-name-input';
    input.value = currentName;
    input.maxLength = 60;
    titleText.replaceWith(input);
    if (editBtn) editBtn.classList.add('hidden');
    input.focus();
    input.select();

    const commit = () => {
      const val = input.value.trim();
      const defaultName = `${item.serviceName} #${item.id}`;
      item.customName = val && val !== defaultName ? val : null;
      updateItem(this.itemId, item);
      this.render();
    };

    input.addEventListener('blur', commit);
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') input.blur();
      if (e.key === 'Escape') { input.value = currentName; input.blur(); }
    });
  }

  // ── Events ──────────────────────────────────────────────

  bindEvents() {
    // Dropdowns (exclude duration-unit and per-meter-volume-unit which have their own handlers)
    this.el.querySelectorAll('.form-select:not(.duration-unit):not(.per-meter-volume-unit)').forEach(sel => {
      sel.addEventListener('change', (e) => this.onSelectChange(e));
    });

    // Savings radio buttons
    this.el.querySelectorAll('.savings-section input[type="radio"]').forEach(radio => {
      radio.addEventListener('change', (e) => this.onSavingsChange(e.target.value));
    });

    // Quantity + duration inputs
    this.el.querySelectorAll('.form-input[data-field="quantity"], .form-input[data-field="duration"]').forEach(inp => {
      inp.addEventListener('input', (e) => this.onQuantityChange(e));
    });

    // Per-meter quantity inputs (volume meters)
    this.el.querySelectorAll('.per-meter-input').forEach(inp => {
      inp.addEventListener('input', (e) => this.onPerMeterQuantityChange(e));
    });

    // Per-meter hourly inputs (units and hours)
    this.el.querySelectorAll('.per-meter-hourly-units, .per-meter-hourly-hours').forEach(inp => {
      inp.addEventListener('input', (e) => this.onPerMeterHourlyChange(e));
    });
    this.el.querySelectorAll('.per-meter-daily-units, .per-meter-daily-days').forEach(inp => {
      inp.addEventListener('input', (e) => this.onPerMeterDailyChange(e));
    });

    // Per-meter volume unit selector (GB/TB)
    this.el.querySelectorAll('.per-meter-volume-unit').forEach(sel => {
      sel.addEventListener('change', (e) => this.onPerMeterVolumeUnitChange(e));
    });

    // Duration unit selector
    this.el.querySelectorAll('.duration-unit').forEach(sel => {
      sel.addEventListener('change', (e) => {
        const item = this.item;
        if (!item) return;
        item.hoursUnit = e.target.value;
        updateItem(this.itemId, item);
        this.render();
      });
    });

    // Edit name (click on title text or pencil icon)
    this.el.querySelectorAll('[data-action="edit-name"]').forEach(el => {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        this.startEditName();
      });
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

  onSavingsChange(value) {
    const item = this.item;
    if (!item) return;
    const [type, term] = value.split('|');
    item.selections.type = type;
    item.selections.term = term || null;
    if (!term) delete item.selections.term;
    updateItem(this.itemId, item);
    this.recalculateLocal();
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
      updateItem(this.itemId, item);
      this.recalculateLocal();
      return;  // No cascade needed for savings changes
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
      if (this.staticSubs.has(subField)) {
        // Clear all non-static sub-selections
        for (const key of Object.keys(item.subSelections)) {
          if (!this.staticSubs.has(key)) delete item.subSelections[key];
        }
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
        for (const key of Object.keys(item.subSelections)) {
          if (!this.staticSubs.has(key)) delete item.subSelections[key];
        }
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

    if (field === 'duration') {
      item.hoursPerMonth = this.displayToHours(value, item.hoursUnit || 'hours');
    } else {
      item[field] = value;
    }
    updateItem(this.itemId, item);

    debounce(`qty-${this.itemId}`, () => this.recalculateLocal(), 300);
  }

  onPerMeterQuantityChange(e) {
    const meterName = e.target.dataset.meter;
    const displayValue = parseFloat(e.target.value) || 0;
    const item = this.item;
    if (!item) return;

    if (!item.meterQuantities) item.meterQuantities = {};
    // Convert display value to base unit (GB) if volume unit is TB
    const volumeUnit = (item.meterVolumeUnits || {})[meterName] || 'GB';
    item.meterQuantities[meterName] = volumeUnit === 'TB' ? displayValue * 1024 : displayValue;
    updateItem(this.itemId, item);

    debounce(`qty-${this.itemId}`, () => this.recalculateLocal(), 300);
  }

  onPerMeterVolumeUnitChange(e) {
    const meterName = e.target.dataset.meter;
    const newUnit = e.target.value;  // 'GB' or 'TB'
    const item = this.item;
    if (!item) return;

    if (!item.meterVolumeUnits) item.meterVolumeUnits = {};
    item.meterVolumeUnits[meterName] = newUnit;
    // meterQuantities stays in base unit (GB), no conversion needed
    updateItem(this.itemId, item);
    this.render();
  }

  onPerMeterHourlyChange(e) {
    const meterName = e.target.dataset.meter;
    const value = parseFloat(e.target.value) || 0;
    const item = this.item;
    if (!item) return;

    if (!item.meterHourlyDetails) item.meterHourlyDetails = {};
    if (!item.meterHourlyDetails[meterName]) {
      item.meterHourlyDetails[meterName] = { units: 0, hours: 730 };
    }

    const isUnits = e.target.classList.contains('per-meter-hourly-units');
    if (isUnits) {
      item.meterHourlyDetails[meterName].units = value;
    } else {
      item.meterHourlyDetails[meterName].hours = value;
    }

    // Resolve final usage: units × hours
    const details = item.meterHourlyDetails[meterName];
    if (!item.meterQuantities) item.meterQuantities = {};
    item.meterQuantities[meterName] = details.units * details.hours;
    updateItem(this.itemId, item);

    debounce(`qty-${this.itemId}`, () => this.recalculateLocal(), 300);
  }

  onPerMeterDailyChange(e) {
    const meterName = e.target.dataset.meter;
    const value = parseFloat(e.target.value) || 0;
    const item = this.item;
    if (!item) return;

    if (!item.meterDailyDetails) item.meterDailyDetails = {};
    if (!item.meterDailyDetails[meterName]) {
      item.meterDailyDetails[meterName] = { units: 0, days: 31 };
    }

    const isUnits = e.target.classList.contains('per-meter-daily-units');
    if (isUnits) {
      item.meterDailyDetails[meterName].units = value;
    } else {
      item.meterDailyDetails[meterName].days = value;
    }

    // Resolve final usage: units × days
    const details = item.meterDailyDetails[meterName];
    if (!item.meterQuantities) item.meterQuantities = {};
    item.meterQuantities[meterName] = details.units * details.days;
    updateItem(this.itemId, item);

    debounce(`qty-${this.itemId}`, () => this.recalculateLocal(), 300);
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
      const _staticSubs = this.staticSubs;
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
              if (_staticSubs.has(sd.field)) continue;
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
          if (_staticSubs.has(sd.field)) continue;
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

      // Fetch meters and calculate locally if fully configured
      this.fetchAndCacheMeters();

    } catch (err) {
      if (err.name === 'AbortError') return;
      updateItem(this.itemId, { loading: false, error: err.message });
      this.render();
    }
  }

  async fetchAndCacheMeters() {
    const item = this.item;
    if (!item) return;

    const { armRegionName, productName, skuName } = item.selections;
    if (!armRegionName || !productName || !skuName) {
      updateItem(this.itemId, { cost: null, meters: null });
      this.render();
      emit('total-changed');
      return;
    }

    const cacheKey = `${armRegionName}|${productName}|${skuName}`;
    if (item.metersCacheKey === cacheKey && item.metersCache) {
      // Cache hit — calculate locally without API call
      this.recalculateLocal();
      return;
    }

    try {
      const resp = await fetchMeters(
        this.itemId, item.serviceName, armRegionName, productName, skuName,
      );
      updateItem(this.itemId, {
        metersCache: resp.groups,
        metersCacheKey: cacheKey,
        meterQuantities: {},       // Clear per-meter quantities on cache refresh
        meterHourlyDetails: {},    // Clear hourly decomposition too
        meterVolumeUnits: {},      // Clear volume unit selections too
      });
      this.recalculateLocal();
    } catch (err) {
      if (err.name === 'AbortError') return;
      console.warn('Meters fetch error:', err);
    }
  }

  recalculateLocal() {
    const item = this.item;
    if (!item || !item.metersCache) return;

    const type = item.selections.type || 'Consumption';
    const term = item.selections.term || null;

    let result;
    if (this.quantityModel === 'per_meter') {
      result = calculatePerMeterPrice(
        item.metersCache, type, term,
        item.meterQuantities || {},
        this.computeMeterFreeOffsets(item),
      );
    } else {
      result = calculateLocalPrice(
        item.metersCache, type, term,
        item.quantity || 1, item.hoursPerMonth || 730,
      );
    }

    updateItem(this.itemId, {
      cost: result.monthlyCost,
      upfrontCost: result.upfrontCost,
      paygCost: result.paygCost,
      meters: result.meters,
      error: null,
    });

    // Preserve focus on per-meter inputs during re-render
    const focused = document.activeElement;
    let focusClass = null;
    let focusedMeter = null;
    if (focused?.dataset?.meter) {
      focusedMeter = focused.dataset.meter;
      for (const cls of ['per-meter-input', 'per-meter-hourly-units', 'per-meter-hourly-hours', 'per-meter-daily-units', 'per-meter-daily-days', 'per-meter-volume-unit']) {
        if (focused.classList.contains(cls)) { focusClass = cls; break; }
      }
    }
    const selStart = focused?.selectionStart;

    this.render();

    if (focusedMeter && focusClass) {
      const inp = this.el.querySelector(`.${focusClass}[data-meter="${CSS.escape(focusedMeter)}"]`);
      if (inp) {
        inp.focus();
        if (selStart != null) try { inp.setSelectionRange(selStart, selStart); } catch {}
      }
    }

    emit('total-changed');
  }
}
