/**
 * Cost Calculation display — collapsible section showing how price is computed.
 *
 * Three modes:
 * 1. instances_x_hours (default): N Instance x H Hours x price/hr = total
 * 2. per_meter (default): per-meter breakdown lines
 * 3. formula: custom display_steps from quantity_formula config
 */

import { makeFmt, makeFmtPrice } from '../pricing.js';

function esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/**
 * Render cost calculation HTML for instances_x_hours model.
 * @param {Object} item - estimate item state
 * @param {string} currency - 'USD' or 'CNY'
 * @returns {string} HTML
 */
function renderInstancesXHours(item, currency) {
  if (!item.meters?.length || item.cost == null) return '';

  const fmt = makeFmt(currency);
  const fmtPrice = makeFmtPrice(currency);
  const quantity = item.quantity || 1;
  const hours = item.hoursPerMonth || 730;
  const type = item.selections?.type || 'Consumption';

  let lines = '';

  if (type === 'Reservation' && item.upfrontCost != null) {
    // Reservation: show per-instance term price
    const perInstance = item.meters[0];
    if (perInstance) {
      lines += `<div class="calc-step">${quantity} Instance x ${fmtPrice.format(perInstance.usage > 0 ? perInstance.monthly_cost / quantity : 0)}/term = ${fmt.format(item.upfrontCost)}</div>`;
    }
  } else {
    // PAYG / SavingsPlan: quantity x hours x price
    for (const m of item.meters) {
      if (m.usage === 0 && m.monthly_cost === 0) continue;
      const unitPrice = m.usage > 0 ? m.monthly_cost / m.usage : 0;
      lines += `<div class="calc-step">${quantity} x ${hours} Hours x ${fmtPrice.format(unitPrice)}/hr = ${fmt.format(m.monthly_cost)}</div>`;
    }
  }

  if (!lines) return '';

  lines += `<div class="calc-total">Monthly: ${fmt.format(item.cost)}</div>`;
  return lines;
}

/**
 * Render cost calculation HTML for per_meter model.
 * @param {Object} item - estimate item state
 * @param {string} currency - 'USD' or 'CNY'
 * @returns {string} HTML
 */
function renderPerMeter(item, currency) {
  if (!item.meters?.length || item.cost == null) return '';

  const fmt = makeFmt(currency);
  const fmtPrice = makeFmtPrice(currency);
  let lines = '';
  for (const m of item.meters) {
    if (m.usage === 0 && m.monthly_cost === 0) continue;
    const unitPrice = m.usage > 0 ? m.monthly_cost / m.usage : 0;
    lines += `<div class="calc-step"><span class="calc-meter-name">${esc(m.meter)}</span>: ${m.usage.toLocaleString()} ${esc(m.unit)} x ${fmtPrice.format(unitPrice)} = ${fmt.format(m.monthly_cost)}</div>`;
  }

  if (!lines) return '';

  lines += `<div class="calc-total">Monthly: ${fmt.format(item.cost)}</div>`;
  return lines;
}

/**
 * Render cost calculation HTML from formula display_steps.
 * @param {string[]} steps - resolved display_steps with values filled in
 * @param {number} monthlyCost
 * @param {string} currency - 'USD' or 'CNY'
 * @returns {string} HTML
 */
function renderFormulaSteps(steps, monthlyCost, currency) {
  if (!steps?.length) return '';

  const fmt = makeFmt(currency);
  let lines = '';
  for (const step of steps) {
    lines += `<div class="calc-step">${esc(step)}</div>`;
  }
  if (monthlyCost != null) {
    lines += `<div class="calc-total">Monthly: ${fmt.format(monthlyCost)}</div>`;
  }
  return lines;
}

/**
 * Build full collapsible cost calculation HTML block.
 *
 * @param {Object} opts
 * @param {Object} opts.item - estimate item state
 * @param {string} opts.quantityModel - 'instances_x_hours' | 'per_meter'
 * @param {string[]|null} opts.formulaSteps - resolved display_steps if formula active
 * @param {boolean} opts.open - whether section is expanded
 * @param {string} [opts.currency] - 'USD' or 'CNY' (default: 'USD')
 * @returns {string} HTML
 */
export function renderCostCalculation({ item, quantityModel, formulaSteps, open, currency = 'USD' }) {
  if (item.cost == null) return '';

  let innerHtml;
  if (formulaSteps?.length) {
    innerHtml = renderFormulaSteps(formulaSteps, item.cost, currency);
  } else if (quantityModel === 'per_meter') {
    innerHtml = renderPerMeter(item, currency);
  } else {
    innerHtml = renderInstancesXHours(item, currency);
  }

  if (!innerHtml) return '';

  const arrowChar = open ? '\u25BE' : '\u25B8';
  const wrapClass = open ? 'calc-detail' : 'calc-detail hidden';

  return `
    <div class="cost-calculation-section">
      <button class="calc-toggle" data-action="toggle-cost-calc">
        <span class="arrow">${arrowChar}</span> View Cost Calculation
      </button>
      <div class="${wrapClass}">
        ${innerHtml}
      </div>
    </div>
  `;
}
