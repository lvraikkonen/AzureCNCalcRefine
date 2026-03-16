/**
 * App entry point — initializes all components.
 */

import { renderServicePicker } from './components/service-picker.js';
import { initEstimateList } from './components/estimate-list.js';
import { initSummaryBar } from './components/summary-bar.js';

document.addEventListener('DOMContentLoaded', () => {
  renderServicePicker();
  initEstimateList(
    document.getElementById('estimate-list'),
    document.getElementById('estimate-empty'),
  );
  initSummaryBar(
    document.getElementById('summary-total'),
    document.getElementById('summary-upfront'),
    document.getElementById('summary-upfront-row'),
  );
});
