import React, { useEffect, useState, useCallback, useMemo } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Input } from '../../../../components/ui/input';
import { Badge } from '../../../../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../../components/ui/select';
import { useToast } from '../../../../hooks/use-toast';
import { Plus, Pencil, Trash2, RefreshCw, Search, Upload, Download, Loader2, ChevronDown, FileSpreadsheet, List } from 'lucide-react';
import PharmacyImportDialog, { downloadPharmacyBlob } from '../../../../components/pharmacy/PharmacyImportDialog';
import MappedImportDialog, { MEDICINE_MAP_FIELDS } from '../../../../components/pharmacy/MappedImportDialog';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '../../../../components/ui/dropdown-menu';
import PharmacyFormDialog from '../../../../components/pharmacy/PharmacyFormDialog';
import { errMsg } from '../../PharmacyModule';
import { usePharmacyMedicineMasters } from '../../../../hooks/usePharmacyMedicineMasters';
import MedicineFormFields, {
  EMPTY_MEDICINE_FORM,
  MEDICINE_FORM_STEPS,
  medicineStepCanProceed,
  prepareMedicinePayload,
} from '../../../../components/pharmacy/MedicineFormFields';
import { costPcsFromMrp, formatMoney } from '../../../../utils/pharmacyUnits';

export default function MedicinesTab() {
  const { toast } = useToast();
  const [rows, setRows] = useState([]);
  const [search, setSearch] = useState('');
  const [scheduleFilter, setScheduleFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [templateImportOpen, setTemplateImportOpen] = useState(false);
  const [mappedImportOpen, setMappedImportOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_MEDICINE_FORM);
  const [activeStep, setActiveStep] = useState(0);
  const [saving, setSaving] = useState(false);

  const { masters, setMasters, reload: loadMasters } = usePharmacyMedicineMasters(true);
  const { categories } = masters;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { include_hidden: true, active_only: true };
      if (search) params.search = search;
      if (scheduleFilter) params.schedule = scheduleFilter;
      if (categoryFilter) params.category_id = categoryFilter;
      const r = await axios.get('/api/pharmacy/medicines', { params });
      setRows(r.data || []);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Failed to load medicines', description: errMsg(e) });
    } finally { setLoading(false); }
  }, [search, scheduleFilter, categoryFilter, toast]);

  useEffect(() => { loadMasters(); }, [loadMasters]);
  useEffect(() => { load(); }, [load]);

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_MEDICINE_FORM);
    setActiveStep(0);
    setOpen(true);
  };
  const openEdit = (row) => {
    const merged = { ...EMPTY_MEDICINE_FORM, ...row };
    ['unit_price', 'mrp', 'purchase_rate', 'rate_a', 'rate_b', 'cost_pcs',
      'default_discount_pct', 'item_discount_pct', 'min_qty', 'max_qty', 'reorder_qty'].forEach((k) => {
      if (merged[k] === 0) merged[k] = '';
    });
    merged.cost_pcs = costPcsFromMrp(merged);
    setEditing(row);
    setForm(merged);
    setActiveStep(0);
    setOpen(true);
  };

  const steps = useMemo(
    () => MEDICINE_FORM_STEPS.map((s, i) => ({ ...s, completed: i < activeStep })),
    [activeStep],
  );

  const handleNext = () => {
    if (!medicineStepCanProceed(form, activeStep)) {
      toast({ variant: 'destructive', title: 'Code, name, and category are required' });
      return;
    }
    setActiveStep((s) => Math.min(s + 1, MEDICINE_FORM_STEPS.length - 1));
  };

  const save = async () => {
    if (!medicineStepCanProceed(form, 0)) {
      toast({ variant: 'destructive', title: 'Code, name, and category are required' });
      setActiveStep(0);
      return;
    }
    const code = (form.medicine_code || '').trim().toLowerCase();
    const codeTaken = rows.some(
      (m) => m.is_active && m.medicine_code?.trim().toLowerCase() === code
        && (!editing || m.id !== editing.id),
    );
    if (codeTaken) {
      toast({ variant: 'destructive', title: 'Medicine code already exists' });
      setActiveStep(0);
      return;
    }
    setSaving(true);
    try {
      const payload = prepareMedicinePayload(form);
      if (editing) {
        await axios.put(`/api/pharmacy/medicines/${editing.id}`, payload);
        toast({ title: 'Medicine updated' });
      } else {
        await axios.post('/api/pharmacy/medicines', payload);
        toast({ title: 'Medicine created' });
      }
      setOpen(false); load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Save failed', description: errMsg(e) });
    } finally {
      setSaving(false);
    }
  };

  const remove = async (row) => {
    const permanent = !row.is_active;
    const msg = permanent
      ? `Permanently delete ${row.name}? This removes it from the catalog and cannot be undone.`
      : `Delete ${row.name}? It will be hidden from the catalog (can be permanently purged later).`;
    if (!window.confirm(msg)) return;
    try {
      await axios.delete(`/api/pharmacy/medicines/${row.id}`, {
        params: permanent ? { permanent: true } : undefined,
      });
      toast({ title: permanent ? 'Permanently deleted' : 'Deleted' });
      load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Delete failed', description: errMsg(e) });
    }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      await downloadPharmacyBlob('/api/pharmacy/medicines/export/xlsx', 'medicines_export.xlsx', toast);
      toast({ title: 'Medicines exported' });
    } catch {
      /* toast already shown */
    } finally {
      setExporting(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between flex-wrap gap-2">
          <span>Medicines ({rows.length})</span>
          <div className="flex flex-wrap gap-2 items-center">
            <div className="relative">
              <Search className="absolute left-2 top-2.5 h-4 w-4 text-gray-400" />
              <Input className="pl-8 h-8 w-56" placeholder="Search name / code / barcode…"
                value={search} onChange={e => setSearch(e.target.value)} />
            </div>
            <Select value={scheduleFilter || 'any'} onValueChange={v => setScheduleFilter(v === 'any' ? '' : v)}>
              <SelectTrigger className="w-40 h-8"><SelectValue placeholder="Any schedule" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="any">Any schedule</SelectItem>
                <SelectItem value="h">Schedule H</SelectItem>
                <SelectItem value="h1">Schedule H1</SelectItem>
                <SelectItem value="narcotic">Narcotic</SelectItem>
                <SelectItem value="tramadol">Tramadol</SelectItem>
                <SelectItem value="controlled">Controlled</SelectItem>
              </SelectContent>
            </Select>
            <Select value={categoryFilter ? String(categoryFilter) : 'any'} onValueChange={v => setCategoryFilter(v === 'any' ? '' : Number(v))}>
              <SelectTrigger className="w-40 h-8"><SelectValue placeholder="Any category" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="any">Any category</SelectItem>
                {categories.map(c => <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>)}
              </SelectContent>
            </Select>
            <Button size="sm" variant="outline" onClick={load}><RefreshCw className="h-3 w-3" /></Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="sm" variant="outline">
                  <Upload className="h-3 w-3 mr-1" /> Import
                  <ChevronDown className="h-3 w-3 ml-1" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-72">
                <DropdownMenuItem
                  className="items-start gap-2 py-2"
                  onSelect={() => setTemplateImportOpen(true)}
                >
                  <FileSpreadsheet className="h-4 w-4 mt-0.5 text-indigo-500 shrink-0" />
                  <div>
                    <div className="font-medium">ERP template</div>
                    <div className="text-[11px] text-muted-foreground leading-snug">
                      Previous flow — download our Excel, fill named columns, preview and import.
                    </div>
                  </div>
                </DropdownMenuItem>
                <DropdownMenuItem
                  className="items-start gap-2 py-2"
                  onSelect={() => setMappedImportOpen(true)}
                >
                  <List className="h-4 w-4 mt-0.5 text-indigo-500 shrink-0" />
                  <div>
                    <div className="font-medium">Vendor file</div>
                    <div className="text-[11px] text-muted-foreground leading-snug">
                      New flow — map Excel columns from a supplier catalog, then import.
                    </div>
                  </div>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <Button size="sm" variant="outline" onClick={handleExport} disabled={exporting}>
              {exporting ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Download className="h-3 w-3 mr-1" />}
              Export
            </Button>
            <Button size="sm" onClick={openCreate}><Plus className="h-3 w-3 mr-1" /> New</Button>
          </div>
        </CardTitle>
      </CardHeader>

      <CardContent>
        {loading ? (
          <p className="text-center py-6 text-gray-500 text-sm">Loading…</p>
        ) : rows.length === 0 ? (
          <p className="text-center py-6 text-gray-500 text-sm">No medicines yet</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-600">
                  <th className="py-2 pr-4">Code</th>
                  <th className="py-2 pr-4">Name</th>
                  <th className="py-2 pr-4">Strength</th>
                  <th className="py-2 pr-4">MRP / Rate A</th>
                  <th className="py-2 pr-4">Flags</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(m => (
                  <tr key={m.id} className="border-b hover:bg-gray-50">
                    <td className="py-2 pr-4 font-mono text-xs">{m.medicine_code}</td>
                    <td className="py-2 pr-4">
                      <div className="font-medium">{m.name}</div>
                      {m.generic_name && <div className="text-xs text-gray-500">{m.generic_name}</div>}
                    </td>
                    <td className="py-2 pr-4 text-xs">{m.dosage_form} {m.strength}</td>
                    <td className="py-2 pr-4 text-xs">₹{formatMoney(m.mrp)} / ₹{formatMoney(m.rate_a || m.unit_price)}</td>
                    <td className="py-2 pr-4">
                      <div className="flex flex-wrap gap-1">
                        {m.is_narcotic && <Badge variant="outline" className="text-[10px] text-red-700">NARC</Badge>}
                        {m.is_schedule_h && <Badge variant="outline" className="text-[10px]">H</Badge>}
                        {m.is_schedule_h1 && <Badge variant="outline" className="text-[10px] text-orange-700">H1</Badge>}
                        {m.is_tramadol && <Badge variant="outline" className="text-[10px]">TRAM</Badge>}
                        {m.is_high_alert && <Badge variant="outline" className="text-[10px] text-yellow-700">HIGH</Badge>}
                      </div>
                    </td>
                    <td className="py-2 pr-4">
                      {!m.is_active && <Badge variant="outline" className="text-xs text-gray-400">Deleted</Badge>}
                      {m.is_active && m.is_hidden && <Badge variant="outline" className="text-xs text-gray-500">Hidden</Badge>}
                      {m.is_active && !m.is_hidden && <Badge variant="outline" className="text-xs">Active</Badge>}
                    </td>
                    <td className="py-2 text-right">
                      {m.is_active && (
                        <Button size="sm" variant="ghost" title="Edit"
                          onClick={() => openEdit(m)}><Pencil className="h-3 w-3" /></Button>
                      )}
                      <Button
                        size="sm"
                        variant="ghost"
                        title={m.is_active ? 'Delete' : 'Permanently delete'}
                        onClick={() => remove(m)}
                      >
                        <Trash2 className="h-3 w-3 text-red-500" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>

      <PharmacyImportDialog
        open={templateImportOpen}
        onOpenChange={setTemplateImportOpen}
        onImported={() => { load(); loadMasters(); }}
        title="Import Medicines — ERP template"
        entityLabel="medicines"
        importUrl="/api/pharmacy/medicines/import"
        templateUrl="/api/pharmacy/medicines/import/template"
        exportUrl="/api/pharmacy/medicines/export/xlsx"
        duplicateLabel="If a medicine code already exists:"
        helpText="Fill the medicines sheet with medicine_code, name, category, and pricing fields. Related masters (category, company, salt, HSN, rack, UoM) are matched by code or name and created if missing."
      />

      <MappedImportDialog
        open={mappedImportOpen}
        onOpenChange={setMappedImportOpen}
        onImported={() => { load(); loadMasters(); }}
        title="Import Medicines — vendor file"
        entityLabel="medicines"
        inspectUrl="/api/pharmacy/medicines/import/inspect"
        importUrl="/api/pharmacy/medicines/import"
        templateUrl="/api/pharmacy/medicines/import/template"
        mappingsUrl="/api/pharmacy/medicines/import/mappings"
        mapFields={MEDICINE_MAP_FIELDS}
        showDuplicateSelect
        detailsHelp="Upload a vendor catalog. Map columns on the next steps. Category, company, salt, rack, UoM, and HSN are created automatically when the mapped values are new."
        importHelp="Preview the catalog rows, then import. Existing medicine codes are skipped or updated based on your choice."
      />

      <PharmacyFormDialog
        open={open}
        onOpenChange={setOpen}
        title={editing ? `Edit Medicine — ${editing.name}` : 'New Medicine'}
        steps={steps}
        activeStep={activeStep}
        onStepChange={setActiveStep}
        onNext={handleNext}
        onSave={save}
        saving={saving}
        canProceed={activeStep !== 0 || medicineStepCanProceed(form, 0)}
        saveLabel={editing ? 'Save' : 'Create'}
      >
        <MedicineFormFields
          form={form}
          onChange={setForm}
          masters={masters}
          onMastersChange={setMasters}
          activeStep={activeStep}
        />
      </PharmacyFormDialog>
    </Card>
  );
}
