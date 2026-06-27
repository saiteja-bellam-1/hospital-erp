#!/usr/bin/env node
/**
 * Lists frontend files with form inputs that lack a navigation scope
 * (FormNavContainer, native <form>, or Dialog).
 *
 * Usage: node frontend/scripts/audit-form-nav.js
 */
const { execSync } = require('child_process');
const path = require('path');

const root = path.join(__dirname, '..');

function rg(pattern) {
  try {
    return execSync(`rg -l "${pattern}" src`, { cwd: root, encoding: 'utf8' })
      .trim()
      .split('\n')
      .filter(Boolean);
  } catch {
    return [];
  }
}

const withInputs = new Set([
  ...rg('<Input'),
  ...rg('<Textarea'),
  ...rg('SelectTrigger'),
  ...rg('<input '),
]);

const withNav = new Set([
  ...rg('FormNavContainer'),
  ...rg('data-form-nav-root'),
  ...rg('<form'),
  ...rg('DialogContent'),
]);

const missing = [...withInputs].filter((f) => !withNav.has(f)).sort();

console.log(`Files with inputs: ${withInputs.size}`);
console.log(`Files with nav scope: ${withNav.size}`);
console.log(`Possibly missing explicit nav scope (${missing.length}):`);
missing.forEach((f) => console.log(`  - ${f}`));
