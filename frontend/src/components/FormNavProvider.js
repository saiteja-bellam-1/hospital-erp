import React, { useEffect } from 'react';
import { handleGlobalFormNavKeyDown } from '../utils/formNavigation';

/** Document-level Enter / arrow navigation for fields inside forms and dialogs. */
export function FormNavProvider({ children }) {
  useEffect(() => {
    document.addEventListener('keydown', handleGlobalFormNavKeyDown);
    return () => document.removeEventListener('keydown', handleGlobalFormNavKeyDown);
  }, []);
  return children;
}
