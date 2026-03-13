/**
 * Estimate list — manages the collection of estimate cards.
 */

import { on } from '../state.js';
import { EstimateCard } from './estimate-card.js';

const cards = new Map(); // itemId → EstimateCard

export function initEstimateList(listEl, emptyEl) {
  // ── Collapse toolbar ──────────────────────────────────────
  const toolbar = document.createElement('div');
  toolbar.className = 'estimate-toolbar hidden';
  toolbar.innerHTML = `
    <button class="btn btn-sm btn-outline" data-action="collapse-all">Collapse All</button>
    <button class="btn btn-sm btn-outline" data-action="expand-all">Expand All</button>
  `;
  listEl.parentNode.insertBefore(toolbar, listEl);

  toolbar.addEventListener('click', (e) => {
    const action = e.target.dataset.action;
    if (!action) return;
    const collapse = action === 'collapse-all';
    for (const card of cards.values()) {
      card.collapsed = collapse;
      card.el.classList.toggle('collapsed', collapse);
      const chevron = card.el.querySelector('.chevron');
      if (chevron) chevron.textContent = collapse ? '▸' : '▾';
      const btn = card.el.querySelector('[data-action="toggle-collapse"]');
      if (btn) btn.title = collapse ? 'Expand' : 'Collapse';
    }
  });

  function updateVisibility() {
    const hasCards = cards.size > 0;
    emptyEl.classList.toggle('hidden', hasCards);
    toolbar.classList.toggle('hidden', !hasCards);
  }

  on('item-added', (e) => {
    const { item } = e.detail;
    const card = new EstimateCard(item.id);
    cards.set(item.id, card);
    listEl.appendChild(card.el);
    updateVisibility();
  });

  on('item-removed', (e) => {
    const { id } = e.detail;
    const card = cards.get(id);
    if (card) {
      card.el.remove();
      cards.delete(id);
    }
    updateVisibility();
  });
}
