/**
 * Summary bar — displays total monthly cost across all items.
 */

import { on, getTotalCost } from '../state.js';

const fmt = new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD',
  minimumFractionDigits: 2, maximumFractionDigits: 2,
});

export function initSummaryBar(totalEl) {
  function refresh() {
    totalEl.textContent = fmt.format(getTotalCost());
  }

  on('total-changed', refresh);
  on('item-removed', refresh);
  refresh();
}
