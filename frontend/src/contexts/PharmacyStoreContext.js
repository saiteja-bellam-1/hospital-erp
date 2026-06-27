import React, {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
} from 'react';
import axios from 'axios';
import { useAuth } from './AuthContext';

const STORAGE_PREFIX = 'pharmacy_active_store_id';

function storageKey(username) {
  return username ? `${STORAGE_PREFIX}_${username}` : STORAGE_PREFIX;
}

const PharmacyStoreContext = createContext(null);

export function PharmacyStoreProvider({ children }) {
  const { user } = useAuth();
  const username = user?.username || '';

  const [stores, setStores] = useState([]);
  const [multiStoreEnabled, setMultiStoreEnabled] = useState(false);
  const [requireStoreAssignment, setRequireStoreAssignment] = useState(false);
  const [storeLocked, setStoreLocked] = useState(false);
  const [activeStoreId, setActiveStoreIdState] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get('/api/pharmacy/stores/settings');
      const list = r.data?.stores || [];
      setStores(list);
      setMultiStoreEnabled(Boolean(r.data?.multi_store_enabled));
      setRequireStoreAssignment(Boolean(r.data?.require_store_assignment));
      setStoreLocked(Boolean(r.data?.store_locked));

      const key = storageKey(username);
      const savedRaw = localStorage.getItem(key);
      const savedId = savedRaw ? parseInt(savedRaw, 10) : null;

      setActiveStoreIdState(() => {
        if (savedId && list.some((s) => s.id === savedId && s.is_active)) return savedId;
        const def = list.find((s) => s.is_default) || list[0];
        if (def) {
          localStorage.setItem(key, String(def.id));
          return def.id;
        }
        return null;
      });
    } catch {
      setStores([]);
    } finally {
      setLoading(false);
    }
  }, [username]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const setActiveStoreId = useCallback((id) => {
    if (storeLocked && activeStoreId && id !== activeStoreId) return;
    setActiveStoreIdState(id);
    if (id && username) localStorage.setItem(storageKey(username), String(id));
  }, [storeLocked, activeStoreId, username]);

  const activeStore = useMemo(
    () => stores.find((s) => s.id === activeStoreId) || stores[0] || null,
    [stores, activeStoreId],
  );

  const storeParams = useMemo(() => {
    if (!activeStore?.id) return {};
    return { store_id: activeStore.id };
  }, [activeStore]);

  const value = useMemo(() => ({
    stores,
    activeStore,
    activeStoreId: activeStore?.id ?? null,
    setActiveStoreId,
    multiStoreEnabled,
    requireStoreAssignment,
    storeLocked,
    storeParams,
    loading,
    refresh,
  }), [
    stores, activeStore, setActiveStoreId, multiStoreEnabled, requireStoreAssignment,
    storeLocked, storeParams, loading, refresh,
  ]);

  return (
    <PharmacyStoreContext.Provider value={value}>
      {children}
    </PharmacyStoreContext.Provider>
  );
}

export function usePharmacyStore() {
  const ctx = useContext(PharmacyStoreContext);
  if (!ctx) {
    return {
      stores: [],
      activeStore: null,
      activeStoreId: null,
      setActiveStoreId: () => {},
      multiStoreEnabled: false,
      requireStoreAssignment: false,
      storeLocked: false,
      storeParams: {},
      loading: false,
      refresh: () => {},
    };
  }
  return ctx;
}
