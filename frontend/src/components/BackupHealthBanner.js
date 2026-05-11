import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { AlertTriangle, XCircle } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

/**
 * Backup-health banner — surfaces "no successful backup recently" / "a
 * location is broken" so it can't go unnoticed.
 *
 * Polls `/api/backup/health` every 90s. Only renders for admin roles
 * (super_admin / hospital_admin). Hidden when status is "healthy" or
 * "disabled" so it doesn't fight for screen real estate when there's
 * nothing to act on.
 */
const POLL_MS = 90 * 1000;

const BackupHealthBanner = () => {
  const { user } = useAuth();
  const [health, setHealth] = useState(null);

  const isAdmin = (user?.roles || []).some((r) => ['super_admin', 'hospital_admin'].includes(r));

  useEffect(() => {
    if (!isAdmin) return undefined;
    let alive = true;
    const fetchHealth = async () => {
      try {
        const res = await axios.get('/api/backup/health');
        if (alive) setHealth(res.data);
      } catch {
        // 401 etc. — ignore, the global interceptor handles it
      }
    };
    fetchHealth();
    const id = setInterval(fetchHealth, POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [isAdmin]);

  if (!isAdmin || !health) return null;
  if (health.status === 'healthy' || health.status === 'disabled') return null;

  const isBroken = health.status === 'broken';
  const Icon = isBroken ? XCircle : AlertTriangle;
  const palette = isBroken
    ? 'bg-red-100 border-red-500 text-red-900'
    : 'bg-amber-50 border-amber-300 text-amber-900';
  const iconColor = isBroken ? 'text-red-700' : 'text-amber-700';

  return (
    <div className={`${palette} border-b px-4 py-2 flex items-center gap-2`}>
      <Icon className={`h-4 w-4 ${iconColor}`} />
      <span className="text-sm font-medium flex-1">
        {health.message}
      </span>
      {health.broken && health.broken.length > 0 && (
        <span className="text-xs">
          ({health.broken.map((b) => b.location).join(', ')})
        </span>
      )}
    </div>
  );
};

export default BackupHealthBanner;
