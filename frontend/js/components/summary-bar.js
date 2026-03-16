/**
 * Summary bar — displays total upfront + monthly cost across all items.
 */

import { on, getTotalCost, getTotalUpfrontCost } from '../state.js';

const fmt = new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD',
  minimumFractionDigits: 2, maximumFractionDigits: 2,
});

export function initSummaryBar(totalEl, upfrontEl, upfrontRowEl) {
  function refresh() {
    totalEl.textContent = fmt.format(getTotalCost());

    const upfront = getTotalUpfrontCost();
    upfrontEl.textContent = fmt.format(upfront);
    upfrontRowEl.classList.toggle('hidden', upfront === 0);
  }

  on('total-changed', refresh);
  on('item-removed', refresh);
  refresh();
}
