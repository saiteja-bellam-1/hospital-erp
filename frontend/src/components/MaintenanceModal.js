import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Loader2 } from 'lucide-react';

/**
 * Renders a fullscreen modal whenever the backend returns a
 * `503 {maintenance: true}` response. Polls `/api/backup/maintenance` while
 * visible and auto-dismisses when the backend reports `active: false`.
 *
 * Mounted once at app root so any 503 from anywhere in the app surfaces
 * the same modal.
 */
const MaintenanceModal = () => {
  const [active, setActive] = useState(false);
  const [detail, setDetail] = useState(null);

  useEffect(() => {
    const onMaintenance = (e) => {
      setActive(true);
      setDetail(e.detail);
    };
    window.addEventListener('app:maintenance', onMaintenance);
    return () => window.removeEventListener('app:maintenance', onMaintenance);
  }, []);

  useEffect(() => {
    if (!active) return undefined;
    let alive = true;
    const tick = async () => {
      try {
        const res = await axios.get('/api/backup/maintenance');
        if (!alive) return;
        if (!res.data?.active) {
          setActive(false);
        }
      } catch {
        // Probably still 503 or 401 — keep polling until either succeeds.
      }
    };
    const id = setInterval(tick, 3000);
    tick();
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [active]);

  if (!active) return null;

  return (
    <div className="fixed inset-0 z-[10000] bg-black/60 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-2xl max-w-md w-full p-6 space-y-4">
        <div className="flex items-center gap-3">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
          <div className="font-semibold text-lg">System under maintenance</div>
        </div>
        <p className="text-sm text-gray-700">
          {detail?.detail || 'A restore or maintenance task is in progress. Your data is safe — please wait.'}
        </p>
        <p className="text-xs text-gray-500">
          This screen will close automatically when the operation finishes.
        </p>
      </div>
    </div>
  );
};

export default MaintenanceModal;
