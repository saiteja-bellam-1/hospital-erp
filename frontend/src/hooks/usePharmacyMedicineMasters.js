import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';

const EMPTY_MASTERS = {
  categories: [],
  companies: [],
  racks: [],
  salts: [],
  uoms: [],
  hsnList: [],
};

export function usePharmacyMedicineMasters(enabled = true) {
  const [masters, setMasters] = useState(EMPTY_MASTERS);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [c, co, r, sa, u, h] = await Promise.all([
        axios.get('/api/pharmacy/categories'),
        axios.get('/api/pharmacy/companies'),
        axios.get('/api/pharmacy/racks'),
        axios.get('/api/pharmacy/salts'),
        axios.get('/api/pharmacy/uoms'),
        axios.get('/api/pharmacy/hsn'),
      ]);
      setMasters({
        categories: c.data || [],
        companies: co.data || [],
        racks: r.data || [],
        salts: sa.data || [],
        uoms: u.data || [],
        hsnList: h.data || [],
      });
    } catch {
      setMasters(EMPTY_MASTERS);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled) return undefined;
    load();
    return undefined;
  }, [enabled, load]);

  return { masters, setMasters, loading, reload: load };
}
