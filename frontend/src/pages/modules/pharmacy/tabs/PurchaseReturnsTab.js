import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Badge } from '../../../../components/ui/badge';
import { Input } from '../../../../components/ui/input';
import { Label } from '../../../../components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../../../components/ui/tabs';
import { useToast } from '../../../../hooks/use-toast';
import { errMsg } from '../../PharmacyModule';
import PdfPreviewDialog from '../../../../components/PdfPreviewDialog';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../../../components/ui/dialog';
import { Plus, RefreshCw, Eye, Truck, FileText, Link2, Printer } from 'lucide-react';
import { usePharmacyPermissions } from '../../../../hooks/usePharmacyPermissions';

const STATUS_LABELS = {
  draft: 'Draft',
  confirmed: 'Confirmed',
  challan_created: 'Challan created',
  cn_recorded: 'CN recorded',
  debit_note_issued: 'Debit note issued',
  partial: 'Partial',
  completed: 'Completed',
  cancelled: 'Cancelled',
};

function statusLabel(status) {
  return STATUS_LABELS[status] || status || '—';
}

function returnLabel(r) {
  if (!r) return '';
  const total = (r.grand_total || 0).toFixed?.(2) ?? r.grand_total;
  return `${r.return_number} · ${r.supplier_name || 'Supplier'} · ₹${total}`;
}

function pendingCn(r) {
  if (!r) return 0;
  if (r.pending_cn_amount != null) return Number(r.pending_cn_amount) || 0;
  const total = Number(r.grand_total) || 0;
  const cn = Number(r.cn_total != null ? r.cn_total : r.supplier_credit_note_amount) || 0;
  return Math.max(0, total - cn);
}

function isEligible(tab, r) {
  if (!r || r.status === 'cancelled') return false;
  if (tab === 'challan') {
    if (r.status === 'draft' || r.status === 'completed') return false;
    if (r.goods_fully_challaned) return false;
    // Remaining goods, or never challaned yet
    return r.status === 'confirmed' || !!r.has_challan || (r.items || []).some((it) => (it.quantity_remaining ?? it.quantity) > 0);
  }
  if (tab === 'supplier-cn') {
    return !!r.has_challan && pendingCn(r) > 0.000001 && r.status !== 'completed';
  }
  if (tab === 'debit-note') {
    const cn = Number(r.cn_total != null ? r.cn_total : (r.supplier_credit_note_amount || 0)) || 0;
    const dn = Number(r.dn_total != null ? r.dn_total : (r.debit_note?.amount || 0)) || 0;
    return cn > dn + 0.000001;
  }
  if (tab === 'allocate') return !!(r.debit_note || (r.debit_notes && r.debit_notes.length));
  return true;
}

function nextWorkflowTab(r) {
  if (!r) return 'returns';
  if (r.status === 'draft' || r.status === 'cancelled') return 'returns';
  if (r.status === 'confirmed' || (r.has_challan === false && r.status !== 'completed')) return 'challan';
  if (!r.goods_fully_challaned && r.has_challan && pendingCn(r) <= 0) return 'challan';
  if (pendingCn(r) > 0.000001) return 'supplier-cn';
  const cn = Number(r.cn_total != null ? r.cn_total : (r.supplier_credit_note_amount || 0)) || 0;
  const dn = Number(r.dn_total != null ? r.dn_total : 0) || 0;
  if (cn > dn + 0.000001) return 'debit-note';
  if (r.status === 'partial') return 'supplier-cn';
  if (r.debit_note || r.status === 'completed') return 'allocate';
  if (r.status === 'challan_created') return 'supplier-cn';
  if (r.status === 'cn_recorded') return 'debit-note';
  return 'returns';
}

function ReturnSelect({ rows, value, onChange, emptyText }) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">Purchase return</Label>
      <select
        className="w-full border rounded h-9 px-2 text-sm bg-white"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">{emptyText || 'Select a purchase return…'}</option>
        {rows.map((r) => (
          <option key={r.id} value={String(r.id)}>{returnLabel(r)}</option>
        ))}
      </select>
      {rows.length === 0 && (
        <p className="text-xs text-amber-700">No purchase returns are eligible for this step yet.</p>
      )}
    </div>
  );
}

function SelectedReturnSummary({ doc, onOpen }) {
  if (!doc) return null;
  return (
    <div className="rounded-md border bg-slate-50 px-3 py-2 text-sm flex flex-wrap items-center justify-between gap-2">
      <div>
        <div className="font-medium">{doc.return_number}</div>
        <div className="text-xs text-gray-600">
          {doc.supplier_name || '—'} · {doc.return_date} · ₹{(doc.grand_total || 0).toFixed?.(2) ?? doc.grand_total}
          {' · '}<Badge variant="outline" className="text-[10px] align-middle">{statusLabel(doc.status)}</Badge>
        </div>
      </div>
      {onOpen && (
        <Button size="sm" variant="outline" className="h-8" onClick={onOpen}>
          <Eye className="h-3 w-3 mr-1" /> Open return
        </Button>
      )}
    </div>
  );
}

function HistoryTable({ title, emptyText, children, count }) {
  return (
    <Card>
      <CardHeader className="py-3 px-4">
        <CardTitle className="text-base">{title}{count != null ? ` (${count})` : ''}</CardTitle>
      </CardHeader>
      <CardContent className="pt-0 px-4 pb-4">
        {count === 0 ? (
          <p className="text-sm text-gray-500 py-4 text-center">{emptyText}</p>
        ) : (
          <div className="overflow-x-auto">{children}</div>
        )}
      </CardContent>
    </Card>
  );
}

export default function PurchaseReturnsTab() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { hasPerm } = usePharmacyPermissions();

  const initialTab = searchParams.get('tab') || 'returns';
  const initialReturnId = searchParams.get('returnId') || '';

  const [tab, setTab] = useState(initialTab);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState(initialReturnId);
  const [doc, setDoc] = useState(null);
  const [saving, setSaving] = useState(false);
  const [challanForm, setChallanForm] = useState({ transporter: '', vehicle: '', notes: '' });
  const [cnForm, setCnForm] = useState({
    supplier_credit_note_number: '',
    supplier_credit_note_date: '',
    supplier_credit_note_amount: '',
  });
  const [allocRows, setAllocRows] = useState([{ purchase_id: '', amount: '' }]);
  const [payables, setPayables] = useState(null);
  const [preview, setPreview] = useState({ open: false, path: null, title: '' });
  const [detail, setDetail] = useState(null);

  const loadRows = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (search) params.search = search;
      const r = await axios.get('/api/pharmacy/purchase-returns', { params });
      setRows(r.data || []);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Failed to load', description: errMsg(e) });
    } finally {
      setLoading(false);
    }
  }, [search, toast]);

  useEffect(() => { loadRows(); }, [loadRows]);

  useEffect(() => {
    const t = searchParams.get('tab');
    const rid = searchParams.get('returnId') || '';
    if (t && t !== tab) setTab(t);
    if (rid !== selectedId) setSelectedId(rid);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const syncUrl = (nextTab, nextReturnId) => {
    const params = new URLSearchParams();
    if (nextTab && nextTab !== 'returns') params.set('tab', nextTab);
    if (nextReturnId) params.set('returnId', String(nextReturnId));
    setSearchParams(params, { replace: true });
  };

  const onTabChange = (v) => {
    setTab(v);
    setDoc(null);
    const eligible = (rows || []).filter((r) => isEligible(v, r));
    const keep = eligible.some((r) => String(r.id) === String(selectedId));
    const nextId = keep ? selectedId : '';
    setSelectedId(nextId);
    syncUrl(v, nextId);
  };

  const onSelectReturn = (id) => {
    setSelectedId(id);
    syncUrl(tab, id);
  };

  const loadDoc = useCallback(async (rid) => {
    if (!rid) {
      setDoc(null);
      setPayables(null);
      return;
    }
    try {
      const r = await axios.get(`/api/pharmacy/purchase-returns/${rid}`);
      const d = r.data;
      setDoc(d);
      setCnForm({
        supplier_credit_note_number: '',
        supplier_credit_note_date: '',
        supplier_credit_note_amount: pendingCn(d) > 0 ? String(pendingCn(d)) : '',
      });
      if (d.debit_note?.allocations?.length) {
        setAllocRows(d.debit_note.allocations.map((a) => ({
          purchase_id: String(a.purchase_id),
          amount: String(a.amount),
        })));
      } else {
        setAllocRows([{ purchase_id: '', amount: '' }]);
      }
      if (d.supplier_id && d.debit_note) {
        try {
          const p = await axios.get(`/api/pharmacy/suppliers/${d.supplier_id}/payables`);
          setPayables(p.data);
        } catch {
          setPayables(null);
        }
      } else {
        setPayables(null);
      }
    } catch (e) {
      setDoc(null);
      toast({ variant: 'destructive', title: 'Failed to load return', description: errMsg(e) });
    }
  }, [toast]);

  useEffect(() => {
    if (tab === 'returns') return;
    loadDoc(selectedId);
  }, [tab, selectedId, loadDoc]);

  const eligible = useMemo(
    () => (tab === 'returns' ? rows : rows.filter((r) => isEligible(tab, r))),
    [rows, tab],
  );

  const challanHistory = useMemo(
    () => rows.filter((r) => r.has_challan),
    [rows],
  );
  const cnHistory = useMemo(
    () => rows.filter((r) => (r.cn_total || 0) > 0 || r.supplier_credit_note_number),
    [rows],
  );
  const dnHistory = useMemo(
    () => rows.filter((r) => r.debit_note || (r.debit_notes && r.debit_notes.length)),
    [rows],
  );

  const printChallan = (returnId) => setPreview({
    open: true,
    title: 'Challan',
    path: `/api/pharmacy/purchase-returns/${returnId}/challan/pdf`,
  });
  const printDn = (dnId) => setPreview({
    open: true,
    title: 'Debit Note',
    path: `/api/pharmacy/debit-notes/${dnId}/pdf`,
  });
  const printReturn = (returnId) => setPreview({
    open: true,
    title: 'Purchase Return',
    path: `/api/pharmacy/purchase-returns/${returnId}/pdf`,
  });

  const refreshAfterAction = async (updated) => {
    setDoc(updated);
    await loadRows();
    const next = nextWorkflowTab(updated);
    if (next !== tab) {
      setTab(next);
      syncUrl(next, updated.id);
      toast({ title: `Continue to ${next.replace('-', ' ')}` });
    }
  };

  const createChallan = async () => {
    if (!doc?.id) return;
    setSaving(true);
    try {
      const r = await axios.post(`/api/pharmacy/purchase-returns/${doc.id}/challan`, challanForm);
      toast({ title: 'Challan created — stock reduced' });
      setChallanForm({ transporter: '', vehicle: '', notes: '' });
      await refreshAfterAction(r.data);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Challan failed', description: errMsg(e) });
    } finally {
      setSaving(false);
    }
  };

  const recordCn = async () => {
    if (!doc?.id) return;
    setSaving(true);
    try {
      const r = await axios.post(`/api/pharmacy/purchase-returns/${doc.id}/supplier-credit-note`, {
        supplier_credit_note_number: cnForm.supplier_credit_note_number,
        supplier_credit_note_date: cnForm.supplier_credit_note_date || null,
        supplier_credit_note_amount: cnForm.supplier_credit_note_amount === ''
          ? null : Number(cnForm.supplier_credit_note_amount),
      });
      toast({
        title: pendingCn(r.data) > 0.000001
          ? `CN recorded — ₹${pendingCn(r.data).toFixed(2)} still pending`
          : 'Supplier credit note recorded — fully covered',
      });
      await refreshAfterAction(r.data);
    } catch (e) {
      toast({ variant: 'destructive', title: 'CN failed', description: errMsg(e) });
    } finally {
      setSaving(false);
    }
  };

  const issueDn = async () => {
    if (!doc?.id) return;
    setSaving(true);
    try {
      const r = await axios.post(`/api/pharmacy/purchase-returns/${doc.id}/debit-note`, {});
      toast({ title: r.data.status === 'completed' ? 'Debit note issued — return completed' : 'Debit note issued — return still partial' });
      await refreshAfterAction(r.data);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Debit note failed', description: errMsg(e) });
    } finally {
      setSaving(false);
    }
  };

  const allocate = async () => {
    if (!doc?.debit_note) return;
    setSaving(true);
    try {
      const r = await axios.post(`/api/pharmacy/debit-notes/${doc.debit_note.id}/allocate`, {
        allocations: allocRows
          .filter((a) => a.purchase_id && a.amount)
          .map((a) => ({ purchase_id: Number(a.purchase_id), amount: Number(a.amount) })),
      });
      toast({ title: 'Debit note allocated' });
      const nextDoc = { ...doc, debit_note: r.data };
      setDoc(nextDoc);
      await loadRows();
      if (doc.supplier_id) {
        const p = await axios.get(`/api/pharmacy/suppliers/${doc.supplier_id}/payables`);
        setPayables(p.data);
      }
    } catch (e) {
      toast({ variant: 'destructive', title: 'Allocate failed', description: errMsg(e) });
    } finally {
      setSaving(false);
    }
  };

  const openReturn = (id) => navigate(`/dashboard/pharmacy/purchase-returns/${id}`);
  const continueWorkflow = (r) => {
    const next = nextWorkflowTab(r);
    setTab(next);
    setSelectedId(String(r.id));
    syncUrl(next, r.id);
  };

  const showChallan = hasPerm('create_return_challan');
  const showCn = hasPerm('record_supplier_credit_note');
  const showDn = hasPerm('issue_debit_note');
  const showAlloc = hasPerm('allocate_debit_note');

  return (
    <div className="space-y-3">
      <Tabs value={tab} onValueChange={onTabChange} className="w-full">
        <TabsList className="inline-flex h-auto w-fit max-w-full flex-wrap justify-start gap-1.5 rounded-lg bg-muted p-1.5">
          <TabsTrigger value="returns" className="h-11 px-5 text-base font-semibold data-[state=active]:shadow-sm">
            Returns
          </TabsTrigger>
          {showChallan && (
            <TabsTrigger value="challan" className="h-11 px-5 text-base font-semibold data-[state=active]:shadow-sm">
              Challan
            </TabsTrigger>
          )}
          {showCn && (
            <TabsTrigger value="supplier-cn" className="h-11 px-5 text-base font-semibold data-[state=active]:shadow-sm">
              Supplier CN
            </TabsTrigger>
          )}
          {showDn && (
            <TabsTrigger value="debit-note" className="h-11 px-5 text-base font-semibold data-[state=active]:shadow-sm">
              Debit Note
            </TabsTrigger>
          )}
          {showAlloc && (
            <TabsTrigger value="allocate" className="h-11 px-5 text-base font-semibold data-[state=active]:shadow-sm">
              Allocate
            </TabsTrigger>
          )}
        </TabsList>

        <TabsContent value="returns" className="mt-3">
          <Card>
            <CardHeader>
              <CardTitle className="flex flex-wrap justify-between items-center gap-2">
                <span>Purchase Returns ({rows.length})</span>
                <div className="flex gap-2 items-center">
                  <Input
                    className="h-8 w-48"
                    placeholder="Search…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); loadRows(); } }}
                  />
                  <Button size="sm" variant="outline" onClick={loadRows}>
                    <RefreshCw className="h-3 w-3" />
                  </Button>
                  {hasPerm('create_purchase_return') && (
                    <Button size="sm" onClick={() => navigate('/dashboard/pharmacy/purchase-returns/new')}>
                      <Plus className="h-3 w-3 mr-1" /> New Return
                    </Button>
                  )}
                </div>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {loading ? (
                <p className="text-center py-6 text-sm text-gray-500">Loading…</p>
              ) : rows.length === 0 ? (
                <p className="text-center py-6 text-sm text-gray-500">No purchase returns yet</p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-gray-600">
                      <th className="py-2 pr-4">Return #</th>
                      <th className="py-2 pr-4">Date</th>
                      <th className="py-2 pr-4">Supplier</th>
                      <th className="py-2 pr-4">Total</th>
                      <th className="py-2 pr-4">CN total</th>
                      <th className="py-2 pr-4">Pending</th>
                      <th className="py-2 pr-4">Challan</th>
                      <th className="py-2 pr-4">DN</th>
                      <th className="py-2 pr-4">Status</th>
                      <th className="py-2 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.id} className="border-b hover:bg-gray-50">
                        <td className="py-2 pr-4 font-mono text-xs">{r.return_number}</td>
                        <td className="py-2 pr-4 text-xs">{r.return_date}</td>
                        <td className="py-2 pr-4">{r.supplier_name || '—'}</td>
                        <td className="py-2 pr-4">₹{(r.grand_total || 0).toFixed(2)}</td>
                        <td className="py-2 pr-4">₹{(r.cn_total || 0).toFixed(2)}</td>
                        <td className="py-2 pr-4">
                          {pendingCn(r) > 0.000001 ? (
                            <span className="text-amber-700 font-medium">₹{pendingCn(r).toFixed(2)}</span>
                          ) : (
                            <span className="text-gray-400">₹0.00</span>
                          )}
                        </td>
                        <td className="py-2 pr-4 text-xs">{r.has_challan ? ((r.challans?.length || 1) > 1 ? `${r.challans.length} challans` : (r.challan?.challan_number || 'Yes')) : '—'}</td>
                        <td className="py-2 pr-4 text-xs">{r.debit_notes?.length > 1 ? `${r.debit_notes.length} DNs` : (r.debit_note?.debit_note_number || '—')}</td>
                        <td className="py-2 pr-4"><Badge variant="outline" className="text-xs">{statusLabel(r.status)}</Badge></td>
                        <td className="py-2 text-right">
                          <div className="inline-flex gap-1 flex-wrap justify-end">
                            <Button size="sm" variant="ghost" onClick={() => openReturn(r.id)} title="Open">
                              <Eye className="h-3 w-3" />
                            </Button>
                            <Button size="sm" variant="ghost" title="Print return" onClick={() => printReturn(r.id)}>
                              <Printer className="h-3 w-3" />
                            </Button>
                            {r.has_challan && (
                              <Button size="sm" variant="outline" className="h-8" onClick={() => printChallan(r.id)}>
                                Challan
                              </Button>
                            )}
                            {r.debit_note && (
                              <Button size="sm" variant="outline" className="h-8" onClick={() => printDn(r.debit_note.id)}>
                                DN
                              </Button>
                            )}
                            {r.status !== 'draft' && r.status !== 'cancelled' && r.status !== 'completed' && (
                              <Button size="sm" variant="outline" className="h-8" onClick={() => continueWorkflow(r)}>
                                Continue
                              </Button>
                            )}
                            <Button size="sm" variant="ghost" title="View details" onClick={() => setDetail(r)}>
                              View
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {showChallan && (
          <TabsContent value="challan" className="mt-3 space-y-3">
            <Card>
              <CardHeader className="py-3 px-4">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Truck className="h-4 w-4" /> Create challan (stock out)
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0 px-4 pb-4 space-y-3">
                <ReturnSelect
                  rows={eligible}
                  value={selectedId}
                  onChange={onSelectReturn}
                  emptyText="Select return with remaining goods to challan…"
                />
                <SelectedReturnSummary doc={doc} onOpen={doc ? () => openReturn(doc.id) : null} />
                {doc && isEligible('challan', doc) && (
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <div>
                      <Label>Transporter</Label>
                      <Input value={challanForm.transporter} onChange={(e) => setChallanForm({ ...challanForm, transporter: e.target.value })} />
                    </div>
                    <div>
                      <Label>Vehicle</Label>
                      <Input value={challanForm.vehicle} onChange={(e) => setChallanForm({ ...challanForm, vehicle: e.target.value })} />
                    </div>
                    <div>
                      <Label>Notes</Label>
                      <Input value={challanForm.notes} onChange={(e) => setChallanForm({ ...challanForm, notes: e.target.value })} />
                    </div>
                    <div className="md:col-span-3 flex gap-2">
                      <Button onClick={createChallan} disabled={saving}>{doc?.has_challan ? 'Create another challan' : 'Create Challan'}</Button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            <HistoryTable
              title="Created challans"
              emptyText="No challans created yet"
              count={challanHistory.length}
            >
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-gray-600">
                    <th className="py-2 pr-3">Challan #</th>
                    <th className="py-2 pr-3">Date</th>
                    <th className="py-2 pr-3">Return #</th>
                    <th className="py-2 pr-3">Supplier</th>
                    <th className="py-2 pr-3">Transporter</th>
                    <th className="py-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {challanHistory.map((r) => (
                    <tr key={r.id} className="border-b hover:bg-gray-50">
                      <td className="py-2 pr-3 font-mono text-xs">{r.challan.challan_number}</td>
                      <td className="py-2 pr-3 text-xs">{r.challan.challan_date}</td>
                      <td className="py-2 pr-3 font-mono text-xs">{r.return_number}</td>
                      <td className="py-2 pr-3">{r.supplier_name || '—'}</td>
                      <td className="py-2 pr-3 text-xs">{r.challan.transporter || '—'}</td>
                      <td className="py-2 text-right">
                        <div className="inline-flex gap-1 justify-end">
                          <Button size="sm" variant="outline" className="h-8" onClick={() => setDetail(r)}>View</Button>
                          <Button size="sm" variant="outline" className="h-8" onClick={() => printChallan(r.id)}>
                            <Printer className="h-3 w-3 mr-1" /> Print
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </HistoryTable>
          </TabsContent>
        )}

        {showCn && (
          <TabsContent value="supplier-cn" className="mt-3 space-y-3">
            <Card>
              <CardHeader className="py-3 px-4">
                <CardTitle className="text-base">Record supplier credit note</CardTitle>
              </CardHeader>
              <CardContent className="pt-0 px-4 pb-4 space-y-3">
                <ReturnSelect
                  rows={eligible}
                  value={selectedId}
                  onChange={onSelectReturn}
                  emptyText="Select return with pending CN amount…"
                />
                <SelectedReturnSummary doc={doc} onOpen={doc ? () => openReturn(doc.id) : null} />
                {doc && (
                  <p className="text-sm text-gray-600">
                    Return ₹{(doc.grand_total || 0).toFixed(2)} · CN received ₹{(doc.cn_total || 0).toFixed(2)} ·
                    {' '}<span className={pendingCn(doc) > 0 ? 'text-amber-700 font-medium' : ''}>
                      Pending ₹{pendingCn(doc).toFixed(2)}
                    </span>
                  </p>
                )}
                {doc && isEligible('supplier-cn', doc) && (
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <div>
                      <Label>CN number</Label>
                      <Input
                        value={cnForm.supplier_credit_note_number}
                        onChange={(e) => setCnForm({ ...cnForm, supplier_credit_note_number: e.target.value })}
                      />
                    </div>
                    <div>
                      <Label>CN date</Label>
                      <Input
                        type="date"
                        value={cnForm.supplier_credit_note_date}
                        onChange={(e) => setCnForm({ ...cnForm, supplier_credit_note_date: e.target.value })}
                      />
                    </div>
                    <div>
                      <Label>CN amount</Label>
                      <Input
                        value={cnForm.supplier_credit_note_amount}
                        onChange={(e) => setCnForm({ ...cnForm, supplier_credit_note_amount: e.target.value })}
                        placeholder={String(pendingCn(doc) || doc.grand_total || '')}
                      />
                    </div>
                    <div className="md:col-span-3">
                      <Button onClick={recordCn} disabled={saving}>{(doc?.credit_notes?.length || 0) > 0 ? 'Add another CN' : 'Save CN reference'}</Button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            <HistoryTable
              title="Recorded supplier credit notes"
              emptyText="No supplier credit notes recorded yet"
              count={cnHistory.length}
            >
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-gray-600">
                    <th className="py-2 pr-3">Latest CN #</th>
                    <th className="py-2 pr-3">CN total</th>
                    <th className="py-2 pr-3">Pending</th>
                    <th className="py-2 pr-3">Return #</th>
                    <th className="py-2 pr-3">Supplier</th>
                    <th className="py-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {cnHistory.map((r) => (
                    <tr key={r.id} className="border-b hover:bg-gray-50">
                      <td className="py-2 pr-3 font-mono text-xs">
                        {r.supplier_credit_note_number || '—'}
                        {(r.credit_notes?.length || 0) > 1 ? ` (+${r.credit_notes.length - 1})` : ''}
                      </td>
                      <td className="py-2 pr-3">₹{(r.cn_total || 0).toFixed(2)}</td>
                      <td className="py-2 pr-3">
                        {pendingCn(r) > 0.000001 ? (
                          <span className="text-amber-700 font-medium">₹{pendingCn(r).toFixed(2)}</span>
                        ) : '₹0.00'}
                      </td>
                      <td className="py-2 pr-3 font-mono text-xs">{r.return_number}</td>
                      <td className="py-2 pr-3">{r.supplier_name || '—'}</td>
                      <td className="py-2 text-right">
                        <div className="inline-flex gap-1 justify-end">
                          <Button size="sm" variant="outline" className="h-8" onClick={() => setDetail(r)}>View</Button>
                          {r.has_challan && (
                            <Button size="sm" variant="outline" className="h-8" onClick={() => printChallan(r.id)}>
                              <Printer className="h-3 w-3 mr-1" /> Challan
                            </Button>
                          )}
                          {r.debit_note && (
                            <Button size="sm" variant="outline" className="h-8" onClick={() => printDn(r.debit_note.id)}>
                              <Printer className="h-3 w-3 mr-1" /> DN
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </HistoryTable>
          </TabsContent>
        )}

        {showDn && (
          <TabsContent value="debit-note" className="mt-3 space-y-3">
            <Card>
              <CardHeader className="py-3 px-4">
                <CardTitle className="flex items-center gap-2 text-base">
                  <FileText className="h-4 w-4" /> Issue debit note
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0 px-4 pb-4 space-y-3">
                <ReturnSelect
                  rows={eligible}
                  value={selectedId}
                  onChange={onSelectReturn}
                  emptyText="Select return with CN not yet fully debit-noted…"
                />
                <SelectedReturnSummary doc={doc} onOpen={doc ? () => openReturn(doc.id) : null} />
                {doc && isEligible('debit-note', doc) && (
                  <>
                    <p className="text-sm text-gray-600">
                      CN total ₹{(doc.cn_total || 0).toFixed(2)} · DN total ₹{(doc.dn_total || 0).toFixed(2)} ·
                      Uncovered ₹{Math.max(0, (doc.cn_total || 0) - (doc.dn_total || 0)).toFixed(2)}
                      {pendingCn(doc) > 0 ? ` · Return still pending ₹${pendingCn(doc).toFixed(2)}` : ''}
                    </p>
                    <Button onClick={issueDn} disabled={saving}>{(doc?.debit_notes?.length || 0) > 0 ? 'Issue another debit note' : 'Issue Debit Note'}</Button>
                  </>
                )}
              </CardContent>
            </Card>

            <HistoryTable
              title="Issued debit notes"
              emptyText="No debit notes issued yet"
              count={dnHistory.length}
            >
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-gray-600">
                    <th className="py-2 pr-3">DN #</th>
                    <th className="py-2 pr-3">Date</th>
                    <th className="py-2 pr-3">Amount</th>
                    <th className="py-2 pr-3">Return #</th>
                    <th className="py-2 pr-3">Supplier</th>
                    <th className="py-2 pr-3">Return status</th>
                    <th className="py-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {dnHistory.map((r) => (
                    <tr key={r.id} className="border-b hover:bg-gray-50">
                      <td className="py-2 pr-3 font-mono text-xs">{r.debit_note.debit_note_number}</td>
                      <td className="py-2 pr-3 text-xs">{r.debit_note.debit_note_date}</td>
                      <td className="py-2 pr-3">₹{(r.debit_note.amount || 0).toFixed?.(2) ?? r.debit_note.amount}</td>
                      <td className="py-2 pr-3 font-mono text-xs">{r.return_number}</td>
                      <td className="py-2 pr-3">{r.supplier_name || '—'}</td>
                      <td className="py-2 pr-3">
                        <Badge variant="outline" className="text-xs">{statusLabel(r.status)}</Badge>
                      </td>
                      <td className="py-2 text-right">
                        <div className="inline-flex gap-1 justify-end">
                          <Button size="sm" variant="outline" className="h-8" onClick={() => setDetail(r)}>View</Button>
                          <Button size="sm" variant="outline" className="h-8" onClick={() => printDn(r.debit_note.id)}>
                            <Printer className="h-3 w-3 mr-1" /> DN
                          </Button>
                          {r.has_challan && (
                            <Button size="sm" variant="outline" className="h-8" onClick={() => printChallan(r.id)}>
                              <Printer className="h-3 w-3 mr-1" /> Challan
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </HistoryTable>
          </TabsContent>
        )}

        {showAlloc && (
          <TabsContent value="allocate" className="mt-3 space-y-3">
            <Card>
              <CardHeader className="py-3 px-4">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Link2 className="h-4 w-4" /> Allocate debit note
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0 px-4 pb-4 space-y-3">
                <ReturnSelect
                  rows={eligible}
                  value={selectedId}
                  onChange={onSelectReturn}
                  emptyText="Select return with debit note…"
                />
                <SelectedReturnSummary doc={doc} onOpen={doc ? () => openReturn(doc.id) : null} />
                {doc?.debit_note && (
                  <>
                    <p className="text-sm text-gray-600">
                      Debit note {doc.debit_note.debit_note_number} · ₹
                      {doc.debit_note.amount?.toFixed?.(2) ?? doc.debit_note.amount}
                    </p>
                    {payables && (
                      <p className="text-sm text-gray-600">
                        Supplier outstanding ₹{payables.outstanding?.toFixed(2)} across {payables.purchases?.length || 0} credit purchases
                      </p>
                    )}
                    {(allocRows.length ? allocRows : [{ purchase_id: '', amount: '' }]).map((row, idx) => (
                      <div key={idx} className="grid grid-cols-1 md:grid-cols-3 gap-2">
                        <select
                          className="border rounded h-9 px-2"
                          value={row.purchase_id}
                          onChange={(e) => {
                            const next = [...(allocRows.length ? allocRows : [{ purchase_id: '', amount: '' }])];
                            next[idx] = { ...next[idx], purchase_id: e.target.value };
                            setAllocRows(next);
                          }}
                        >
                          <option value="">Purchase…</option>
                          {(payables?.purchases || []).map((p) => (
                            <option key={p.purchase_id} value={p.purchase_id}>
                              {p.purchase_number} outstanding ₹{p.outstanding.toFixed(2)}
                            </option>
                          ))}
                        </select>
                        <Input
                          value={row.amount}
                          placeholder="Amount"
                          onChange={(e) => {
                            const next = [...(allocRows.length ? allocRows : [{ purchase_id: '', amount: '' }])];
                            next[idx] = { ...next[idx], amount: e.target.value };
                            setAllocRows(next);
                          }}
                        />
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setAllocRows((allocRows.length ? allocRows : []).filter((_, i) => i !== idx))}
                        >
                          Remove
                        </Button>
                      </div>
                    ))}
                    <div className="flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setAllocRows([...(allocRows.length ? allocRows : []), { purchase_id: '', amount: '' }])}
                      >
                        Add allocation
                      </Button>
                      <Button size="sm" onClick={allocate} disabled={saving}>Save allocations</Button>
                      {doc.has_challan && (
                        <Button size="sm" variant="outline" onClick={() => printChallan(doc.id)}>
                          <Printer className="h-3 w-3 mr-1" /> Print Challan
                        </Button>
                      )}
                      <Button size="sm" variant="outline" onClick={() => printDn(doc.debit_note.id)}>
                        <Printer className="h-3 w-3 mr-1" /> Print DN
                      </Button>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>

            <HistoryTable
              title="Debit notes ready / allocated"
              emptyText="No debit notes to allocate yet"
              count={dnHistory.length}
            >
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-gray-600">
                    <th className="py-2 pr-3">DN #</th>
                    <th className="py-2 pr-3">Return #</th>
                    <th className="py-2 pr-3">Supplier</th>
                    <th className="py-2 pr-3">Amount</th>
                    <th className="py-2 pr-3">Allocated</th>
                    <th className="py-2 text-right">Print</th>
                  </tr>
                </thead>
                <tbody>
                  {dnHistory.map((r) => {
                    const allocated = (r.debit_note.allocations || []).reduce(
                      (s, a) => s + (Number(a.amount) || 0),
                      0,
                    );
                    return (
                      <tr key={r.id} className="border-b hover:bg-gray-50">
                        <td className="py-2 pr-3 font-mono text-xs">{r.debit_note.debit_note_number}</td>
                        <td className="py-2 pr-3 font-mono text-xs">{r.return_number}</td>
                        <td className="py-2 pr-3">{r.supplier_name || '—'}</td>
                        <td className="py-2 pr-3">₹{(r.debit_note.amount || 0).toFixed?.(2) ?? r.debit_note.amount}</td>
                        <td className="py-2 pr-3">₹{allocated.toFixed(2)}</td>
                        <td className="py-2 text-right">
                          <div className="inline-flex gap-1 justify-end">
                            <Button size="sm" variant="outline" className="h-8" onClick={() => setDetail(r)}>View</Button>
                            <Button
                              size="sm"
                              variant="outline"
                              className="h-8"
                              onClick={() => {
                                setSelectedId(String(r.id));
                                syncUrl('allocate', r.id);
                              }}
                            >
                              Select
                            </Button>
                            <Button size="sm" variant="outline" className="h-8" onClick={() => printDn(r.debit_note.id)}>
                              <Printer className="h-3 w-3 mr-1" /> DN
                            </Button>
                            {r.has_challan && (
                              <Button size="sm" variant="outline" className="h-8" onClick={() => printChallan(r.id)}>
                                <Printer className="h-3 w-3 mr-1" /> Challan
                              </Button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </HistoryTable>
          </TabsContent>
        )}
      </Tabs>


      <Dialog open={!!detail} onOpenChange={(open) => { if (!open) setDetail(null); }}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {detail?.return_number || 'Purchase return'} · {statusLabel(detail?.status)}
            </DialogTitle>
          </DialogHeader>
          {detail && (
            <div className="space-y-4 text-sm">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs">
                <div><span className="text-gray-500">Date</span><div className="font-medium">{detail.return_date}</div></div>
                <div><span className="text-gray-500">Supplier</span><div className="font-medium">{detail.supplier_name || '—'}</div></div>
                <div><span className="text-gray-500">Return total</span><div className="font-medium">₹{(detail.grand_total || 0).toFixed?.(2) ?? detail.grand_total}</div></div>
                <div><span className="text-gray-500">CN received</span><div className="font-medium">₹{(detail.cn_total || 0).toFixed(2)}</div></div>
                <div><span className="text-gray-500">Pending CN</span>
                  <div className={`font-medium ${pendingCn(detail) > 0 ? 'text-amber-700' : ''}`}>
                    ₹{pendingCn(detail).toFixed(2)}
                  </div>
                </div>
                <div><span className="text-gray-500">Purchase</span><div className="font-medium">{detail.purchase_number || '—'}</div></div>
                <div><span className="text-gray-500">Reason</span><div className="font-medium">{detail.reason || '—'}</div></div>
                <div><span className="text-gray-500">Status</span><div><Badge variant="outline">{statusLabel(detail.status)}</Badge></div></div>
              </div>

              {(detail.challans?.length ? detail.challans : (detail.challan ? [detail.challan] : [])).map((c) => (
                <div key={c.id} className="rounded-md border p-3 space-y-1">
                  <div className="font-medium flex items-center justify-between gap-2">
                    <span>Challan {c.challan_number}</span>
                    <Button size="sm" variant="outline" className="h-8" onClick={() => printChallan(detail.id)}>
                      <Printer className="h-3 w-3 mr-1" /> Print
                    </Button>
                  </div>
                  <div className="text-xs text-gray-600">
                    Date {c.challan_date}
                    {c.transporter ? ` · ${c.transporter}` : ''}
                    {c.vehicle ? ` · ${c.vehicle}` : ''}
                  </div>
                </div>
              ))}

              {(detail.credit_notes?.length > 0 || detail.supplier_credit_note_number) && (
                <div className="rounded-md border p-3 text-xs space-y-1">
                  <div className="font-medium text-sm mb-1">
                    Supplier credit notes · total ₹{(detail.cn_total || 0).toFixed(2)}
                  </div>
                  {(detail.credit_notes || []).length > 0 ? (
                    detail.credit_notes.map((cn) => (
                      <div key={cn.id}>
                        #{cn.credit_note_number}
                        {cn.credit_note_date ? ` · ${cn.credit_note_date}` : ''}
                        {' · '}₹{(cn.amount || 0).toFixed(2)}
                      </div>
                    ))
                  ) : (
                    <div>
                      #{detail.supplier_credit_note_number}
                      {detail.supplier_credit_note_date ? ` · ${detail.supplier_credit_note_date}` : ''}
                      {' · '}₹{(detail.supplier_credit_note_amount ?? detail.grand_total ?? 0).toFixed?.(2)
                        ?? (detail.supplier_credit_note_amount ?? detail.grand_total)}
                    </div>
                  )}
                </div>
              )}

              {(detail.debit_notes?.length ? detail.debit_notes : (detail.debit_note ? [detail.debit_note] : [])).map((dn) => (
                <div key={dn.id} className="rounded-md border p-3 space-y-1">
                  <div className="font-medium flex items-center justify-between gap-2">
                    <span>Debit note {dn.debit_note_number}</span>
                    <Button size="sm" variant="outline" className="h-8" onClick={() => printDn(dn.id)}>
                      <Printer className="h-3 w-3 mr-1" /> Print
                    </Button>
                  </div>
                  <div className="text-xs text-gray-600">
                    Date {dn.debit_note_date}
                    {' · '}₹{(dn.amount || 0).toFixed?.(2) ?? dn.amount}
                    {' · '}{dn.status}
                  </div>
                  {(dn.allocations || []).length > 0 && (
                    <div className="text-xs mt-2">
                      Allocations:{' '}
                      {dn.allocations.map((a) => (
                        <span key={a.id} className="mr-2">
                          {a.purchase_number || a.purchase_id}: ₹{(a.amount || 0).toFixed?.(2) ?? a.amount}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}

              <div>
                <div className="font-medium mb-2">Medicines ({(detail.items || []).length})</div>
                {(detail.items || []).length === 0 ? (
                  <p className="text-xs text-gray-500">No line items on this return.</p>
                ) : (
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b text-left text-gray-600">
                        <th className="py-1.5 pr-2">Medicine</th>
                        <th className="py-1.5 pr-2">Batch</th>
                        <th className="py-1.5 pr-2 text-right">Qty</th>
                        <th className="py-1.5 pr-2 text-right">Left</th>
                        <th className="py-1.5 pr-2 text-right">Rate</th>
                        <th className="py-1.5 pr-2 text-right">Disc%</th>
                        <th className="py-1.5 text-right">Amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(detail.items || []).map((it) => (
                        <tr key={it.id} className="border-b">
                          <td className="py-1.5 pr-2">{it.medicine_name || it.medicine_id}</td>
                          <td className="py-1.5 pr-2 font-mono">{it.batch_number || it.batch_id}</td>
                          <td className="py-1.5 pr-2 text-right">{it.quantity}</td>
                          <td className="py-1.5 pr-2 text-right">{it.quantity_remaining != null ? it.quantity_remaining : '—'}</td>
                          <td className="py-1.5 pr-2 text-right">₹{(it.purchase_rate || 0).toFixed?.(2) ?? it.purchase_rate}</td>
                          <td className="py-1.5 pr-2 text-right">{it.discount_pct || 0}</td>
                          <td className="py-1.5 text-right">₹{(it.line_total || 0).toFixed?.(2) ?? it.line_total}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              <div className="flex flex-wrap gap-2 pt-1">
                <Button size="sm" variant="outline" onClick={() => printReturn(detail.id)}>
                  <Printer className="h-3 w-3 mr-1" /> Print return
                </Button>
                <Button size="sm" variant="outline" onClick={() => openReturn(detail.id)}>
                  <Eye className="h-3 w-3 mr-1" /> Open entry
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <PdfPreviewDialog
        open={preview.open}
        onClose={() => setPreview({ open: false, path: null, title: '' })}
        title={preview.title}
        path={preview.path}
      />
    </div>
  );
}
