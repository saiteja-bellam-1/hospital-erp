import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import axios from 'axios';

const NAV_LAYOUT_CACHE_KEY = 'kthealth_nav_layout';

function readCachedNavLayout() {
  try {
    const value = localStorage.getItem(NAV_LAYOUT_CACHE_KEY);
    if (value === 'header' || value === 'sidebar') return value;
  } catch {
    /* storage unavailable */
  }
  return null;
}

function writeCachedNavLayout(layout) {
  try {
    localStorage.setItem(NAV_LAYOUT_CACHE_KEY, layout);
  } catch {
    /* storage unavailable */
  }
}

function normalizeLayout(value) {
  return value === 'header' ? 'header' : 'sidebar';
}

const LayoutPreferencesContext = createContext({
  navLayout: 'sidebar',
  setNavLayout: () => {},
  loading: true,
  // True when a layout can be painted without guessing. The default context
  // is only used outside the provider, where there is nothing to wait for.
  layoutResolved: true,
  refreshUiSettings: async () => {},
});

export function LayoutPreferencesProvider({ children, enabled = true }) {
  // The saved layout lives on the server. Reading it only after mount made
  // every refresh paint the side menu, then jump to the top menu once
  // /api/hospital/ui-settings returned. The cache is the last confirmed value
  // so the first paint matches what the user already has.
  const [navLayout, setNavLayoutState] = useState(() => readCachedNavLayout() || 'sidebar');
  const [layoutResolved, setLayoutResolved] = useState(() => readCachedNavLayout() != null);
  const [loading, setLoading] = useState(true);

  const applyLayout = useCallback((layout) => {
    const next = normalizeLayout(layout);
    setNavLayoutState(next);
    writeCachedNavLayout(next);
    return next;
  }, []);

  const refreshUiSettings = useCallback(async () => {
    if (!enabled) {
      setLoading(false);
      setLayoutResolved(true);
      return;
    }
    try {
      const res = await axios.get('/api/hospital/ui-settings');
      applyLayout(res.data?.nav_layout);
    } catch {
      // Keep a previously confirmed layout. Forcing sidebar here is what
      // put the side menu back whenever the settings request failed.
      if (!readCachedNavLayout()) setNavLayoutState('sidebar');
    } finally {
      setLoading(false);
      setLayoutResolved(true);
    }
  }, [enabled, applyLayout]);

  useEffect(() => {
    refreshUiSettings();
  }, [refreshUiSettings]);

  const setNavLayout = useCallback((layout) => {
    applyLayout(layout);
  }, [applyLayout]);

  const value = useMemo(
    () => ({ navLayout, setNavLayout, loading, layoutResolved, refreshUiSettings }),
    [navLayout, setNavLayout, loading, layoutResolved, refreshUiSettings],
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
