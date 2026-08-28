import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';

/** Effective physiotherapy permissions from GET /api/admin/me/permissions. */
export function usePhysioPermissions() {
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
    const list = mods.physiotherapy || [];
    return list.includes('*') || list.includes(key);
  }, [state]);

  const hasAnyPerm = useCallback((...keys) => keys.some((k) => hasPerm(k)), [hasPerm]);

  return {
    loaded: state.loaded,
    isAdmin: state.isAdmin,
    hasPerm,
    hasAnyPerm,
    canCatalog: hasPerm('manage_catalog'),
    canSchedule: hasPerm('schedule_sessions'),
    canAttend: hasPerm('record_attendance'),
    canPackages: hasPerm('manage_packages'),
    canManageTemplates: state.isAdmin || !!(state.modules['*']?.includes('*')),
    canReports: hasPerm('view_physio_reports'),
    canSchedules: hasPerm('manage_therapist_schedules'),
    canViewDocs: hasPerm('view_physio_documents'),
    canUploadDocs: hasPerm('upload_physio_documents'),
    canDeleteDocs: hasPerm('delete_physio_documents'),
  };
}

export const PHYSIO_ROLE_NAMES = [
  'hospital_admin',
  'super_admin',
  'receptionist',
  'frontdesk',
  'physiotherapist',
  'billing_admin',
];
