import React from 'react';
import { Store } from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Badge } from '../ui/badge';
import { usePharmacyStore } from '../../contexts/PharmacyStoreContext';

export default function PharmacyStoreSelector({ compact = false, posMode = false }) {
  const {
    stores, activeStore, activeStoreId, setActiveStoreId,
    multiStoreEnabled, storeLocked, loading,
  } = usePharmacyStore();

  if (loading || stores.length === 0) return null;

  const showSelector = !storeLocked && (multiStoreEnabled || stores.length > 1);

  if (!showSelector) {
    if (!activeStore) return null;
    return (
      <Badge variant={posMode ? 'default' : 'outline'} className="font-normal">
        <Store className="h-3 w-3 mr-1" />
        {posMode ? 'Billing: ' : ''}{activeStore.code} — {activeStore.name}
      </Badge>
    );
  }

  return (
    <div className={`flex items-center gap-2 ${compact ? '' : 'min-w-[200px]'}`}>
      {!compact && <Store className="h-4 w-4 text-gray-500 shrink-0" />}
      <Select
        value={activeStoreId ? String(activeStoreId) : undefined}
        onValueChange={(v) => setActiveStoreId(parseInt(v, 10))}
      >
        <SelectTrigger className={compact ? 'h-8 w-[200px]' : 'w-[240px]'}>
          <SelectValue placeholder="Select store" />
        </SelectTrigger>
        <SelectContent>
          {stores.filter((s) => s.is_active).map((s) => (
            <SelectItem key={s.id} value={String(s.id)}>
              {s.code} — {s.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
