import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '../ui/dialog';
import { 
  Stethoscope, 
  FlaskConical, 
  Receipt, 
  Eye,
  Calendar,
  User,
  FileText
} from 'lucide-react';
import DoctorConsultation from './DoctorConsultation';
import BillingManager from '../billing/BillingManager';

const ConsultationCard = ({ consultation, userRole = 'doctor' }) => {
  const [showDetails, setShowDetails] = useState(false);
  const [showBilling, setShowBilling] = useState(false);

  const getStatusColor = (status) => {
    switch (status) {
      case 'ongoing': return 'bg-blue-100 text-blue-800';
      case 'completed': return 'bg-green-100 text-green-800';
      case 'cancelled': return 'bg-red-100 text-red-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const getConsultationType = (type) => {
    return type === 'outpatient' ? 'OPD' : type.toUpperCase();
  };

  return (
    <>
      <Card className="hover:shadow-md transition-shadow">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <CardTitle className="flex items-center gap-2 text-lg">
                <Stethoscope className="h-4 w-4" />
                {consultation.patient_name || 'Unknown Patient'}
              </CardTitle>
              <p className="text-sm text-gray-600 flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                {new Date(consultation.consultation_date).toLocaleDateString()}
              </p>
            </div>
            <div className="flex flex-col items-end gap-2">
              <Badge className={getStatusColor(consultation.status)}>
                {consultation.status}
              </Badge>
              <Badge variant="outline">
                {getConsultationType(consultation.consultation_type)}
              </Badge>
            </div>
          </div>
        </CardHeader>
        
        <CardContent className="space-y-4">
          <div className="space-y-2">
            {consultation.chief_complaint && (
              <div>
                <p className="text-sm font-medium text-gray-700">Chief Complaint:</p>
                <p className="text-sm text-gray-600">{consultation.chief_complaint}</p>
              </div>
            )}
            
            {consultation.doctor_name && (
              <p className="text-sm text-gray-600 flex items-center gap-1">
                <User className="h-3 w-3" />
                Dr. {consultation.doctor_name}
              </p>
            )}
            
            {consultation.consultation_fee && (
              <p className="text-sm font-semibold text-green-600">
                Consultation Fee: ₹{consultation.consultation_fee}
              </p>
            )}
          </div>

          <div className="flex gap-2 pt-2 border-t">
            {userRole === 'doctor' && (
              <Dialog open={showDetails} onOpenChange={setShowDetails}>
                <DialogTrigger asChild>
                  <Button variant="outline" size="sm" className="flex items-center gap-1 flex-1">
                    <Eye className="h-3 w-3" />
                    View Details
                  </Button>
                </DialogTrigger>
                <DialogContent className="max-w-6xl h-[90vh]">
                  <DialogHeader>
                    <DialogTitle>Consultation Details</DialogTitle>
                  </DialogHeader>
                  <div className="overflow-y-auto">
                    <DoctorConsultation 
                      consultation={{
                        id: consultation.id,
                        patient_name: consultation.patient_name,
                        chief_complaint: consultation.chief_complaint,
                        present_history: consultation.present_history,
                        consultation_type: consultation.consultation_type,
                        consultation_fee: consultation.consultation_fee,
                        status: consultation.status
                      }}
                    />
                  </div>
                </DialogContent>
              </Dialog>
            )}

            {(userRole === 'receptionist' || userRole === 'hospital_admin') && (
              <Dialog open={showBilling} onOpenChange={setShowBilling}>
                <DialogTrigger asChild>
                  <Button variant="outline" size="sm" className="flex items-center gap-1 flex-1">
                    <Receipt className="h-3 w-3" />
                    Billing
                  </Button>
                </DialogTrigger>
                <DialogContent className="max-w-4xl">
                  <DialogHeader>
                    <DialogTitle>Billing Management</DialogTitle>
                  </DialogHeader>
                  <BillingManager 
                    consultation={{
                      id: consultation.id,
                      patient_name: consultation.patient_name,
                      doctor_name: consultation.doctor_name
                    }}
                    onPaymentUpdate={(payment) => {
                      console.log('Payment processed:', payment);
                      // Could trigger a refresh of consultation data
                    }}
                  />
                </DialogContent>
              </Dialog>
            )}

            {userRole === 'doctor' && (
              <Button variant="outline" size="sm" className="flex items-center gap-1">
                <FileText className="h-3 w-3" />
                Notes
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </>
  );
};

export default ConsultationCard;