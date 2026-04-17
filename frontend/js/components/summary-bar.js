/**
 * Summary bar — displays total upfront + monthly cost across all items.
 */

import { on, getTotalCost, getTotalUpfrontCost, state } from '../state.js';
import { makeFmt } from '../pricing.js';

/** Detect the dominant currency: CNY if any item has CNY, else USD. */
function detectCurrency() {
  return state.items.some(i => i.currency === 'CNY') ? 'CNY' : 'USD';
}

export function initSummaryBar(totalEl, upfrontEl, upfrontRowEl) {
  function refresh() {
    const fmt = makeFmt(detectCurrency());
    totalEl.textContent = fmt.format(getTotalCost());

    const upfront = getTotalUpfrontCost();
    upfrontEl.textContent = fmt.format(upfront);
    upfrontRowEl.classList.toggle('hidden', upfront === 0);
  }

  on('total-changed', refresh);
  on('item-removed', refresh);
  on('item-updated', refresh);
  refresh();
}
