/**
 * Service picker — renders service tiles with Add buttons.
 */

import { createItem } from '../state.js';
import { fetchPreload } from '../api.js';

const SERVICES = [
  { name: 'Virtual Machines', icon: '🖥️', available: true },
  { name: 'Storage', icon: '💾', available: false },
  { name: 'SQL Database', icon: '🗄️', available: false },
  { name: 'App Service', icon: '🌐', available: false },
];

export function renderServicePicker(container) {
  container.innerHTML = SERVICES.map(svc => `
    <div class="service-tile ${svc.available ? '' : 'disabled'}">
      <div class="service-tile-icon">${svc.icon}</div>
      <div class="service-tile-name">${svc.name}</div>
      <div class="service-tile-status">${svc.available ? 'Available' : 'Coming soon'}</div>
      ${svc.available
        ? `<button class="btn btn-primary btn-add" data-service="${svc.name}">+ Add</button>`
        : '<button class="btn btn-outline" disabled>Coming soon</button>'
      }
    </div>
  `).join('');

  // Fire-and-forget preload for all available services
  SERVICES.filter(s => s.available).forEach(svc => fetchPreload(svc.name));

  container.addEventListener('click', (e) => {
    const btn = e.target.closest('.btn-add');
    if (!btn) return;
    const serviceName = btn.dataset.service;
    createItem(serviceName);
  });
}
