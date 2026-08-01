import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import axios from 'axios';

const LayoutPreferencesContext = createContext({
  navLayout: 'sidebar',
  setNavLayout: () => {},
  loading: true,
  refreshUiSettings: async () => {},
});

export function LayoutPreferencesProvider({ children, enabled = true }) {
  const [navLayout, setNavLayoutState] = useState('sidebar');
  const [loading, setLoading] = useState(true);

  const refreshUiSettings = useCallback(async () => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    try {
      const res = await axios.get('/api/hospital/ui-settings');
      const layout = res.data?.nav_layout === 'header' ? 'header' : 'sidebar';
      setNavLayoutState(layout);
    } catch {
      setNavLayoutState('sidebar');
    } finally {
      setLoading(false);
    }
  }, [enabled]);

  useEffect(() => {
    refreshUiSettings();
  }, [refreshUiSettings]);

  const setNavLayout = useCallback((layout) => {
    setNavLayoutState(layout === 'header' ? 'header' : 'sidebar');
  }, []);

  const value = useMemo(
    () => ({ navLayout, setNavLayout, loading, refreshUiSettings }),
    [navLayout, setNavLayout, loading, refreshUiSettings],
  );

  return (
    <LayoutPreferencesContext.Provider value={value}>
      {children}
    </LayoutPreferencesContext.Provider>
  );
}

export function useLayoutPreferences() {
  return useContext(LayoutPreferencesContext);
}
