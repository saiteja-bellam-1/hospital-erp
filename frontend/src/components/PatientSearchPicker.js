import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Search, UserPlus, XCircle, Loader2 } from 'lucide-react';
import { Label } from './ui/label';
import { Input } from './ui/input';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import QuickPatientRegisterDialog from './QuickPatientRegisterDialog';
import { guessPatientFieldsFromQuery } from '../utils/patientSearchHints';

/**
 * Searchable patient picker with inline quick-registration when no match is found.
 *
 * @param {object|null} value - Selected patient object
 * @param {(patient: object|null) => void} onChange
 */
export default function PatientSearchPicker({
  value,
  onChange,
  label = 'Search Patient',
  placeholder = 'Search by name, phone, or patient ID…',
  required = false,
  id = 'patient_search',
  className = '',
  compact = false,
}) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [showResults, setShowResults] = useState(false);
  const [registerOpen, setRegisterOpen] = useState(false);
  const [registerPrefill, setRegisterPrefill] = useState({});

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      setSearching(false);
      return undefined;
    }

    setSearching(true);
    setShowResults(true);
    const timer = setTimeout(async () => {
      try {
        const res = await axios.post('/api/patients/search', {
          search_term: query.trim(),
          sort_by: 'name',
          sort_order: 'asc',
        });
        setResults((res.data?.patients || []).slice(0, 10));
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [query]);

  const openRegister = () => {
    setRegisterPrefill(guessPatientFieldsFromQuery(query));
    setRegisterOpen(true);
  };

  const selectPatient = (patient) => {
    onChange?.(patient);
    setQuery('');
    setResults([]);
    setShowResults(false);
  };

  const clearSelection = () => {
    onChange?.(null);
    setQuery('');
    setResults([]);
    setShowResults(true);
  };

  const handleCreated = (patient) => {
    selectPatient(patient);
  };

  const ageLabel = (p) => {
    if (p.age != null) return `${p.age}y`;
    if (p.date_of_birth) {
      const y = new Date().getFullYear() - new Date(p.date_of_birth).getFullYear();
      return `${y}y`;
    }
    return null;
  };

  return (
    <div className={className}>
      <Label htmlFor={id}>
        {label}{required ? ' *' : ''}
      </Label>

      {value ? (
        <div className={`mt-1 p-3 bg-green-50 border border-green-200 rounded-lg flex justify-between items-center ${compact ? 'py-2' : ''}`}>
          <div>
            <p className={`font-medium text-green-900 ${compact ? 'text-sm' : ''}`}>
              {value.first_name} {value.last_name}
            </p>
            <p className="text-sm text-green-600">
              {value.primary_phone}
              {value.patient_id ? ` • ID: ${String(value.patient_id).slice(0, 8)}…` : ''}
            </p>
          </div>
          <Button type="button" variant="ghost" size="sm" onClick={clearSelection} aria-label="Change patient">
            <XCircle className="h-4 w-4" />
          </Button>
        </div>
      ) : (
        <>
          <div className="relative mt-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <Input
              id={id}
              className="pl-9"
              placeholder={placeholder}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onFocus={() => query.trim() && setShowResults(true)}
            />
            {searching && (
              <div className="absolute right-3 top-1/2 -translate-y-1/2">
                <Loader2 className="h-4 w-4 animate-spin text-gray-400" />
              </div>
            )}
          </div>

          {!query.trim() && (
            <p className="text-gray-400 text-xs mt-1.5">Start typing to search, or add a new patient.</p>
          )}

          {showResults && query.trim() && (
            <div className="mt-1 border rounded-lg max-h-48 overflow-y-auto">
              {searching ? (
                <div className="flex items-center justify-center py-4 gap-2 text-gray-400">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span className="text-sm">Searching…</span>
                </div>
              ) : results.length === 0 ? (
                <div className="py-4 px-3 text-center space-y-2">
                  <p className="text-gray-500 text-sm">No patients found for &ldquo;{query.trim()}&rdquo;</p>
                  <Button type="button" size="sm" variant="outline" onClick={openRegister}>
                    <UserPlus className="h-4 w-4 mr-1.5" />
                    Add new patient
                  </Button>
                </div>
              ) : (
                <>
                  {results.map((patient) => {
                    const age = ageLabel(patient);
                    return (
                      <button
                        key={patient.patient_id || patient.id}
                        type="button"
                        className="w-full text-left px-4 py-2.5 hover:bg-blue-50 border-b last:border-b-0"
                        onClick={() => selectPatient(patient)}
                      >
                        <div className="flex justify-between items-center gap-2">
                          <div>
                            <p className="font-medium text-gray-900 text-sm">
                              {patient.first_name} {patient.last_name}
                            </p>
                            <p className="text-xs text-gray-500">
                              {patient.primary_phone}
                              {patient.patient_id ? ` • ID: ${String(patient.patient_id).slice(0, 8)}…` : ''}
                            </p>
                          </div>
                          {(patient.gender || age) && (
                            <Badge variant="outline" className="text-xs shrink-0">
                              {[patient.gender || 'N/A', age].filter(Boolean).join(' • ')}
                            </Badge>
                          )}
                        </div>
                      </button>
                    );
                  })}
                  <div className="px-3 py-2 border-t bg-gray-50">
                    <Button type="button" size="sm" variant="ghost" className="w-full text-blue-700" onClick={openRegister}>
                      <UserPlus className="h-4 w-4 mr-1.5" />
                      Add new patient
                    </Button>
                  </div>
                </>
              )}
            </div>
          )}
        </>
      )}

      <QuickPatientRegisterDialog
        open={registerOpen}
        onOpenChange={setRegisterOpen}
        initialValues={registerPrefill}
        onCreated={handleCreated}
      />
    </div>
  );
}
