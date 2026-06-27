import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';

/**
 * Effective pharmacy module permissions for the logged-in user.
 * Mirrors inpatient's /api/admin/me/permissions pattern.
 */
export function usePharmacyPermissions() {
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
    const list = mods.pharmacy || [];
    return list.includes('*') || list.includes(key);
  }, [state]);

  const hasAnyPerm = useCallback((...keys) => keys.some((k) => hasPerm(k)), [hasPerm]);

  return { ...state, hasPerm, hasAnyPerm };
}

export const PHARMACY_ROLE_NAMES = [
  'pharmacist',
  'pharmacy_admin',
  'pharmacy_pos_operator',
  'satellite_pharmacy_admin',
  'pharmacy_transfer_clerk',
  'hospital_admin',
  'super_admin',
];
