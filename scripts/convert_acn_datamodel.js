/**
 * Convert ACN calculator JS files to standard JSON.
 *
 * Usage: node scripts/convert_acn_datamodel.js
 *
 * Input:
 *   prod-config/calculatorconst.js   (constants + enums)
 *   prod-config/calculatordatamodel.js (service data with CalculatorConst refs)
 *
 * Output:
 *   prod-config/calculatordatamodel.json  (resolved service data, ~257 unique slugs)
 *   prod-config/calculatorconst.json      (all constant values)
 *   prod-config/duplicate_slugs.json      (duplicate slug report)
 */

const fs = require('fs');
const path = require('path');

const prodDir = path.join(__dirname, '..', 'prod-config');

// --- Step 1: Detect duplicate slugs via regex before JS execution ---
const datamodelRaw = fs.readFileSync(path.join(prodDir, 'calculatordatamodel.js'), 'utf8');

const slugPattern = /^\s*"([^"]+)"\s*:\s*\{/gm;
const slugOccurrences = {};
let match;
while ((match = slugPattern.exec(datamodelRaw)) !== null) {
  const slug = match[1];
  const lineNum = datamodelRaw.substring(0, match.index).split('\n').length;
  if (!slugOccurrences[slug]) {
    slugOccurrences[slug] = [];
  }
  slugOccurrences[slug].push(lineNum);
}

const duplicates = {};
for (const [slug, lines] of Object.entries(slugOccurrences)) {
  if (lines.length > 1) {
    duplicates[slug] = { occurrences: lines.length, lines };
  }
}

// --- Step 2: Execute JS files to resolve all references ---
const constCode = fs.readFileSync(path.join(prodDir, 'calculatorconst.js'), 'utf8');

// eval in this scope so CalculatorConst, PriceTierEnum, PricePeriodEnum are available
eval(constCode);
eval(datamodelRaw);

// --- Step 3: Write outputs ---
const serviceCount = Object.keys(CalculatorData.Services).length;

fs.writeFileSync(
  path.join(prodDir, 'calculatordatamodel.json'),
  JSON.stringify(CalculatorData, null, 2),
  'utf8'
);

fs.writeFileSync(
  path.join(prodDir, 'calculatorconst.json'),
  JSON.stringify(CalculatorConst, null, 2),
  'utf8'
);

fs.writeFileSync(
  path.join(prodDir, 'duplicate_slugs.json'),
  JSON.stringify(duplicates, null, 2),
  'utf8'
);

console.log(`Converted ${serviceCount} unique service slugs (after JS dedup).`);
console.log(`Found ${Object.keys(duplicates).length} duplicate slug(s):`);
for (const [slug, info] of Object.entries(duplicates)) {
  console.log(`  "${slug}": ${info.occurrences} occurrences at lines ${info.lines.join(', ')}`);
}
console.log(`\nOutput files:`);
console.log(`  ${path.join(prodDir, 'calculatordatamodel.json')}`);
console.log(`  ${path.join(prodDir, 'calculatorconst.json')}`);
console.log(`  ${path.join(prodDir, 'duplicate_slugs.json')}`);
