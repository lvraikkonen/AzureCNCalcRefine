/**
 * App entry point — initializes all components.
 */

import { renderServicePicker } from './components/service-picker.js';
import { initEstimateList } from './components/estimate-list.js';
import { initSummaryBar } from './components/summary-bar.js';

document.addEventListener('DOMContentLoaded', () => {
  renderServicePicker(document.getElementById('service-grid'));
  initEstimateList(
    document.getElementById('estimate-list'),
    document.getElementById('estimate-empty'),
  );
  initSummaryBar(document.getElementById('summary-total'));
});
