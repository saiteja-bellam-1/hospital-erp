import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Textarea } from '../ui/textarea';
import { Badge } from '../ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { 
  Plus, 
  FlaskConical, 
  Receipt, 
  Stethoscope, 
  ClipboardCheck,
  AlertCircle,
  CheckCircle,
  Printer
} from 'lucide-react';

const DoctorConsultation = ({ consultation, onUpdate }) => {
  const [activeTab, setActiveTab] = useState('consultation');
  const [labRecommendations, setLabRecommendations] = useState([]);
  const [selectedTests, setSelectedTests] = useState([]);
  const [labOrders, setLabOrders] = useState([]);
  const [bill, setBill] = useState(null);
  const [availableTests, setAvailableTests] = useState([]);
  const [loading, setLoading] = useState(false);

  // Load initial data
  useEffect(() => {
    if (consultation?.id) {
      fetchLabRecommendations();
      fetchAvailableTests();
      fetchExistingLabOrders();
      fetchBill();
    }
  }, [consultation?.id]);

  const fetchLabRecommendations = async () => {
    try {
      const token = localStorage.getItem('auth_token');
      const response = await fetch(`/api/consultations/${consultation.id}/test-recommendations`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        setLabRecommendations(data.recommendations);
      }
    } catch (error) {
      console.error('Error fetching lab recommendations:', error);
    }
  };

  const fetchAvailableTests = async () => {
    try {
      const token = localStorage.getItem('auth_token');
      const response = await fetch(`/api/consultations/${consultation.id}/available-tests`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        setAvailableTests(data);
      }
    } catch (error) {
      console.error('Error fetching available tests:', error);
    }
  };

  const fetchExistingLabOrders = async () => {
    try {
      const token = localStorage.getItem('auth_token');
      const response = await fetch(`/api/consultations/${consultation.id}/lab-orders`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        setLabOrders(data.lab_orders);
      }
    } catch (error) {
      console.error('Error fetching lab orders:', error);
    }
  };

  const fetchBill = async () => {
    try {
      const token = localStorage.getItem('auth_token');
      const response = await fetch(`/api/consultations/${consultation.id}/bill`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        setBill(data);
      }
    } catch (error) {
      // Bill might not exist yet
      console.log('No bill found yet');
    }
  };

  const handleOrderLabTests = async () => {
    if (selectedTests.length === 0) return;

    setLoading(true);
    try {
      const token = localStorage.getItem('auth_token');
      const response = await fetch(`/api/consultations/${consultation.id}/lab-orders`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          test_ids: selectedTests,
          priority: 'normal',
          notes: 'Ordered during consultation'
        })
      });

      if (response.ok) {
        setSelectedTests([]);
        fetchExistingLabOrders();
        // Auto-generate updated bill
        generateBill();
      }
    } catch (error) {
      console.error('Error ordering lab tests:', error);
    } finally {
      setLoading(false);
    }
  };

  const generateBill = async () => {
    try {
      const token = localStorage.getItem('auth_token');
      const response = await fetch(`/api/consultations/${consultation.id}/generate-bill`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        setBill(data);
      }
    } catch (error) {
      console.error('Error generating bill:', error);
    }
  };

  const getConfidenceColor = (score) => {
    if (score >= 80) return 'bg-green-100 text-green-800';
    if (score >= 60) return 'bg-yellow-100 text-yellow-800';
    return 'bg-red-100 text-red-800';
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'ordered': return 'bg-blue-100 text-blue-800';
      case 'collected': return 'bg-yellow-100 text-yellow-800';
      case 'processing': return 'bg-orange-100 text-orange-800';
      case 'completed': return 'bg-green-100 text-green-800';
      case 'cancelled': return 'bg-red-100 text-red-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <Card className="w-full max-w-6xl mx-auto">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Stethoscope className="h-5 w-5" />
          Doctor Consultation - {consultation?.patient_name}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="consultation" className="flex items-center gap-2">
              <Stethoscope className="h-4 w-4" />
              Consultation
            </TabsTrigger>
            <TabsTrigger value="lab-orders" className="flex items-center gap-2">
              <FlaskConical className="h-4 w-4" />
              Lab Orders
            </TabsTrigger>
            <TabsTrigger value="recommendations" className="flex items-center gap-2">
              <ClipboardCheck className="h-4 w-4" />
              Recommendations
            </TabsTrigger>
            <TabsTrigger value="billing" className="flex items-center gap-2">
              <Receipt className="h-4 w-4" />
              Billing
            </TabsTrigger>
          </TabsList>

          <TabsContent value="consultation" className="mt-6">
            <Card>
              <CardHeader>
                <CardTitle>Consultation Details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label>Chief Complaint</Label>
                    <p className="text-sm text-gray-600 mt-1">
                      {consultation?.chief_complaint || 'Not recorded'}
                    </p>
                  </div>
                  <div>
                    <Label>Consultation Type</Label>
                    <Badge variant="outline" className="mt-1">
                      {consultation?.consultation_type || 'outpatient'}
                    </Badge>
                  </div>
                </div>
                <div>
                  <Label>Present History</Label>
                  <p className="text-sm text-gray-600 mt-1">
                    {consultation?.present_history || 'Not recorded'}
                  </p>
                </div>
                <div>
                  <Label>Consultation Fee</Label>
                  <p className="text-lg font-semibold text-green-600 mt-1">
                    ₹{consultation?.consultation_fee || '0'}
                  </p>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="lab-orders" className="mt-6">
            <div className="space-y-6">
              {/* Order New Tests */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Plus className="h-4 w-4" />
                    Order New Lab Tests
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div className="max-h-60 overflow-y-auto space-y-2">
                      {availableTests.map((test) => (
                        <div
                          key={test.id}
                          className={`p-3 border rounded-lg cursor-pointer transition-colors ${
                            selectedTests.includes(test.id)
                              ? 'border-blue-500 bg-blue-50'
                              : 'border-gray-200 hover:border-gray-300'
                          }`}
                          onClick={() => {
                            if (selectedTests.includes(test.id)) {
                              setSelectedTests(selectedTests.filter(id => id !== test.id));
                            } else {
                              setSelectedTests([...selectedTests, test.id]);
                            }
                          }}
                        >
                          <div className="flex justify-between items-center">
                            <div>
                              <h4 className="font-medium">{test.name}</h4>
                              <p className="text-sm text-gray-600">
                                Code: {test.test_code} • Sample: {test.sample_type}
                              </p>
                              {test.preparation_instructions && (
                                <p className="text-xs text-amber-600 mt-1">
                                  {test.preparation_instructions}
                                </p>
                              )}
                            </div>
                            <div className="text-right">
                              <p className="font-semibold text-green-600">₹{test.cost}</p>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                    {selectedTests.length > 0 && (
                      <div className="flex justify-between items-center pt-4 border-t">
                        <p className="text-sm text-gray-600">
                          {selectedTests.length} test(s) selected
                        </p>
                        <Button
                          onClick={handleOrderLabTests}
                          disabled={loading}
                          className="flex items-center gap-2"
                        >
                          <FlaskConical className="h-4 w-4" />
                          {loading ? 'Ordering...' : 'Order Selected Tests'}
                        </Button>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>

              {/* Existing Orders */}
              {labOrders.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle>Existing Lab Orders</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      {labOrders.map((order) => (
                        <div key={order.id} className="flex justify-between items-center p-3 border rounded-lg">
                          <div>
                            <h4 className="font-medium">{order.test_name}</h4>
                            <p className="text-sm text-gray-600">
                              Order: {order.order_number} • Priority: {order.priority}
                            </p>
                            {order.notes && (
                              <p className="text-xs text-gray-500 mt-1">{order.notes}</p>
                            )}
                          </div>
                          <div className="text-right">
                            <Badge className={getStatusColor(order.status)}>
                              {order.status}
                            </Badge>
                            <p className="text-sm text-green-600 mt-1">₹{order.test_cost}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          </TabsContent>

          <TabsContent value="recommendations" className="mt-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ClipboardCheck className="h-4 w-4" />
                  AI Test Recommendations
                </CardTitle>
                <p className="text-sm text-gray-600">
                  Based on symptoms: {consultation?.chief_complaint}
                </p>
              </CardHeader>
              <CardContent>
                {labRecommendations.length > 0 ? (
                  <div className="space-y-3">
                    {labRecommendations.map((rec) => (
                      <div key={rec.test_id} className="p-4 border rounded-lg">
                        <div className="flex justify-between items-start">
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-2">
                              <h4 className="font-medium">{rec.test_name}</h4>
                              <Badge className={getConfidenceColor(rec.confidence_score)}>
                                {rec.confidence_score}% confidence
                              </Badge>
                            </div>
                            <p className="text-sm text-gray-600 mb-2">
                              {rec.recommendation_reason}
                            </p>
                            <p className="text-xs text-gray-500">
                              Category: {rec.category_name} • Code: {rec.test_code}
                            </p>
                          </div>
                          <div className="text-right ml-4">
                            <p className="font-semibold text-green-600">₹{rec.cost}</p>
                            <Button
                              size="sm"
                              variant="outline"
                              className="mt-2"
                              onClick={() => {
                                if (!selectedTests.includes(rec.test_id)) {
                                  setSelectedTests([...selectedTests, rec.test_id]);
                                  setActiveTab('lab-orders');
                                }
                              }}
                              disabled={selectedTests.includes(rec.test_id)}
                            >
                              {selectedTests.includes(rec.test_id) ? 'Selected' : 'Add to Order'}
                            </Button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-8">
                    <AlertCircle className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                    <p className="text-gray-500">No recommendations available</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="billing" className="mt-6">
            <div className="space-y-6">
              {bill ? (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center justify-between">
                      <span>Bill Summary</span>
                      <Badge className={bill.status === 'paid' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'}>
                        {bill.status.toUpperCase()}
                      </Badge>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-4">
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <Label>Bill Number</Label>
                          <p className="font-mono text-sm">{bill.bill_number}</p>
                        </div>
                        <div>
                          <Label>Date</Label>
                          <p className="text-sm">{new Date(bill.bill_date).toLocaleDateString()}</p>
                        </div>
                      </div>

                      <div className="space-y-2">
                        <Label>Bill Items</Label>
                        <div className="border rounded-lg overflow-hidden">
                          <table className="w-full text-sm">
                            <thead className="bg-gray-50">
                              <tr>
                                <th className="text-left p-3">Item</th>
                                <th className="text-right p-3">Qty</th>
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
                                  <td className="text-right p-3">{item.quantity}</td>
                                  <td className="text-right p-3">₹{item.unit_price}</td>
                                  <td className="text-right p-3 font-medium">₹{item.total_price}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>

                      <div className="space-y-2 border-t pt-4">
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
                        <div className="flex justify-between text-green-600">
                          <span>Amount Paid:</span>
                          <span>₹{bill.amount_paid}</span>
                        </div>
                        {bill.balance_due > 0 && (
                          <div className="flex justify-between text-red-600 font-medium">
                            <span>Balance Due:</span>
                            <span>₹{bill.balance_due}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ) : (
                <Card>
                  <CardContent className="text-center py-8">
                    <Receipt className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                    <p className="text-gray-500 mb-4">No bill generated yet</p>
                    <Button onClick={generateBill} className="flex items-center gap-2">
                      <Receipt className="h-4 w-4" />
                      Generate Bill
                    </Button>
                  </CardContent>
                </Card>
              )}
            </div>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
};

export default DoctorConsultation;