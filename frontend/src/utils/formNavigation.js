/** Keyboard navigation between form fields (Enter / arrows) to reduce mouse use. */

export const NAV_SKIP_ATTR = 'data-nav-skip';
export const NAV_ROOT_ATTR = 'data-form-nav-root';
export const NAV_ROW_ATTR = 'data-nav-row';
export const NAV_COL_ATTR = 'data-nav-col';

const FOCUSABLE_SELECTOR = [
  `input:not([type="hidden"]):not([disabled]):not([${NAV_SKIP_ATTR}])`,
  `textarea:not([disabled]):not([${NAV_SKIP_ATTR}])`,
  `select:not([disabled]):not([${NAV_SKIP_ATTR}])`,
  `button[role="combobox"]:not([disabled]):not([${NAV_SKIP_ATTR}])`,
  `[data-form-nav]:not([disabled]):not([${NAV_SKIP_ATTR}])`,
].join(',');

export function isNavSkipped(el) {
  if (!el) return true;
  return el.hasAttribute(NAV_SKIP_ATTR) || Boolean(el.closest(`[${NAV_SKIP_ATTR}]`));
}

export function isFocusableField(el) {
  if (!el?.matches) return false;
  if (isNavSkipped(el)) return false;
  if (el.disabled) return false;
  if (el.readOnly && el.tagName !== 'SELECT') return false;
  if (el.type === 'hidden') return false;
  if (el.tabIndex < 0) return false;
  const tag = el.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (el.getAttribute('role') === 'combobox') return true;
  if (el.hasAttribute('data-form-nav')) return true;
  return false;
}

export function getFocusableFields(container) {
  if (!container) return [];
  return Array.from(container.querySelectorAll(FOCUSABLE_SELECTOR)).filter(isFocusableField);
}

export function sortByVisualPosition(fields) {
  return [...fields].sort((a, b) => {
    const ra = a.getBoundingClientRect();
    const rb = b.getBoundingClientRect();
    const rowDiff = ra.top - rb.top;
    if (Math.abs(rowDiff) > 10) return rowDiff;
    return ra.left - rb.left;
  });
}

function sameRow(a, b, threshold = 12) {
  return Math.abs(a.getBoundingClientRect().top - b.getBoundingClientRect().top) <= threshold;
}

function sortByTablePosition(fields) {
  return [...fields].sort((a, b) => {
    const rowA = a.getAttribute(NAV_ROW_ATTR) ?? '';
    const rowB = b.getAttribute(NAV_ROW_ATTR) ?? '';
    if (rowA !== rowB) {
      if (rowA === '') return 1;
      if (rowB === '') return -1;
      const na = Number(rowA);
      const nb = Number(rowB);
      if (!Number.isNaN(na) && !Number.isNaN(nb) && na !== nb) return na - nb;
      return rowA.localeCompare(rowB, undefined, { numeric: true });
    }
    const colA = Number(a.getAttribute(NAV_COL_ATTR) ?? '0');
    const colB = Number(b.getAttribute(NAV_COL_ATTR) ?? '0');
    if (colA !== colB) return colA - colB;
    return a.getBoundingClientRect().left - b.getBoundingClientRect().left;
  });
}

function orderedFields(container, mode) {
  const fields = getFocusableFields(container);
  if (mode === 'table') return sortByTablePosition(fields);
  if (mode === 'grid') return sortByVisualPosition(fields);
  return fields;
}

function findNextField(sorted, current, direction, mode) {
  const idx = sorted.indexOf(current);
  if (idx === -1) return null;

  if (direction === 'next') return sorted[idx + 1] ?? null;
  if (direction === 'prev') return sorted[idx - 1] ?? null;

  if (mode === 'grid' && (direction === 'left' || direction === 'right')) {
    const rowmates = sorted.filter((f) => sameRow(f, current));
    const rowIdx = rowmates.indexOf(current);
    if (direction === 'left') return rowmates[rowIdx - 1] ?? null;
    return rowmates[rowIdx + 1] ?? null;
  }

  if (mode === 'table' && (direction === 'left' || direction === 'right')) {
    const row = current.getAttribute(NAV_ROW_ATTR);
    if (!row) return null;
    const rowmates = sorted.filter((f) => f.getAttribute(NAV_ROW_ATTR) === row);
    const rowIdx = rowmates.indexOf(current);
    if (direction === 'left') return rowmates[rowIdx - 1] ?? null;
    return rowmates[rowIdx + 1] ?? null;
  }

  return null;
}

function isSelectOpen(target) {
  if (target.getAttribute('aria-expanded') === 'true') return true;
  if (target.closest('[role="listbox"]')) return true;
  if (target.closest('[data-radix-select-content]')) return true;
  return false;
}

function focusField(el) {
  el.focus();
  if (el.tagName === 'INPUT' && typeof el.select === 'function') {
    const t = el.type || 'text';
    if (['text', 'search', 'tel', 'email', 'url', 'number'].includes(t)) {
      try {
        el.select();
      } catch {
        /* ignore */
      }
    }
  }
}

/**
 * @param {KeyboardEvent} e
 * @param {HTMLElement} container
 * @param {{ mode?: 'linear' | 'grid' | 'table' }} [options]
 */
export function handleFormNavKeyDown(e, container, options = {}) {
  const { mode = 'linear' } = options;
  const target = e.target;
  if (!container?.contains(target) || !isFocusableField(target)) return;
  if (isNavSkipped(target)) return;
  if (isSelectOpen(target)) return;

  const tag = target.tagName;
  const isTextarea = tag === 'TEXTAREA';
  const isNumber = tag === 'INPUT' && target.type === 'number';
  const isCombobox = target.getAttribute('role') === 'combobox';

  let direction = null;

  if (e.key === 'Enter' && !e.shiftKey) {
    if (isCombobox) return;
    if (isTextarea && !(e.ctrlKey || e.metaKey)) return;
    direction = 'next';
  } else if (e.key === 'ArrowDown' && !e.altKey) {
    if (isNumber || isTextarea) return;
    if (isCombobox && target.getAttribute('aria-expanded') !== 'false') return;
    direction = 'next';
  } else if (e.key === 'ArrowUp' && !e.altKey) {
    if (isNumber) return;
    if (isCombobox) return;
    direction = 'prev';
  } else if (e.key === 'ArrowRight' && (mode === 'grid' || mode === 'table')) {
    direction = 'right';
  } else if (e.key === 'ArrowLeft' && (mode === 'grid' || mode === 'table')) {
    direction = 'left';
  }

  if (!direction) return;

  const sorted = orderedFields(container, mode);
  const next = findNextField(sorted, target, direction, mode);
  if (!next) return;

  e.preventDefault();
  e.stopPropagation?.();
  focusField(next);
}

/** Resolve the navigation scope for a focused field. */
export function findNavRoot(el) {
  if (!el) return null;
  return (
    el.closest(`[${NAV_ROOT_ATTR}]`)
    || el.closest('form')
    || el.closest('[role="dialog"]')
  );
}

export function getNavMode(root) {
  if (!root) return 'linear';
  return root.getAttribute('data-form-nav-mode') || 'linear';
}

/** @param {KeyboardEvent} e */
export function handleGlobalFormNavKeyDown(e) {
  if (e.defaultPrevented) return;
  if (!['Enter', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) return;
  const target = e.target;
  if (!(target instanceof HTMLElement)) return;
  const root = findNavRoot(target);
  if (!root) return;
  handleFormNavKeyDown(e, root, { mode: getNavMode(root) });
}

export function navCellProps(row, col) {
  return { [NAV_ROW_ATTR]: String(row), [NAV_COL_ATTR]: String(col) };
}
