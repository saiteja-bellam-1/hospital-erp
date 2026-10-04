import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Card, CardContent } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Input } from '../../../../components/ui/input';
import { Label } from '../../../../components/ui/label';
import { Textarea } from '../../../../components/ui/textarea';
import { Badge } from '../../../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../../../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../../components/ui/select';
import { Plus, Edit2, Loader2 } from 'lucide-react';
import PatientSearchPicker from '../../../../components/PatientSearchPicker';
import { useLabFeedback } from '../useLabFeedback';
import { defaultRateCardId, testPrice } from '../../../../utils/labPricing';

const EMPTY_PARTNER = {
  name: '', contact_person: '', phone: '', email: '', address: '',
  partner_role: 'both', notes: '',
};

const ROLE_LABEL = {
  both: 'Send and receive',
  send_out: 'We send samples',
  receive_in: 'They send samples',
};

export default function PartnersTab() {
  const { showFeedback, FeedbackToast } = useLabFeedback();
  const [rateCards, setRateCards] = useState([]);
  const [rateNames, setRateNames] = useState({});
  const [partners, setPartners] = useState([]);
  const [tests, setTests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_PARTNER);

  const [patient, setPatient] = useState(null);
  const [receivePartnerId, setReceivePartnerId] = useState('');
  const [receiveRateId, setReceiveRateId] = useState('');
  const [receiveTests, setReceiveTests] = useState([]);
  const [receiveRef, setReceiveRef] = useState('');
  const [receiveNotes, setReceiveNotes] = useState('');
  const [testSearch, setTestSearch] = useState('');
  const [receiving, setReceiving] = useState(false);

  const [payables, setPayables] = useState([]);
  const [receivables, setReceivables] = useState([]);
  const [selectedSettle, setSelectedSettle] = useState([]);
  const [invoiceRef, setInvoiceRef] = useState('');
  const [settling, setSettling] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [cardsRes, partnersRes, testsRes, payRes, recRes] = await Promise.all([
        axios.get('/api/lab/rate-cards'),
        axios.get('/api/lab/partners'),
        axios.get('/api/lab/tests'),
        axios.get('/api/lab/partner-orders', { params: { fulfillment: 'send_out', settlement: 'unsettled' } }),
        axios.get('/api/lab/partner-orders', { params: { fulfillment: 'receive_in', settlement: 'unsettled' } }),
      ]);
      setRateCards(cardsRes.data || []);
      const names = {};
      (cardsRes.data || []).forEach((c) => { names[c.id] = c.name; });
      setRateNames(names);
      setPartners(partnersRes.data || []);
      setTests(testsRes.data || []);
      setPayables(payRes.data || []);
      setReceivables(recRes.data || []);
      setReceiveRateId((prev) => prev || defaultRateCardId(cardsRes.data));
    } catch (err) {
      showFeedback(err.response?.data?.detail || 'Failed to load partner labs', 'error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const saveRateName = async (card) => {
    const name = (rateNames[card.id] || '').trim();
    if (!name || name === card.name) return;
    try {
      await axios.put(`/api/lab/rate-cards/${card.id}`, { name });
      showFeedback(`${card.code} renamed`);
      load();
    } catch (err) {
      showFeedback(err.response?.data?.detail || 'Failed to rename rate', 'error');
    }
  };

  const openPartner = (partner = null) => {
    if (partner) {
      setEditing(partner);
      setForm({
        name: partner.name,
        contact_person: partner.contact_person || '',
        phone: partner.phone || '',
        email: partner.email || '',
        address: partner.address || '',
        partner_role: partner.partner_role || 'both',
        notes: partner.notes || '',
      });
    } else {
      setEditing(null);
      setForm({ ...EMPTY_PARTNER });
    }
    setShowDialog(true);
  };

  const savePartner = async () => {
    if (!form.name.trim()) return;
    const payload = { ...form };
    try {
      if (editing) await axios.put(`/api/lab/partners/${editing.id}`, payload);
      else await axios.post('/api/lab/partners', payload);
      showFeedback(editing ? 'Partner updated' : 'Partner added');
      setShowDialog(false);
      load();
    } catch (err) {
      const detail = err.response?.data?.detail;
      showFeedback(typeof detail === 'string' ? detail : 'Failed to save partner', 'error');
    }
  };

  const toggleReceiveTest = (test) => {
    setReceiveTests((prev) => (
      prev.some((t) => t.id === test.id) ? prev.filter((t) => t.id !== test.id) : [...prev, test]
    ));
  };

  const submitReceiveIn = async () => {
    if (!patient || !receivePartnerId || receiveTests.length === 0) return;
    setReceiving(true);
    try {
      await axios.post('/api/lab/orders/receive-in', {
        partner_id: parseInt(receivePartnerId, 10),
        patient_id: patient.id,
        test_ids: receiveTests.map((t) => t.id),
        rate_card_id: receiveRateId ? parseInt(receiveRateId, 10) : null,
        partner_reference: receiveRef || null,
        notes: receiveNotes || null,
      });
      showFeedback('Receive-in order registered');
      setReceiveTests([]);
      setReceiveRef('');
      setReceiveNotes('');
      load();
    } catch (err) {
      const detail = err.response?.data?.detail;
      const message = detail?.message || (typeof detail === 'string' ? detail : 'Failed to register order');
      showFeedback(message, 'error');
    } finally {
      setReceiving(false);
    }
  };

  const toggleSettle = (id) => {
    setSelectedSettle((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const settleSelected = async () => {
    if (selectedSettle.length === 0) return;
    setSettling(true);
    try {
      await axios.post('/api/lab/partner-orders/settle', {
        order_ids: selectedSettle,
        invoice_ref: invoiceRef || null,
      });
      showFeedback('Partner orders settled');
      setSelectedSettle([]);
      setInvoiceRef('');
      load();
    } catch (err) {
      const detail = err.response?.data?.detail;
      showFeedback(typeof detail === 'string' ? detail : 'Failed to settle', 'error');
    } finally {
      setSettling(false);
    }
  };

  const receiveTotal = receiveTests.reduce((sum, t) => sum + testPrice(t, receiveRateId), 0);
  const incomingPartners = partners.filter((p) => p.partner_role !== 'send_out');
  const filteredTests = tests.filter((t) => {
    if (!testSearch) return true;
    const q = testSearch.toLowerCase();
    return t.name.toLowerCase().includes(q) || (t.test_code || '').toLowerCase().includes(q);
  });

  const renderSettlementRow = (order, moneyLabel) => (
    <label key={order.id} className="flex items-start gap-3 py-2 border-b last:border-0 text-sm">
      <input
        type="checkbox"
        className="mt-1"
        checked={selectedSettle.includes(order.id)}
        onChange={() => toggleSettle(order.id)}
      />
      <div className="flex-1">
        <div className="font-medium">{order.test_name} <span className="text-gray-400 font-normal">({order.test_code})</span></div>
        <div className="text-xs text-gray-500">
          {order.patient_name} · {order.partner_name || 'Partner'} · {order.order_number}
          {order.partner_reference ? ` · Ref ${order.partner_reference}` : ''}
          {order.partner_status ? ` · ${String(order.partner_status).replace(/_/g, ' ')}` : ''}
        </div>
      </div>
      <div className="text-right text-xs">
        <div>{moneyLabel} ₹{Number(order.amount || 0).toFixed(2)}</div>
        {order.partner_cost != null && (
          <div className="text-gray-500">Their charge ₹{Number(order.partner_cost).toFixed(2)}</div>
        )}
      </div>
    </label>
  );

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <FeedbackToast />

      <Card>
        <CardContent className="py-4 space-y-3">
          <p className="text-sm font-medium">Selling rates</p>
          <p className="text-xs text-gray-500">Rate A is the default price on new bookings. Rate B is the alternate price, chosen at the counter or on an order.</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {rateCards.map((card) => (
              <div key={card.id} className="flex items-end gap-2">
                <div className="flex-1">
                  <Label>{card.code}{card.is_default ? ' (default)' : ''}</Label>
                  <Input
                    value={rateNames[card.id] || ''}
                    onChange={(e) => setRateNames({ ...rateNames, [card.id]: e.target.value })}
                  />
                </div>
                <Button variant="outline" onClick={() => saveRateName(card)}>Save</Button>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Partner labs</h2>
        <Button onClick={() => openPartner()}><Plus className="h-4 w-4 mr-2" /> Add partner</Button>
      </div>
      {partners.length === 0 ? (
        <Card><CardContent className="py-8 text-center text-sm text-gray-500">No partner labs yet.</CardContent></Card>
      ) : (
        <div className="space-y-2">
          {partners.map((p) => (
            <Card key={p.id}>
              <CardContent className="py-3 flex items-center justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{p.name}</span>
                    <Badge variant="outline">{ROLE_LABEL[p.partner_role] || p.partner_role}</Badge>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    {[p.phone, p.contact_person, p.default_rate_name && `Bill at ${p.default_rate_name}`].filter(Boolean).join(' · ') || 'No contact details'}
                  </p>
                </div>
                <Button variant="ghost" size="sm" onClick={() => openPartner(p)}><Edit2 className="h-4 w-4" /></Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Card>
        <CardContent className="py-4 space-y-3">
          <h2 className="text-lg font-semibold">Register a sample from another lab</h2>
          <p className="text-xs text-gray-500">We process the sample here and bill the partner. It does not appear on the patient’s reception bill.</p>
          <PatientSearchPicker value={patient} onChange={setPatient} label="Patient on the report" required />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <Label>Partner lab</Label>
              <Select value={receivePartnerId || '_none'} onValueChange={(v) => {
                const id = v === '_none' ? '' : v;
                setReceivePartnerId(id);
                const partner = partners.find((p) => String(p.id) === id);
                if (partner?.default_rate_card_id) setReceiveRateId(String(partner.default_rate_card_id));
              }}>
                <SelectTrigger><SelectValue placeholder="Select partner" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="_none">Select partner</SelectItem>
                  {incomingPartners.map((p) => (
                    <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Rate to bill them</Label>
              <Select value={receiveRateId || '_none'} onValueChange={(v) => setReceiveRateId(v === '_none' ? '' : v)}>
                <SelectTrigger><SelectValue placeholder="Rate" /></SelectTrigger>
                <SelectContent>
                  {rateCards.map((c) => (
                    <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div>
            <Label>Tests</Label>
            <Input className="mt-1" placeholder="Search tests..." value={testSearch} onChange={(e) => setTestSearch(e.target.value)} />
            <div className="border rounded-lg mt-2 max-h-40 overflow-y-auto divide-y">
              {filteredTests.slice(0, 40).map((test) => {
                const selected = receiveTests.some((t) => t.id === test.id);
                return (
                  <button type="button" key={test.id} className={`w-full text-left px-3 py-2 text-sm ${selected ? 'bg-blue-50' : ''}`} onClick={() => toggleReceiveTest(test)}>
                    {test.name} — ₹{testPrice(test, receiveRateId)}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <Label>Their reference</Label>
              <Input value={receiveRef} onChange={(e) => setReceiveRef(e.target.value)} placeholder="Accession or invoice no." />
            </div>
            <div>
              <Label>Notes</Label>
              <Input value={receiveNotes} onChange={(e) => setReceiveNotes(e.target.value)} />
            </div>
          </div>
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium">Partner bill ₹{receiveTotal.toFixed(2)}</p>
            <Button onClick={submitReceiveIn} disabled={receiving || !patient || !receivePartnerId || receiveTests.length === 0}>
              {receiving ? 'Saving...' : 'Register receive-in'}
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardContent className="py-4">
            <h2 className="font-semibold mb-1">We owe partner labs</h2>
            <p className="text-xs text-gray-500 mb-2">Send-out orders. The patient was billed our rate. This is what we pay the processing lab.</p>
            {payables.length === 0 ? <p className="text-sm text-gray-400">Nothing unsettled.</p> : payables.map((o) => renderSettlementRow(o, 'Patient paid'))}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4">
            <h2 className="font-semibold mb-1">Partner labs owe us</h2>
            <p className="text-xs text-gray-500 mb-2">Receive-in orders processed here.</p>
            {receivables.length === 0 ? <p className="text-sm text-gray-400">Nothing unsettled.</p> : receivables.map((o) => renderSettlementRow(o, 'Bill'))}
          </CardContent>
        </Card>
      </div>
      <div className="flex flex-col md:flex-row gap-2 md:items-end">
        <div className="flex-1">
          <Label>Partner invoice reference</Label>
          <Input value={invoiceRef} onChange={(e) => setInvoiceRef(e.target.value)} placeholder="Optional" />
        </div>
        <Button onClick={settleSelected} disabled={settling || selectedSettle.length === 0}>
          {settling ? 'Settling...' : `Settle ${selectedSettle.length} selected`}
        </Button>
      </div>

      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>{editing ? 'Edit partner' : 'New partner lab'}</DialogTitle></DialogHeader>
          <div className="space-y-3 max-h-[70vh] overflow-y-auto">
            <div>
              <Label>Name *</Label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div>
              <Label>Work we exchange</Label>
              <Select value={form.partner_role} onValueChange={(v) => setForm({ ...form, partner_role: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="both">Both directions</SelectItem>
                  <SelectItem value="send_out">We send samples to them</SelectItem>
                  <SelectItem value="receive_in">They send samples to us</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Contact</Label>
                <Input value={form.contact_person} onChange={(e) => setForm({ ...form, contact_person: e.target.value })} />
              </div>
              <div>
                <Label>Phone</Label>
                <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
              </div>
            </div>
            <div>
              <Label>Email</Label>
              <Input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </div>
            <div>
              <Label>Address</Label>
              <Textarea rows={2} value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
            </div>
            <div>
              <Label>Notes</Label>
              <Textarea rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setShowDialog(false)}>Cancel</Button>
              <Button onClick={savePartner} disabled={!form.name.trim()}>{editing ? 'Update' : 'Create'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
