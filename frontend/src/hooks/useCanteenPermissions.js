import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';

/** Effective canteen permissions (module gated by inpatient enablement on the backend). */
export function useCanteenPermissions() {
  const [state, setState] = useState({ loaded: false, isAdmin: false, modules: {} });

  useEffect(() => {
    let cancelled = false;
    axios.get('/api/admin/me/permissions')
      .then((res) => {
        if (cancelled) return;
        setState({
          loaded: true,
          isAdmin: !!res.data?.is_admin,
          modules: res.data?.modules || {},
        });
      })
      .catch(() => {
        if (!cancelled) setState({ loaded: true, isAdmin: false, modules: {} });
      });
    return () => { cancelled = true; };
  }, []);

  const hasPerm = useCallback((key) => {
    if (state.isAdmin) return true;
    const mods = state.modules || {};
    if (mods['*']?.includes('*')) return true;
    const list = mods.canteen || [];
    return list.includes('*') || list.includes(key);
  }, [state]);

  const hasAnyPerm = useCallback((...keys) => keys.some((k) => hasPerm(k)), [hasPerm]);

  return { ...state, hasPerm, hasAnyPerm };
}

export const CANTEEN_ROLE_NAMES = [
  'canteen_admin',
  'canteen_sales',
  'hospital_admin',
  'super_admin',
];
