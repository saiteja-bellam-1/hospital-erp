import React from 'react';
import { AlertTriangle, XCircle, Info } from 'lucide-react';
import { phoneTel } from '../utils/supportContact';

const LicenseBanner = ({ licenseStatus }) => {
  if (!licenseStatus || licenseStatus.status === 'active' || licenseStatus.status === 'no_license') {
    return null;
  }

  const configs = {
    trial: {
      bg: 'bg-blue-50 border-blue-300',
      text: 'text-blue-900',
      icon: <Info className="h-4 w-4 text-blue-600" />,
    },
    trial_expired: {
      bg: 'bg-amber-50 border-amber-300',
      text: 'text-amber-950',
      icon: <AlertTriangle className="h-4 w-4 text-amber-600" />,
    },
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

  const showSupport = licenseStatus.status === 'trial_expired';
  const contact = licenseStatus.support_contact;

  return (
    <div className={`${config.bg} border-b px-4 py-2 flex flex-wrap items-center gap-x-3 gap-y-1`}>
      {config.icon}
      <span className={`text-sm font-medium ${config.text}`}>
        {licenseStatus.message}
      </span>
      {showSupport && contact?.name && (
        <span className="text-sm text-amber-900">
          {contact.name}
          {contact.phone && (
            <>
              {' '}
              <a href={phoneTel(contact.phone)} className="font-medium underline underline-offset-2">
                {contact.phone}
              </a>
            </>
          )}
          {contact.email && (
            <>
              {' · '}
              <a href={`mailto:${contact.email}`} className="font-medium underline underline-offset-2">
                {contact.email}
              </a>
            </>
          )}
        </span>
      )}
    </div>
  );
};

export default LicenseBanner;
