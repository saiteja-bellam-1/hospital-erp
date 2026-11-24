import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Textarea } from '../../../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import { Loader2 } from 'lucide-react';
import { formatInr } from '../billing/BillingReportControls';
import { localDateString } from '../../../utils/localDate';

function errorMessage(err, fallback) {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  return fallback;
}

export default function FrontDeskExpensesPanel({ dateFrom, dateTo, onChanged }) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [expenses, setExpenses] = useState([]);
  const [total, setTotal] = useState(0);
  const [categories, setCategories] = useState([]);
  const [methods, setMethods] = useState([]);
  const [expenseDate, setExpenseDate] = useState(dateTo || localDateString());
  const [amount, setAmount] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [newCategory, setNewCategory] = useState('');
  const [paymentMethod, setPaymentMethod] = useState('cash');
  const [description, setDescription] = useState('');
  const [voidingId, setVoidingId] = useState(null);
  const [voidReason, setVoidReason] = useState('');

  useEffect(() => {
    setExpenseDate(dateTo || localDateString());
  }, [dateTo]);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await axios.get('/api/hospital/front-desk-expenses', {
        params: { date_from: dateFrom, date_to: dateTo },
      });
      setExpenses(res.data?.expenses || []);
      setTotal(Number(res.data?.total || 0));
      setCategories(res.data?.categories || []);
      setMethods(res.data?.payment_methods || []);
    } catch (err) {
      setExpenses([]);
      setTotal(0);
      setError(errorMessage(err, 'Could not load expenses.'));
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo]);

  useEffect(() => { load(); }, [load]);

  const save = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError('');
    try {
      const payload = {
        expense_date: expenseDate,
        amount: Number(amount),
        description,
        payment_method: paymentMethod,
      };
      if (newCategory.trim()) payload.category = newCategory.trim();
      else payload.category_id = Number(categoryId);
      await axios.post('/api/hospital/front-desk-expenses', payload);
      setAmount('');
      setDescription('');
      setNewCategory('');
      setVoidingId(null);
      await load();
      if (onChanged) onChanged();
    } catch (err) {
      setError(errorMessage(err, 'Could not save this expense.'));
    } finally {
      setSaving(false);
    }
  };

  const addCategory = async () => {
    const name = newCategory.trim();
    if (!name) return;
    setSaving(true);
    setError('');
    try {
      const res = await axios.post('/api/hospital/front-desk-expense-categories', { name });
      const saved = res.data;
      setCategories((current) => {
        if (current.some((item) => item.id === saved.id)) return current;
        return [...current, saved].sort((a, b) => a.name.localeCompare(b.name));
      });
      setCategoryId(String(saved.id));
      setNewCategory('');
    } catch (err) {
      setError(errorMessage(err, 'Could not save this category.'));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id) => {
    setSaving(true);
    setError('');
    try {
      await axios.post(`/api/hospital/front-desk-expenses/${id}/void`, { reason: voidReason });
      setVoidingId(null);
      setVoidReason('');
      await load();
      if (onChanged) onChanged();
    } catch (err) {
      setError(errorMessage(err, 'Could not remove this expense.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Front-desk expenses</CardTitle>
        <p className="text-xs font-normal text-gray-500 mt-1">
          Money paid out from the desk. The total is deducted from that day’s net on the daily breakdown.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
            {error}
          </div>
        )}
        <form onSubmit={save} className="grid gap-3 md:grid-cols-2">
          <div>
            <Label className="text-xs">Date</Label>
            <Input type="date" value={expenseDate} max={localDateString()} onChange={(e) => setExpenseDate(e.target.value)} required />
          </div>
          <div>
            <Label className="text-xs">Amount</Label>
            <Input
              type="number"
              min="0.01"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0.00"
              required
            />
          </div>
          <div>
            <Label className="text-xs">Category</Label>
            {categories.length > 0 ? (
              <Select
                value={categoryId || undefined}
                onValueChange={(value) => { setCategoryId(value); setNewCategory(''); }}
              >
                <SelectTrigger><SelectValue placeholder="Select a category" /></SelectTrigger>
                <SelectContent>
                  {categories.map((item) => (
                    <SelectItem key={item.id} value={String(item.id)}>{item.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <p className="text-xs text-gray-500 mb-1">No categories yet. Type one below.</p>
            )}
            <div className="mt-2 flex gap-2">
              <Input
                value={newCategory}
                onChange={(e) => {
                  setNewCategory(e.target.value);
                  if (e.target.value.trim()) setCategoryId('');
                }}
                placeholder={categories.length ? 'Or type a new category' : 'Category name'}
                maxLength={80}
              />
              <Button type="button" variant="outline" disabled={saving || !newCategory.trim()} onClick={addCategory}>
                Add
              </Button>
            </div>
          </div>
          <div>
            <Label className="text-xs">Paid from</Label>
            <Select value={paymentMethod} onValueChange={setPaymentMethod}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {methods.map((item) => (
                  <SelectItem key={item.id} value={item.id}>{item.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="md:col-span-2">
            <Label className="text-xs">What was it for</Label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={300}
              rows={2}
              placeholder="Tea for the waiting area, courier to the lab, ..."
              required
            />
          </div>
          <div>
            <Button type="submit" disabled={saving || (!categoryId && !newCategory.trim())}>
              {saving ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : null}
              Add expense
            </Button>
          </div>
        </form>

        {loading ? (
          <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
        ) : expenses.length === 0 ? (
          <p className="text-sm text-gray-500">No expenses in this date range.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="pb-2 pr-3">Date</th>
                  <th className="pb-2 pr-3">Category</th>
                  <th className="pb-2 pr-3">Details</th>
                  <th className="pb-2 pr-3">Paid from</th>
                  <th className="pb-2 pr-3 text-right">Amount</th>
                  <th className="pb-2" />
                </tr>
              </thead>
              <tbody>
                {expenses.map((row) => (
                  <tr key={row.id} className="border-b align-top">
                    <td className="py-2 pr-3 whitespace-nowrap">{row.expense_date}</td>
                    <td className="py-2 pr-3 whitespace-nowrap">{row.category_label}</td>
                    <td className="py-2 pr-3">
                      <div>{row.description}</div>
                      <div className="text-[11px] text-gray-400">{row.created_by_name}</div>
                      {voidingId === row.id && (
                        <div className="mt-2 flex flex-wrap gap-2">
                          <Input
                            value={voidReason}
                            onChange={(e) => setVoidReason(e.target.value)}
                            placeholder="Reason for removing"
                            className="h-8 max-w-xs"
                          />
                          <Button type="button" size="sm" variant="destructive" disabled={saving} onClick={() => remove(row.id)}>
                            Remove
                          </Button>
                          <Button type="button" size="sm" variant="outline" onClick={() => { setVoidingId(null); setVoidReason(''); }}>
                            Cancel
                          </Button>
                        </div>
                      )}
                    </td>
                    <td className="py-2 pr-3 whitespace-nowrap">{row.payment_method_label}</td>
                    <td className="py-2 pr-3 text-right whitespace-nowrap">{formatInr(row.amount)}</td>
                    <td className="py-2 text-right">
                      {voidingId !== row.id && (
                        <Button type="button" size="sm" variant="ghost" onClick={() => { setVoidingId(row.id); setVoidReason(''); }}>
                          Remove
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="font-semibold">
                  <td className="py-2 pr-3" colSpan={4}>Total deducted</td>
                  <td className="py-2 pr-3 text-right">{formatInr(total)}</td>
                  <td />
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
