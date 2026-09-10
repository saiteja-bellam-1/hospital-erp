import React, { useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../ui/dialog';
import { Button } from '../ui/button';
import { Loader2 } from 'lucide-react';

/**
 * Lazy-loading drill-down dialog for dashboard KPI cards.
 *
 * @param {object} props
 * @param {boolean} props.open
 * @param {(open: boolean) => void} props.onOpenChange
 * @param {string} props.title
 * @param {string} [props.description]
 * @param {() => Promise<any[]>} props.loadRows — called when opened
 * @param {(rows: any[]) => React.ReactNode} props.renderRows
 * @param {string} [props.emptyText]
 * @param {{ label: string, onClick: () => void }} [props.viewAll]
 * @param {React.ReactNode} [props.filterBar] — optional chips/filters above the list
 * @param {any} [props.reloadKey] — change to re-fetch while open
 */
export default function DashboardDrillDialog({
  open,
  onOpenChange,
  title,
  description,
  loadRows,
  renderRows,
  emptyText = 'No items',
  viewAll,
  filterBar,
  reloadKey,
}) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    setLoading(true);
    setError(null);
    loadRows()
      .then((data) => {
        if (!cancelled) setRows(Array.isArray(data) ? data : []);
      })
      .catch((e) => {
        if (!cancelled) {
          setRows([]);
          setError(e?.response?.data?.detail || e?.message || 'Failed to load');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [open, loadRows, reloadKey]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl w-[96vw] max-h-[90vh] flex flex-col overflow-hidden gap-0 p-0">
        <DialogHeader className="px-6 pt-6 pb-3 shrink-0 border-b">
          <DialogTitle>{title}</DialogTitle>
          {description && (
            <p className="text-sm text-gray-500 mt-1">{description}</p>
          )}
        </DialogHeader>

        {filterBar && (
          <div className="px-6 py-3 border-b shrink-0 bg-gray-50/80">
            {filterBar}
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-6 py-4 min-h-[12rem]">
          {loading ? (
            <div className="flex items-center justify-center gap-2 py-12 text-sm text-gray-500">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </div>
          ) : error ? (
            <p className="text-center py-12 text-sm text-red-600">
              {typeof error === 'string' ? error : 'Failed to load'}
            </p>
          ) : rows.length === 0 ? (
            <p className="text-center py-12 text-sm text-gray-500">{emptyText}</p>
          ) : (
            renderRows(rows)
          )}
        </div>

        <DialogFooter className="px-6 py-3 border-t shrink-0 sm:justify-between gap-2">
          <p className="text-xs text-gray-500 self-center">
            {!loading && !error ? `${rows.length} item${rows.length === 1 ? '' : 's'}` : ''}
          </p>
          <div className="flex gap-2">
            {viewAll && (
              <Button
                variant="outline"
                onClick={() => {
                  onOpenChange(false);
                  viewAll.onClick();
                }}
              >
                {viewAll.label}
              </Button>
            )}
            <Button variant="secondary" onClick={() => onOpenChange(false)}>Close</Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
