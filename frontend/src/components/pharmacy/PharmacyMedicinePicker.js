import React, { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Plus } from 'lucide-react';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import { NAV_SKIP_ATTR } from '../../utils/formNavigation';

/**
 * Search-and-pick a medicine from the pharmacy catalog.
 * Optional `onCreateNew` opens inline catalog create (e.g. QuickMedicineDialog).
 */
export default function PharmacyMedicinePicker({
  value,
  medicine,
  onSelect,
  onCreateNew,
  placeholder = 'Search name / code…',
  className = '',
  navProps = {},
}) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [searching, setSearching] = useState(false);
  const [editing, setEditing] = useState(!value);
  const timerRef = useRef(null);

  useEffect(() => {
    if (value) setEditing(false);
  }, [value]);

  useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current);
  }, []);

  const search = useCallback(async (q) => {
    const term = (q || '').trim();
    if (term.length < 2) {
      setResults([]);
      setOpen(false);
      return;
    }
    setSearching(true);
    try {
      const res = await axios.get('/api/pharmacy/medicines/lookup', { params: { q: term, limit: 20 } });
      setResults(res.data || []);
      setOpen(true);
    } catch {
      setResults([]);
      setOpen(false);
    } finally {
      setSearching(false);
    }
  }, []);

  const handleQueryChange = (v) => {
    setQuery(v);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => search(v), 250);
  };

  const pick = (m) => {
    onSelect?.(m);
    setQuery('');
    setResults([]);
    setOpen(false);
    setEditing(false);
  };

  const startEdit = () => {
    setEditing(true);
    setQuery(medicine?.name || '');
    if ((medicine?.name || '').length >= 2) search(medicine.name);
  };

  const triggerCreate = () => {
    onCreateNew?.(query.trim());
    setOpen(false);
  };

  const createButton = onCreateNew ? (
    <Button
      type="button"
      size="icon"
      variant="outline"
      className="h-8 w-8 shrink-0"
      title="Create new medicine"
      onClick={() => onCreateNew(query.trim())}
    >
      <Plus className="h-3 w-3" />
    </Button>
  ) : null;

  if (value && medicine && !editing) {
    return (
      <div className={`flex gap-1 items-center min-w-0 ${className}`}>
        <button
          type="button"
          className="flex-1 min-w-0 text-left rounded border bg-white px-2 py-1.5 hover:bg-gray-50 min-h-8"
          onClick={startEdit}
          title="Click to change medicine"
          {...navProps}
        >
          <div className="font-medium text-sm truncate">{medicine.name}</div>
          <div className="text-[10px] text-gray-500 truncate">
            {medicine.medicine_code}
            {medicine.strength ? ` · ${medicine.strength}` : ''}
          </div>
        </button>
        {createButton}
      </div>
    );
  }

  return (
    <div className={`relative min-w-0 ${className}`}>
      <div className="flex gap-1">
        <Input
          className="h-8 flex-1 min-w-0"
          placeholder={searching ? 'Searching…' : placeholder}
          value={query}
          onChange={(e) => handleQueryChange(e.target.value)}
          onFocus={() => { if (results.length > 0 || (query.trim().length >= 2 && onCreateNew)) setOpen(true); }}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          {...{ [NAV_SKIP_ATTR]: '' }}
          {...navProps}
        />
        {createButton}
        {value && (
          <Button type="button" size="sm" variant="ghost" className="h-8 px-2 shrink-0" onClick={() => setEditing(false)}>
            Cancel
          </Button>
        )}
      </div>
      {open && results.length > 0 && (
        <div className="absolute z-30 left-0 right-0 mt-1 border bg-white rounded shadow-lg max-h-48 overflow-y-auto">
          {results.map((m) => (
            <button
              key={m.id}
              type="button"
              className="w-full text-left px-2 py-1.5 hover:bg-blue-50 text-xs border-b last:border-0"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => pick(m)}
            >
              <span className="font-medium">{m.name}</span>
              <span className="text-gray-500"> · {m.medicine_code}</span>
              {m.strength && <span className="text-gray-500"> · {m.strength}</span>}
            </button>
          ))}
        </div>
      )}
      {open && query.trim().length >= 2 && !searching && results.length === 0 && (
        <div className="absolute z-30 left-0 right-0 mt-1 border bg-white rounded shadow-lg p-2 text-xs">
          <p className="text-gray-500 mb-1.5">No catalog match for &ldquo;{query.trim()}&rdquo;</p>
          {onCreateNew ? (
            <Button type="button" size="sm" variant="outline" className="w-full h-7 text-xs" onMouseDown={(e) => e.preventDefault()} onClick={triggerCreate}>
              <Plus className="h-3 w-3 mr-1" /> Create new medicine
            </Button>
          ) : (
            <p className="text-gray-500">Add the medicine under <span className="font-medium">Medicines</span> first.</p>
          )}
        </div>
      )}
    </div>
  );
}
