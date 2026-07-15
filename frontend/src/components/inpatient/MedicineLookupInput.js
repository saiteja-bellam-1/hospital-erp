import { useCallback, useEffect, useRef, useState } from 'react';
import { NAV_SKIP_ATTR } from '../../utils/formNavigation';
import axios from 'axios';
import { Input } from '../ui/input';

/**
 * Medicine search for prescribing. Uses the supplied cross-module catalog
 * endpoint and always permits free text when no result is selected.
 */
export default function MedicineLookupInput({
  admissionId,
  lookupUrl,
  value = '',
  medicineId = '',
  onChange,
  placeholder = 'Medicine name (search catalog or type free-text)',
  className = '',
}) {
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const timerRef = useRef(null);
  const endpoint = lookupUrl || (
    admissionId ? `/api/inpatient/admissions/${admissionId}/medicines-lookup` : null
  );

  const search = useCallback(async (query) => {
    if (!endpoint || !query || query.trim().length < 2) {
      setResults([]);
      return;
    }
    try {
      const res = await axios.get(
        endpoint,
        { params: { q: query.trim(), limit: 15 } },
      );
      setResults(res.data || []);
      setOpen(true);
    } catch {
      setResults([]);
    }
  }, [endpoint]);

  useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current); }, []);

  const handleInput = (v) => {
    onChange({ medicine_id: '', medicine_name: v });
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => search(v), 250);
  };

  const pick = (m) => {
    const label = [
      m.name,
      m.strength,
      m.dosage_form ? `(${m.dosage_form})` : '',
    ].filter(Boolean).join(' ');
    onChange({ medicine_id: m.id, medicine_name: label.trim() });
    setResults([]);
    setOpen(false);
  };

  return (
    <div className={`relative ${open ? 'z-50' : 'z-0'} ${className}`}>
      <Input
        placeholder={placeholder}
        value={value}
        onChange={(e) => handleInput(e.target.value)}
        onFocus={() => { if (results.length > 0 && !medicineId) setOpen(true); }}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        {...{ [NAV_SKIP_ATTR]: '' }}
      />
      {open && results.length > 0 && !medicineId && (
        <div className="absolute z-[100] w-full bg-white border rounded-md shadow-xl mt-1 max-h-48 overflow-y-auto">
          {results.map(m => (
            <div
              key={m.id}
              className="px-3 py-1.5 hover:bg-blue-50 cursor-pointer text-xs"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => pick(m)}
            >
              <span className="font-medium">{m.name}</span>
              {m.strength && <span className="text-gray-500"> · {m.strength}</span>}
              {m.dosage_form && <span className="text-gray-500"> · {m.dosage_form}</span>}
              <span className="text-gray-400 ml-1">₹{Number(m.unit_price || 0).toFixed(2)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
