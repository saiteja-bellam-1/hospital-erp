import React from 'react';
import { AlertTriangle, XCircle, Info } from 'lucide-react';

const LicenseBanner = ({ licenseStatus }) => {
  if (!licenseStatus || licenseStatus.status === 'active' || licenseStatus.status === 'no_license') {
    return null;
  }

  const configs = {
    expiring_soon: {
      bg: 'bg-yellow-50 border-yellow-300',
      text: 'text-yellow-800',
      icon: <AlertTriangle className="h-4 w-4 text-yellow-600" />,
    },
    grace_period: {
      bg: 'bg-red-50 border-red-300',
      text: 'text-red-800',
      icon: <XCircle className="h-4 w-4 text-red-600" />,
    },
    expired: {
      bg: 'bg-red-100 border-red-500',
      text: 'text-red-900',
      icon: <XCircle className="h-4 w-4 text-red-700" />,
    },
    machine_mismatch: {
      bg: 'bg-red-100 border-red-500',
      text: 'text-red-900',
      icon: <XCircle className="h-4 w-4 text-red-700" />,
    },
  };

  const config = configs[licenseStatus.status];
  if (!config) return null;

  return (
    <div className={`${config.bg} border-b px-4 py-2 flex items-center gap-2`}>
      {config.icon}
      <span className={`text-sm font-medium ${config.text}`}>
        {licenseStatus.message}
      </span>
    </div>
  );
};

export default LicenseBanner;
