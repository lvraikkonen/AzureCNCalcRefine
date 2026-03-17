/**
 * Azure region display names and country/geography grouping.
 *
 * Maps Azure ARM region slugs (e.g. "eastus") to human-readable names
 * (e.g. "East US") and groups them by country/geography for the dropdown.
 */

const REGION_MAP = {
  // ── United States ─────────────────────────────
  centralus:        { display: 'Central US',        group: 'United States' },
  eastus:           { display: 'East US',           group: 'United States' },
  eastus2:          { display: 'East US 2',         group: 'United States' },
  northcentralus:   { display: 'North Central US',  group: 'United States' },
  southcentralus:   { display: 'South Central US',  group: 'United States' },
  westcentralus:    { display: 'West Central US',   group: 'United States' },
  westus:           { display: 'West US',           group: 'United States' },
  westus2:          { display: 'West US 2',         group: 'United States' },
  westus3:          { display: 'West US 3',         group: 'United States' },

  // ── US Government ─────────────────────────────
  usgovarizona:     { display: 'US Gov Arizona',    group: 'US Government' },
  usgovtexas:       { display: 'US Gov Texas',      group: 'US Government' },
  usgovvirginia:    { display: 'US Gov Virginia',   group: 'US Government' },

  // ── Canada ────────────────────────────────────
  canadacentral:    { display: 'Canada Central',    group: 'Canada' },
  canadaeast:       { display: 'Canada East',       group: 'Canada' },

  // ── Brazil ────────────────────────────────────
  brazilsouth:      { display: 'Brazil South',      group: 'Brazil' },
  brazilsoutheast:  { display: 'Brazil Southeast',  group: 'Brazil' },

  // ── Chile ─────────────────────────────────────
  chilecentral:     { display: 'Chile Central',     group: 'Chile' },

  // ── Mexico ────────────────────────────────────
  mexicocentral:    { display: 'Mexico Central',    group: 'Mexico' },

  // ── United Kingdom ────────────────────────────
  uksouth:          { display: 'UK South',          group: 'United Kingdom' },
  ukwest:           { display: 'UK West',           group: 'United Kingdom' },

  // ── Ireland ───────────────────────────────────
  northeurope:      { display: 'North Europe',      group: 'Ireland' },

  // ── Netherlands ───────────────────────────────
  westeurope:       { display: 'West Europe',       group: 'Netherlands' },

  // ── France ────────────────────────────────────
  francecentral:    { display: 'France Central',    group: 'France' },
  francesouth:      { display: 'France South',      group: 'France' },

  // ── Germany ───────────────────────────────────
  germanynorth:     { display: 'Germany North',     group: 'Germany' },
  germanywestcentral: { display: 'Germany West Central', group: 'Germany' },

  // ── Switzerland ───────────────────────────────
  switzerlandnorth: { display: 'Switzerland North', group: 'Switzerland' },
  switzerlandwest:  { display: 'Switzerland West',  group: 'Switzerland' },

  // ── Norway ────────────────────────────────────
  norwayeast:       { display: 'Norway East',       group: 'Norway' },
  norwaywest:       { display: 'Norway West',       group: 'Norway' },

  // ── Sweden ────────────────────────────────────
  swedencentral:    { display: 'Sweden Central',    group: 'Sweden' },
  swedensouth:      { display: 'Sweden South',      group: 'Sweden' },

  // ── Denmark ───────────────────────────────────
  denmarkeast:      { display: 'Denmark East',      group: 'Denmark' },

  // ── Poland ────────────────────────────────────
  polandcentral:    { display: 'Poland Central',    group: 'Poland' },

  // ── Italy ─────────────────────────────────────
  italynorth:       { display: 'Italy North',       group: 'Italy' },

  // ── Spain ─────────────────────────────────────
  spaincentral:     { display: 'Spain Central',     group: 'Spain' },

  // ── Austria ───────────────────────────────────
  austriaeast:      { display: 'Austria East',      group: 'Austria' },

  // ── Belgium ───────────────────────────────────
  belgiumcentral:   { display: 'Belgium Central',   group: 'Belgium' },

  // ── Israel ────────────────────────────────────
  israelcentral:    { display: 'Israel Central',    group: 'Israel' },
  israelnorthwest:  { display: 'Israel Northwest',  group: 'Israel' },

  // ── Qatar ─────────────────────────────────────
  qatarcentral:     { display: 'Qatar Central',     group: 'Qatar' },

  // ── UAE ───────────────────────────────────────
  uaecentral:       { display: 'UAE Central',       group: 'UAE' },
  uaenorth:         { display: 'UAE North',         group: 'UAE' },

  // ── South Africa ──────────────────────────────
  southafricanorth: { display: 'South Africa North', group: 'South Africa' },
  southafricawest:  { display: 'South Africa West',  group: 'South Africa' },

  // ── Australia ─────────────────────────────────
  australiacentral:  { display: 'Australia Central',    group: 'Australia' },
  australiacentral2: { display: 'Australia Central 2',  group: 'Australia' },
  australiaeast:     { display: 'Australia East',       group: 'Australia' },
  australiasoutheast:{ display: 'Australia Southeast',  group: 'Australia' },

  // ── New Zealand ───────────────────────────────
  newzealandnorth:  { display: 'New Zealand North', group: 'New Zealand' },

  // ── Japan ─────────────────────────────────────
  japaneast:        { display: 'Japan East',        group: 'Japan' },
  japanwest:        { display: 'Japan West',        group: 'Japan' },

  // ── Korea ─────────────────────────────────────
  koreacentral:     { display: 'Korea Central',     group: 'Korea' },
  koreasouth:       { display: 'Korea South',       group: 'Korea' },

  // ── India ─────────────────────────────────────
  centralindia:     { display: 'Central India',     group: 'India' },
  southindia:       { display: 'South India',       group: 'India' },
  westindia:        { display: 'West India',        group: 'India' },
  jioindiacentral:  { display: 'Jio India Central', group: 'India' },
  jioindiawest:     { display: 'Jio India West',    group: 'India' },

  // ── Hong Kong ─────────────────────────────────
  eastasia:         { display: 'East Asia',         group: 'Hong Kong' },

  // ── Singapore ─────────────────────────────────
  southeastasia:    { display: 'Southeast Asia',    group: 'Singapore' },

  // ── Indonesia ─────────────────────────────────
  indonesiacentral: { display: 'Indonesia Central', group: 'Indonesia' },

  // ── Malaysia ──────────────────────────────────
  malaysiawest:     { display: 'Malaysia West',     group: 'Malaysia' },

  // ── AT&T ──────────────────────────────────────
  attatlanta1:      { display: 'AT&T Atlanta',      group: 'AT&T' },
  attdallas1:       { display: 'AT&T Dallas',       group: 'AT&T' },
  attdetroit1:      { display: 'AT&T Detroit',      group: 'AT&T' },
};

/**
 * Get display name for a region slug.
 * Falls back to the slug itself if not mapped.
 */
export function getRegionDisplay(slug) {
  return REGION_MAP[slug]?.display || slug;
}

/**
 * Get country/geography group for a region slug.
 * Falls back to "Other" if not mapped.
 */
export function getRegionGroup(slug) {
  return REGION_MAP[slug]?.group || 'Other';
}

/**
 * Build grouped region options from a flat list of region slugs.
 * Returns an array of { group, regions: [{ slug, display }] } sorted by group name,
 * with "Global" first if present.
 *
 * @param {string[]} slugs - Region slugs from API
 * @returns {Array<{group: string, regions: Array<{slug: string, display: string}>}>}
 */
export function buildGroupedRegions(slugs) {
  const groups = new Map();

  for (const slug of slugs) {
    if (slug === 'Global') {
      if (!groups.has('Global')) groups.set('Global', []);
      groups.get('Global').push({ slug, display: 'Global' });
      continue;
    }
    const group = getRegionGroup(slug);
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group).push({ slug, display: getRegionDisplay(slug) });
  }

  // Sort regions within each group
  for (const regions of groups.values()) {
    regions.sort((a, b) => a.display.localeCompare(b.display));
  }

  // Sort groups alphabetically, with Global first
  const sorted = [...groups.entries()].sort(([a], [b]) => {
    if (a === 'Global') return -1;
    if (b === 'Global') return 1;
    return a.localeCompare(b);
  });

  return sorted.map(([group, regions]) => ({ group, regions }));
}
