import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Badge } from '../ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '../ui/dialog';
import { 
  Receipt, 
  CreditCard, 
  Printer,
  CheckCircle
} from 'lucide-react';

const BillingManager = ({ consultation, onPaymentUpdate }) => {
  const [bill, setBill] = useState(null);
  const [loading, setLoading] = useState(false);
  const [paymentDialogOpen, setPaymentDialogOpen] = useState(false);
  const [printDialogOpen, setPrintDialogOpen] = useState(false);
  const [printData, setPrintData] = useState(null);
  
  // Payment form state
  const [paymentForm, setPaymentForm] = useState({
    amount_paid: '',
    payment_method: 'cash',
    transaction_reference: '',
    notes: ''
  });

  useEffect(() => {
    if (consultation?.id) {
      fetchOrGenerateBill();
    }
  }, [consultation?.id]);

  const fetchOrGenerateBill = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      
      // Try to get existing bill first
      let response = await fetch(`http://localhost:8000/api/consultations/${consultation.id}/bill`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        // If no bill exists, generate one
        response = await fetch(`http://localhost:8000/api/consultations/${consultation.id}/generate-bill`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        });
      }

      if (response.ok) {
        const data = await response.json();
        setBill(data);
        // Set payment amount to balance due by default
        setPaymentForm(prev => ({
          ...prev,
          amount_paid: data.balance_due.toString()
        }));
      }
    } catch (error) {
      console.error('Error fetching/generating bill:', error);
    } finally {
      setLoading(false);
    }
  };

  const processPayment = async () => {
    if (!bill || !paymentForm.amount_paid) return;

    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`http://localhost:8000/api/consultations/${consultation.id}/bill/payment`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          amount_paid: parseFloat(paymentForm.amount_paid),
          payment_method: paymentForm.payment_method,
          transaction_reference: paymentForm.transaction_reference,
          notes: paymentForm.notes
        })
      });

      if (response.ok) {
        const paymentData = await response.json();
        setPaymentDialogOpen(false);
        setPaymentForm({
          amount_paid: '',
          payment_method: 'cash',
          transaction_reference: '',
          notes: ''
        });
        
        // Refresh bill data
        await fetchOrGenerateBill();
        
        // Notify parent component
        if (onPaymentUpdate) {
          onPaymentUpdate(paymentData);
        }

        // Auto-show print dialog after successful payment
        await fetchPrintData();
        setPrintDialogOpen(true);
      } else {
        const error = await response.json();
        alert(error.detail || 'Payment processing failed');
      }
    } catch (error) {
      console.error('Error processing payment:', error);
      alert('Payment processing failed');
    } finally {
      setLoading(false);
    }
  };

  const fetchPrintData = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`http://localhost:8000/api/consultations/${consultation.id}/bill/print`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        setPrintData(data);
      }
    } catch (error) {
      console.error('Error fetching print data:', error);
    }
  };

  const handlePrint = () => {
    window.print();
  };

  const handleDirectPrint = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`http://localhost:8000/api/consultations/${consultation.id}/bill/download`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        }
      });

      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        
        // Create iframe for direct printing
        const iframe = document.createElement('iframe');
        iframe.style.display = 'none';
        document.body.appendChild(iframe);
        iframe.src = url;
        
        iframe.onload = () => {
          iframe.contentWindow.print();
          // Clean up after printing
          setTimeout(() => {
            document.body.removeChild(iframe);
            window.URL.revokeObjectURL(url);
          }, 1000);
        };
      } else {
        alert('Failed to print bill');
      }
    } catch (error) {
      console.error('Error printing bill:', error);
      alert('Error printing bill');
    }
  };

  const getPaymentMethodIcon = (method) => {
    switch (method) {
      case 'cash': return '💵';
      case 'card': return '💳';
      case 'upi': return '📱';
      case 'cheque': return '📝';
      case 'online': return '🌐';
      default: return '💰';
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'paid': return 'bg-green-100 text-green-800';
      case 'partial': return 'bg-yellow-100 text-yellow-800';
      case 'pending': return 'bg-red-100 text-red-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  if (loading && !bill) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <div className="text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
            <p className="text-gray-500">Loading bill...</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!bill) {
    return (
      <Card>
        <CardContent className="text-center py-8">
          <Receipt className="h-12 w-12 text-gray-400 mx-auto mb-4" />
          <p className="text-gray-500">No bill available</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span className="flex items-center gap-2">
              <Receipt className="h-5 w-5" />
              Bill Management
            </span>
            <Badge className={getStatusColor(bill.status)}>
              {bill.status.toUpperCase()}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-6">
            {/* Bill Summary */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="text-sm font-medium text-gray-500">Bill Number</Label>
                <p className="font-mono text-sm mt-1">{bill.bill_number}</p>
              </div>
              <div>
                <Label className="text-sm font-medium text-gray-500">Patient</Label>
                <p className="text-sm mt-1">{bill.patient_name}</p>
              </div>
              <div>
                <Label className="text-sm font-medium text-gray-500">Doctor</Label>
                <p className="text-sm mt-1">{bill.doctor_name}</p>
              </div>
              <div>
                <Label className="text-sm font-medium text-gray-500">Date</Label>
                <p className="text-sm mt-1">{new Date(bill.bill_date).toLocaleDateString()}</p>
              </div>
            </div>

            {/* Bill Items */}
            <div>
              <Label className="text-sm font-medium text-gray-500 mb-3 block">Bill Items</Label>
              <div className="border rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="text-left p-3">Item</th>
                      <th className="text-center p-3">Qty</th>
                      <th className="text-right p-3">Unit Price</th>
                      <th className="text-right p-3">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bill.items.map((item, index) => (
                      <tr key={index} className="border-t">
                        <td className="p-3">
                          <div>
                            <p className="font-medium">{item.item_name}</p>
                            <p className="text-gray-500 text-xs">{item.item_code}</p>
                          </div>
                        </td>
                        <td className="text-center p-3">{item.quantity}</td>
                        <td className="text-right p-3">₹{item.unit_price}</td>
                        <td className="text-right p-3 font-medium">₹{item.total_price}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Payment Summary */}
            <div className="bg-gray-50 rounded-lg p-4 space-y-2">
              <div className="flex justify-between">
                <span>Subtotal:</span>
                <span>₹{bill.subtotal}</span>
              </div>
              {bill.discount_amount > 0 && (
                <div className="flex justify-between text-green-600">
                  <span>Discount:</span>
                  <span>-₹{bill.discount_amount}</span>
                </div>
              )}
              {bill.tax_amount > 0 && (
                <div className="flex justify-between">
                  <span>Tax:</span>
                  <span>₹{bill.tax_amount}</span>
                </div>
              )}
              <div className="flex justify-between text-lg font-bold border-t pt-2">
                <span>Total Amount:</span>
                <span>₹{bill.total_amount}</span>
              </div>
              {bill.amount_paid > 0 && (
                <div className="flex justify-between text-green-600">
                  <span>Amount Paid:</span>
                  <span>₹{bill.amount_paid}</span>
                </div>
              )}
              {bill.balance_due > 0 && (
                <div className="flex justify-between text-red-600 font-medium">
                  <span>Balance Due:</span>
                  <span>₹{bill.balance_due}</span>
                </div>
              )}
            </div>

            {/* Action Buttons */}
            <div className="flex gap-3">
              {bill.balance_due > 0 && (
                <Dialog open={paymentDialogOpen} onOpenChange={setPaymentDialogOpen}>
                  <DialogTrigger asChild>
                    <Button className="flex items-center gap-2 flex-1">
                      <CreditCard className="h-4 w-4" />
                      Collect Payment
                    </Button>
                  </DialogTrigger>
                  <DialogContent>
                    <DialogHeader>
                      <DialogTitle>Collect Payment</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4">
                      <div className="bg-blue-50 p-3 rounded-lg">
                        <p className="text-sm">
                          <span className="font-medium">Balance Due: </span>
                          <span className="text-lg font-bold text-red-600">₹{bill.balance_due}</span>
                        </p>
                      </div>

                      <div>
                        <Label>Payment Amount</Label>
                        <Input
                          type="number"
                          value={paymentForm.amount_paid}
                          onChange={(e) => setPaymentForm({...paymentForm, amount_paid: e.target.value})}
                          placeholder="Enter amount"
                          max={bill.balance_due}
                        />
                      </div>

                      <div>
                        <Label>Payment Method</Label>
                        <Select
                          value={paymentForm.payment_method}
                          onValueChange={(value) => setPaymentForm({...paymentForm, payment_method: value})}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="cash">💵 Cash</SelectItem>
                            <SelectItem value="card">💳 Card</SelectItem>
                            <SelectItem value="upi">📱 UPI</SelectItem>
                            <SelectItem value="cheque">📝 Cheque</SelectItem>
                            <SelectItem value="online">🌐 Online</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      {(paymentForm.payment_method === 'card' || 
                        paymentForm.payment_method === 'upi' || 
                        paymentForm.payment_method === 'online') && (
                        <div>
                          <Label>Transaction Reference</Label>
                          <Input
                            value={paymentForm.transaction_reference}
                            onChange={(e) => setPaymentForm({...paymentForm, transaction_reference: e.target.value})}
                            placeholder="Enter transaction ID/reference"
                          />
                        </div>
                      )}

                      <div>
                        <Label>Notes (Optional)</Label>
                        <Input
                          value={paymentForm.notes}
                          onChange={(e) => setPaymentForm({...paymentForm, notes: e.target.value})}
                          placeholder="Payment notes"
                        />
                      </div>

                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          onClick={() => setPaymentDialogOpen(false)}
                          className="flex-1"
                        >
                          Cancel
                        </Button>
                        <Button
                          onClick={processPayment}
                          disabled={!paymentForm.amount_paid || loading}
                          className="flex-1"
                        >
                          {loading ? 'Processing...' : `Process ₹${paymentForm.amount_paid || 0}`}
                        </Button>
                      </div>
                    </div>
                  </DialogContent>
                </Dialog>
              )}

              <Button
                variant="outline"
                onClick={handleDirectPrint}
                className="flex items-center gap-2"
              >
                <Printer className="h-4 w-4" />
                Print Bill
              </Button>

              <Button
                variant="outline"
                onClick={async () => {
                  await fetchPrintData();
                  setPrintDialogOpen(true);
                }}
                className="flex items-center gap-2"
              >
                <Receipt className="h-4 w-4" />
                View Receipt
              </Button>

              {bill.status === 'paid' && (
                <Badge className="flex items-center gap-1 px-3 py-2 bg-green-100 text-green-800">
                  <CheckCircle className="h-4 w-4" />
                  Fully Paid
                </Badge>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Print Dialog */}
      <Dialog open={printDialogOpen} onOpenChange={setPrintDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Printer className="h-5 w-5" />
              Print Bill & Receipt
            </DialogTitle>
          </DialogHeader>
          
          {printData && (
            <div className="space-y-4">
              {/* Print Preview */}
              <div className="border rounded-lg p-6 bg-white print:shadow-none" id="bill-print">
                <div className="text-center mb-6">
                  <h1 className="text-2xl font-bold">{printData.hospital_info.name}</h1>
                  <p className="text-sm text-gray-600">{printData.hospital_info.address}</p>
                  <p className="text-sm text-gray-600">
                    {printData.hospital_info.phone} • {printData.hospital_info.email}
                  </p>
                </div>

                <div className="border-t border-b py-4 mb-6">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p><strong>Bill No:</strong> {printData.bill.bill_number}</p>
                      <p><strong>Date:</strong> {new Date(printData.bill.bill_date).toLocaleDateString()}</p>
                      <p><strong>Patient:</strong> {printData.bill.patient_name}</p>
                    </div>
                    <div>
                      <p><strong>Doctor:</strong> {printData.bill.doctor_name}</p>
                      <p><strong>Status:</strong> 
                        <Badge className={`ml-2 ${getStatusColor(printData.bill.status)}`}>
                          {printData.bill.status.toUpperCase()}
                        </Badge>
                      </p>
                    </div>
                  </div>
                </div>

                <table className="w-full text-sm mb-6">
                  <thead>
                    <tr className="border-b">
                      <th className="text-left py-2">Description</th>
                      <th className="text-center py-2">Qty</th>
                      <th className="text-right py-2">Rate</th>
                      <th className="text-right py-2">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {printData.bill.items.map((item, index) => (
                      <tr key={index} className="border-b">
                        <td className="py-2">
                          <div>
                            <p className="font-medium">{item.item_name}</p>
                            <p className="text-gray-500 text-xs">{item.item_code}</p>
                          </div>
                        </td>
                        <td className="text-center py-2">{item.quantity}</td>
                        <td className="text-right py-2">₹{item.unit_price}</td>
                        <td className="text-right py-2 font-medium">₹{item.total_price}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                <div className="border-t pt-4">
                  <div className="flex justify-between mb-2">
                    <span>Subtotal:</span>
                    <span>₹{printData.bill.subtotal}</span>
                  </div>
                  {printData.bill.discount_amount > 0 && (
                    <div className="flex justify-between mb-2 text-green-600">
                      <span>Discount:</span>
                      <span>-₹{printData.bill.discount_amount}</span>
                    </div>
                  )}
                  <div className="flex justify-between text-lg font-bold border-t pt-2 mb-2">
                    <span>Total Amount:</span>
                    <span>₹{printData.bill.total_amount}</span>
                  </div>
                  <div className="flex justify-between text-green-600">
                    <span>Amount Paid:</span>
                    <span>₹{printData.bill.amount_paid}</span>
                  </div>
                  {printData.bill.balance_due > 0 && (
                    <div className="flex justify-between text-red-600 font-medium">
                      <span>Balance Due:</span>
                      <span>₹{printData.bill.balance_due}</span>
                    </div>
                  )}
                </div>

                {printData.payment_receipt && (
                  <div className="border-t mt-6 pt-4">
                    <h3 className="font-semibold mb-3">Payment Receipt</h3>
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <p><strong>Receipt No:</strong> {printData.payment_receipt.receipt_number}</p>
                      <p><strong>Payment Date:</strong> {new Date(printData.payment_receipt.payment_date).toLocaleDateString()}</p>
                      <p><strong>Amount:</strong> ₹{printData.payment_receipt.amount_paid}</p>
                      <p><strong>Method:</strong> {getPaymentMethodIcon(printData.payment_receipt.payment_method)} {printData.payment_receipt.payment_method.toUpperCase()}</p>
                    </div>
                  </div>
                )}

                <div className="text-center mt-8 text-sm text-gray-500">
                  <p>Thank you for choosing {printData.hospital_info.name}</p>
                  <p>Generated on {new Date().toLocaleString()}</p>
                </div>
              </div>

              <div className="flex gap-2">
                <Button variant="outline" onClick={() => setPrintDialogOpen(false)} className="flex-1">
                  Close
                </Button>
                <Button onClick={handlePrint} className="flex items-center gap-2 flex-1">
                  <Printer className="h-4 w-4" />
                  Print
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <style jsx>{`
        @media print {
          body * {
            visibility: hidden;
          }
          #bill-print, #bill-print * {
            visibility: visible;
          }
          #bill-print {
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
          }
        }
      `}</style>
    </>
  );
};

export default BillingManager;