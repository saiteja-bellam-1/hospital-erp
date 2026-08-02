import React, { useEffect, useState, useCallback, useMemo } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Input } from '../../../../components/ui/input';
import { Badge } from '../../../../components/ui/badge';
import { useToast } from '../../../../hooks/use-toast';
import { Plus, Pencil, Trash2, RefreshCw, Search, Upload, Download, Loader2 } from 'lucide-react';
import PharmacyImportDialog, { downloadPharmacyBlob } from '../../../../components/pharmacy/PharmacyImportDialog';
import PharmacyFormDialog from '../../../../components/pharmacy/PharmacyFormDialog';
import { errMsg } from '../../PharmacyModule';
import SupplierFormFields, {
  EMPTY_SUPPLIER_FORM,
  SUPPLIER_FORM_STEPS,
  prepareSupplierPayload,
  supplierStepCanProceed,
} from '../../../../components/pharmacy/SupplierFormFields';

export default function SuppliersTab() {
  const { toast } = useToast();
  const [rows, setRows] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_SUPPLIER_FORM);
  const [activeStep, setActiveStep] = useState(0);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get('/api/pharmacy/suppliers', { params: { active_only: false } });
      setRows(r.data || []);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Load failed', description: errMsg(e) });
    } finally { setLoading(false); }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_SUPPLIER_FORM);
    setActiveStep(0);
    setOpen(true);
  };
  const openEdit = (row) => {
    setEditing(row);
    const f = { ...EMPTY_SUPPLIER_FORM };
    Object.keys(EMPTY_SUPPLIER_FORM).forEach((k) => {
      const v = row[k];
      f[k] = v === null || v === undefined ? EMPTY_SUPPLIER_FORM[k] : v;
    });
    setForm(f);
    setActiveStep(0);
    setOpen(true);
  };

  const steps = useMemo(
    () => SUPPLIER_FORM_STEPS.map((s, i) => ({ ...s, completed: i < activeStep })),
    [activeStep],
  );

  const handleNext = () => {
    if (!supplierStepCanProceed(form, activeStep)) {
      toast({ variant: 'destructive', title: 'Ledger name is required' });
      return;
    }
    setActiveStep((s) => Math.min(s + 1, SUPPLIER_FORM_STEPS.length - 1));
  };

  const save = async () => {
    if (!supplierStepCanProceed(form, 0)) {
      toast({ variant: 'destructive', title: 'Ledger name is required' });
      setActiveStep(0);
      return;
    }
    setSaving(true);
    try {
      const payload = prepareSupplierPayload(form);
      if (editing) {
        await axios.put(`/api/pharmacy/suppliers/${editing.id}`, payload);
        toast({ title: 'Supplier updated' });
      } else {
        await axios.post('/api/pharmacy/suppliers', payload);
        toast({ title: 'Supplier created' });
      }
      setOpen(false); load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Save failed', description: errMsg(e) });
    } finally {
      setSaving(false);
    }
  };

  const remove = async (row) => {
    if (!window.confirm(`Delete supplier "${row.name}"?`)) return;
    try { await axios.delete(`/api/pharmacy/suppliers/${row.id}`); toast({ title: 'Deleted' }); load(); }
    catch (e) { toast({ variant: 'destructive', title: 'Delete failed', description: errMsg(e) }); }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      await downloadPharmacyBlob('/api/pharmacy/suppliers/export/xlsx', 'suppliers_export.xlsx', toast);
      toast({ title: 'Suppliers exported' });
    } catch {
      /* toast already shown */
    } finally {
      setExporting(false);
    }
  };


  const filtered = rows.filter(r => {
    if (!search) return true;
    const hay = `${r.name} ${r.mobile || ''} ${r.gstin_no || r.gstin || ''} ${r.dl_number || ''}`.toLowerCase();
    return hay.includes(search.toLowerCase());
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between flex-wrap gap-2">
          <span>Suppliers ({filtered.length})</span>
          <div className="flex gap-2 items-center">
            <div className="relative">
              <Search className="absolute left-2 top-2.5 h-4 w-4 text-gray-400" />
              <Input className="pl-8 h-8 w-56" placeholder="Search name / mobile / GSTIN / DL…"
                value={search} onChange={e => setSearch(e.target.value)} />
            </div>
            <Button size="sm" variant="outline" onClick={load}><RefreshCw className="h-3 w-3" /></Button>
            <Button size="sm" variant="outline" onClick={() => setImportOpen(true)}>
              <Upload className="h-3 w-3 mr-1" /> Import
            </Button>
            <Button size="sm" variant="outline" onClick={handleExport} disabled={exporting}>
              {exporting ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Download className="h-3 w-3 mr-1" />}
              Export
            </Button>
            <Button size="sm" onClick={openCreate}><Plus className="h-3 w-3 mr-1" /> New Supplier</Button>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? <p className="text-center py-6 text-gray-500 text-sm">Loading…</p>
          : filtered.length === 0 ? <p className="text-center py-6 text-gray-500 text-sm">No suppliers</p>
          : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b text-left text-gray-600">
                  <th className="py-2 pr-4">Name</th>
                  <th className="py-2 pr-4">Mobile</th>
                  <th className="py-2 pr-4">GSTIN</th>
                  <th className="py-2 pr-4">DL No.</th>
                  <th className="py-2 pr-4">DL Exp.</th>
                  <th className="py-2 pr-4">State</th>
                  <th className="py-2 pr-4">Type</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 text-right">Actions</th>
                </tr></thead>
                <tbody>
                  {filtered.map(s => (
                    <tr key={s.id} className="border-b hover:bg-gray-50">
                      <td className="py-2 pr-4">
                        <div className="font-medium">{s.name}</div>
                        {s.contact_person && <div className="text-xs text-gray-500">{s.contact_person}</div>}
                      </td>
                      <td className="py-2 pr-4 text-xs">{s.mobile || s.phone || '—'}</td>
                      <td className="py-2 pr-4 font-mono text-xs">{s.gstin_no || s.gstin || '—'}</td>
                      <td className="py-2 pr-4 text-xs">{s.dl_number || '—'}</td>
                      <td className="py-2 pr-4 text-xs">{s.dl_expiry || '—'}</td>
                      <td className="py-2 pr-4 text-xs">{s.state_code ? `${s.state_code}-${s.state || ''}` : (s.state || '—')}</td>
                      <td className="py-2 pr-4">
                        <Badge variant="outline" className="text-[10px]">{s.ledger_type || 'unregistered'}</Badge>
                      </td>
                      <td className="py-2 pr-4">
                        {!s.is_active && <Badge variant="outline" className="text-xs text-gray-400">Deleted</Badge>}
                        {s.is_active && s.is_hidden && <Badge variant="outline" className="text-xs text-gray-500">Hidden</Badge>}
                        {s.is_active && !s.is_hidden && <Badge variant="outline" className="text-xs">Active</Badge>}
                      </td>
                      <td className="py-2 text-right">
                        <Button size="sm" variant="ghost" onClick={() => openEdit(s)}><Pencil className="h-3 w-3" /></Button>
                        <Button size="sm" variant="ghost" onClick={() => remove(s)}><Trash2 className="h-3 w-3 text-red-500" /></Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </CardContent>

      <PharmacyImportDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        onImported={load}
        title="Import Suppliers"
        entityLabel="suppliers"
        importUrl="/api/pharmacy/suppliers/import"
        templateUrl="/api/pharmacy/suppliers/import/template"
        exportUrl="/api/pharmacy/suppliers/export/xlsx"
        duplicateLabel="If a supplier already exists:"
        helpText="Fill supplier name, contact, GSTIN, drug licence, and address fields. Existing suppliers are matched by name or GSTIN."
      />

      <PharmacyFormDialog
        open={open}
        onOpenChange={setOpen}
        title={editing ? `Edit Supplier — ${editing.name}` : 'New Supplier'}
        steps={steps}
        activeStep={activeStep}
        onStepChange={setActiveStep}
        onNext={handleNext}
        onSave={save}
        saving={saving}
        canProceed={activeStep !== 0 || supplierStepCanProceed(form, 0)}
        saveLabel={editing ? 'Save' : 'Create'}
      >
        <SupplierFormFields form={form} onChange={setForm} activeStep={activeStep} />
      </PharmacyFormDialog>
    </Card>
  );
}
