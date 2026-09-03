import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useAuth } from './AuthContext';

export const DEFAULT_APP_NAME = 'KT HEALTH ERP';

const BrandingContext = createContext({
  hospitalName: DEFAULT_APP_NAME,
  logoUrl: null,
  faviconUrl: null,
  version: 0,
  loading: true,
  refreshBranding: async () => {},
});

function applyBrandingToDocument(name, faviconUrl, cacheBust = '') {
  document.title = name || DEFAULT_APP_NAME;

  const href = faviconUrl
    ? `${faviconUrl}${cacheBust ? `?v=${cacheBust}` : ''}`
    : '/favicon.ico';

  let link = document.querySelector("link[rel~='icon']");
  if (!link) {
    link = document.createElement('link');
    link.rel = 'icon';
    document.head.appendChild(link);
  }
  link.href = href;
}

export function BrandingProvider({ children }) {
  const { user } = useAuth();
  const [hospitalName, setHospitalName] = useState(DEFAULT_APP_NAME);
  const [logoUrl, setLogoUrl] = useState(null);
  const [faviconUrl, setFaviconUrl] = useState(null);
  const [version, setVersion] = useState(0);
  const [loading, setLoading] = useState(true);

  const refreshBranding = useCallback(async () => {
    try {
      const endpoint = user ? '/api/hospital/branding' : '/api/hospital/branding/public';
      const res = await axios.get(endpoint);
      const name = res.data?.name || DEFAULT_APP_NAME;
      const nextLogo = res.data?.logo_url || null;
      const nextFavicon = res.data?.favicon_url || null;
      const nextVersion = nextFavicon ? Date.now() : 0;

      setHospitalName(name);
      setLogoUrl(nextLogo);
      setFaviconUrl(nextFavicon);
      setVersion(nextVersion);
      applyBrandingToDocument(name, nextFavicon, nextVersion);
    } catch {
      setHospitalName(DEFAULT_APP_NAME);
      setLogoUrl(null);
      setFaviconUrl(null);
      setVersion(0);
      applyBrandingToDocument(DEFAULT_APP_NAME, null, 0);
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    refreshBranding();
  }, [refreshBranding]);

  const value = useMemo(
    () => ({
      hospitalName,
      logoUrl,
      faviconUrl,
      version,
      loading,
      refreshBranding,
    }),
    [hospitalName, logoUrl, faviconUrl, version, loading, refreshBranding],
  );

  return (
    <BrandingContext.Provider value={value}>
      {children}
    </BrandingContext.Provider>
  );
}

export function useBranding() {
  return useContext(BrandingContext);
}

export { applyBrandingToDocument };
