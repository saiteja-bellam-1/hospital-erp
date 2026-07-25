import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { ChevronRight, ClipboardCheck, X } from 'lucide-react';

export default function SetupProgressBanner() {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    axios.get('/api/onboarding/status')
      .then((response) => setStatus(response.data))
      .catch(() => {});
  }, []);

  if (!status || status.completed || status.dismissed) return null;

  const dismiss = async () => {
    setStatus((current) => ({ ...current, dismissed: true }));
    try {
      await axios.post('/api/onboarding/dismiss');
    } catch {
      setStatus((current) => ({ ...current, dismissed: false }));
    }
  };

  return (
    <div className="flex items-center gap-3 border-b border-blue-200 bg-blue-50 px-4 py-2.5 text-sm text-blue-900">
      <ClipboardCheck className="h-5 w-5 shrink-0 text-blue-600" />
      <div className="min-w-0 flex-1">
        <span className="font-semibold">Hospital setup: </span>
        <span>{status.required_completed_count} of {status.required_total_count} required steps complete</span>
      </div>
      <Link to="/dashboard/setup" className="flex shrink-0 items-center font-medium text-blue-700 hover:underline">
        Continue setup <ChevronRight className="ml-1 h-4 w-4" />
      </Link>
      <button type="button" onClick={dismiss} aria-label="Dismiss setup reminder" className="rounded p-1 hover:bg-blue-100">
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
