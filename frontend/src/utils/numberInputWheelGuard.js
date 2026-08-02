/**
 * Prevent mouse-wheel / trackpad from changing values on focused number inputs.
 * Uses a non-passive capture listener so preventDefault actually works
 * (React's synthetic onWheel is passive at the root and cannot block the default).
 */
export function installNumberInputWheelGuard() {
  const onWheel = (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) return;
    if (target.type !== 'number') return;
    if (document.activeElement !== target) return;
    event.preventDefault();
  };

  document.addEventListener('wheel', onWheel, { passive: false, capture: true });
  return () => document.removeEventListener('wheel', onWheel, { capture: true });
}
