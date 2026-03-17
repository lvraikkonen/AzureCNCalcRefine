/**
 * Frontend pricing calculation engine — pure functions, no DOM dependency.
 *
 * Mirrors the backend logic in app/services/global_pricing.py and
 * app/api/explore.py (_calculate_one) for local price computation.
 */

/** Check if a unitOfMeasure represents hourly pricing. */
function isHourlyUnit(unit) {
  return unit === '1 Hour' || unit === '1/Hour';
}

/** Convert a term string like "1 Year", "3 Years", "5 Years" to months. */
function termToMonths(term) {
  const match = term && term.match(/^(\d+)\s+Year/i);
  return match ? parseInt(match[1], 10) * 12 : 12;
}

/**
 * Calculate cost for tiered pricing.
 * Port of app/services/global_pricing.py:calculate_tiered_cost
 *
 * @param {Array<{tier_min_units: number, unit_price: number}>} tiers
 * @param {number} usage
 * @returns {number} total cost
 */
export function calculateTieredCost(tiers, usage) {
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

/**
 * Calculate price locally from cached meter groups.
 * Port of app/api/explore.py:_calculate_one (lines 331-418).
 *
 * @param {Array} metersGroups - MeterGroup[] from /meters response (all type/term)
 * @param {string} type - 'Consumption' | 'Reservation' | 'SavingsPlanConsumption'
 * @param {string|null} term - '1 Year' | '3 Years' | null
 * @param {number} quantity
 * @param {number} hoursPerMonth
 * @returns {{ monthlyCost: number, upfrontCost: number|null, paygCost: number|null, meters: Array }}
 */
export function calculateLocalPrice(metersGroups, type, term, quantity, hoursPerMonth) {
  // Filter groups by type
  let matched = metersGroups.filter(g => g.type === type);

  // Filter by term (for Reservation / SavingsPlan); backend stores "-" for empty term
  if (term) {
    matched = matched.filter(g => g.term === term);
  }

  const meters = [];
  let total = 0;

  for (const group of matched) {
    const unit = group.unit;
    let usage, cost;

    if (type === 'Reservation') {
      // Reservation: unitPrice is total for the term, per instance
      usage = quantity;
      cost = group.tiers[0].unit_price * quantity;
    } else if (isHourlyUnit(unit)) {
      // Per-hour pricing: usage = hours x instances
      usage = hoursPerMonth * quantity;
      cost = calculateTieredCost(group.tiers, usage);
    } else {
      // Other units: usage = quantity directly
      usage = quantity;
      cost = calculateTieredCost(group.tiers, usage);
    }

    meters.push({
      meter: group.meter,
      unit,
      usage,
      monthly_cost: cost,
    });
    total += cost;
  }

  let monthlyCost = total;
  let upfrontCost = null;

  // Reservation: total is the full term price; convert to monthly
  if (type === 'Reservation' && term) {
    upfrontCost = total;
    const termMonths = termToMonths(term);
    monthlyCost = total / termMonths;
  }

  // Compute PAYG baseline for discount comparison (non-Consumption only)
  let paygCost = null;
  if (type !== 'Consumption') {
    const consumptionGroups = metersGroups.filter(g => g.type === 'Consumption');
    if (consumptionGroups.length > 0) {
      let paygTotal = 0;
      for (const group of consumptionGroups) {
        if (isHourlyUnit(group.unit)) {
          paygTotal += calculateTieredCost(group.tiers, hoursPerMonth * quantity);
        } else {
          paygTotal += calculateTieredCost(group.tiers, quantity);
        }
      }
      paygCost = paygTotal;
    }
  }

  return { monthlyCost, upfrontCost, paygCost, meters };
}

/**
 * Calculate price for per-meter quantity model.
 * Each meter has an independent usage quantity supplied via meterQuantities.
 *
 * @param {Array} metersGroups - MeterGroup[] from /meters response (all type/term)
 * @param {string} type - 'Consumption' | 'Reservation' | 'SavingsPlanConsumption'
 * @param {string|null} term - '1 Year' | '3 Years' | null
 * @param {Object} meterQuantities - { meterName: number }
 * @returns {{ monthlyCost: number, upfrontCost: number|null, paygCost: number|null, meters: Array }}
 */
export function calculatePerMeterPrice(metersGroups, type, term, meterQuantities) {
  // Filter groups by type
  let matched = metersGroups.filter(g => g.type === type);

  // Filter by term (for Reservation / SavingsPlan)
  if (term) {
    matched = matched.filter(g => g.term === term);
  }

  const meters = [];
  let total = 0;

  for (const group of matched) {
    const usage = meterQuantities[group.meter] || 0;
    let cost;

    if (type === 'Reservation') {
      cost = group.tiers[0].unit_price * usage;
    } else {
      cost = calculateTieredCost(group.tiers, usage);
    }

    meters.push({
      meter: group.meter,
      unit: group.unit,
      usage,
      monthly_cost: cost,
    });
    total += cost;
  }

  let monthlyCost = total;
  let upfrontCost = null;

  if (type === 'Reservation' && term) {
    upfrontCost = total;
    const termMonths = termToMonths(term);
    monthlyCost = total / termMonths;
  }

  // Compute PAYG baseline for discount comparison
  let paygCost = null;
  if (type !== 'Consumption') {
    const consumptionGroups = metersGroups.filter(g => g.type === 'Consumption');
    if (consumptionGroups.length > 0) {
      let paygTotal = 0;
      for (const group of consumptionGroups) {
        const usage = meterQuantities[group.meter] || 0;
        paygTotal += calculateTieredCost(group.tiers, usage);
      }
      paygCost = paygTotal;
    }
  }

  return { monthlyCost, upfrontCost, paygCost, meters };
}

/**
 * Extract available savings options (type/term combos) from cached meter groups,
 * with discount percentages relative to PAYG.
 *
 * @param {Array} metersGroups - MeterGroup[] from /meters response
 * @param {number} quantity
 * @param {number} hoursPerMonth
 * @returns {Array<{type: string, term: string|null, label: string, discountPercent: number|null}>}
 */
export function getAvailableSavingsOptions(metersGroups, quantity = 1, hoursPerMonth = 730, opts = {}) {
  const { meterQuantities, quantityModel } = opts;

  // Collect unique (type, term) combinations
  const seen = new Set();
  const combos = [];
  for (const g of metersGroups) {
    const key = `${g.type}|${g.term === '-' ? '' : g.term}`;
    if (!seen.has(key)) {
      seen.add(key);
      combos.push({ type: g.type, term: g.term === '-' ? null : g.term });
    }
  }

  return combos.map(({ type, term }) => {
    let discountPercent = null;
    if (type !== 'Consumption') {
      let result;
      if (quantityModel === 'per_meter' && meterQuantities) {
        result = calculatePerMeterPrice(metersGroups, type, term, meterQuantities);
      } else {
        result = calculateLocalPrice(metersGroups, type, term, quantity, hoursPerMonth);
      }
      if (result.paygCost && result.paygCost > 0) {
        discountPercent = Math.round((result.paygCost - result.monthlyCost) / result.paygCost * 100);
      }
    }

    let label = 'Pay as you go';
    if (type === 'Reservation') {
      label = term ? `${term} Reserved` : 'Reserved';
    } else if (type === 'SavingsPlanConsumption') {
      label = term ? `${term} Savings Plan` : 'Savings Plan';
    }

    return { type, term, label, discountPercent };
  });
}
