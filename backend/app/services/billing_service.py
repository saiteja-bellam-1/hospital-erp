import uuid
from sqlalchemy.orm import Session
from app.models.billing import Bill, BillItem, Payment, PaymentMethod
from app.models.lab import PatientLabOrder, LabTest
from app.models.pharmacy import Prescription, PrescriptionItem
from app.models.ehr import Consultation
from app.models.outpatient import OutpatientVisit
from app.models.inpatient import Admission, RoomManagement
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from decimal import Decimal

class BillingService:
    def __init__(self, db: Session):
        self.db = db
    
    # Payment Method Management
    def create_payment_method(self, method_data: Dict[str, Any], hospital_id: int) -> PaymentMethod:
        payment_method = PaymentMethod(
            name=method_data["name"],
            description=method_data.get("description"),
            hospital_id=hospital_id
        )
        
        self.db.add(payment_method)
        self.db.commit()
        self.db.refresh(payment_method)
        return payment_method
    
    def get_payment_methods(self, hospital_id: int) -> List[PaymentMethod]:
        return self.db.query(PaymentMethod).filter(
            PaymentMethod.hospital_id == hospital_id,
            PaymentMethod.is_active == True
        ).all()
    
    # Bill Creation from Different Modules
    def create_consultation_bill(self, consultation_id: int, created_by_id: int) -> Bill:
        consultation = self.db.query(Consultation).filter(Consultation.id == consultation_id).first()
        if not consultation:
            raise ValueError("Consultation not found")
        
        bill_number = self._generate_bill_number("CONS")
        
        bill = Bill(
            bill_number=bill_number,
            patient_id=consultation.patient_id,
            bill_type="consultation",
            reference_id=consultation_id,
            subtotal=consultation.consultation_fee,
            total_amount=consultation.consultation_fee,
            created_by_id=created_by_id,
            hospital_id=consultation.patient.hospital_id
        )
        
        self.db.add(bill)
        self.db.commit()
        self.db.refresh(bill)
        
        # Add consultation item
        self._add_bill_item(
            bill.id,
            "consultation",
            f"Consultation with Dr. {consultation.doctor.first_name} {consultation.doctor.last_name}",
            "CONS",
            1,
            consultation.consultation_fee
        )
        
        return bill
    
    def create_lab_bill(self, lab_order_ids: List[int], created_by_id: int) -> Bill:
        if not lab_order_ids:
            raise ValueError("No lab orders provided")
        
        # Get lab orders
        lab_orders = self.db.query(PatientLabOrder).filter(
            PatientLabOrder.id.in_(lab_order_ids)
        ).all()
        
        if not lab_orders:
            raise ValueError("Lab orders not found")
        
        patient_id = lab_orders[0].patient_id
        hospital_id = lab_orders[0].patient.hospital_id
        
        # Verify all orders belong to same patient
        if not all(order.patient_id == patient_id for order in lab_orders):
            raise ValueError("All lab orders must belong to same patient")
        
        bill_number = self._generate_bill_number("LAB")
        subtotal = sum(order.test.cost for order in lab_orders)
        
        bill = Bill(
            bill_number=bill_number,
            patient_id=patient_id,
            bill_type="lab",
            subtotal=subtotal,
            total_amount=subtotal,
            created_by_id=created_by_id,
            hospital_id=hospital_id
        )
        
        self.db.add(bill)
        self.db.commit()
        self.db.refresh(bill)
        
        # Add lab test items
        for order in lab_orders:
            self._add_bill_item(
                bill.id,
                "lab_test",
                order.test.name,
                order.test.test_code,
                1,
                order.test.cost
            )
        
        return bill
    
    def create_pharmacy_bill(self, prescription_id: int, created_by_id: int) -> Bill:
        prescription = self.db.query(Prescription).filter(Prescription.id == prescription_id).first()
        if not prescription:
            raise ValueError("Prescription not found")
        
        bill_number = self._generate_bill_number("PHAR")
        
        bill = Bill(
            bill_number=bill_number,
            patient_id=prescription.patient_id,
            bill_type="pharmacy",
            reference_id=prescription_id,
            subtotal=prescription.total_amount,
            total_amount=prescription.total_amount,
            created_by_id=created_by_id,
            hospital_id=prescription.patient.hospital_id
        )
        
        self.db.add(bill)
        self.db.commit()
        self.db.refresh(bill)
        
        # Add prescription items
        for item in prescription.items:
            self._add_bill_item(
                bill.id,
                "medicine",
                item.medicine.name,
                item.medicine.medicine_code,
                item.quantity_dispensed or item.quantity_prescribed,
                item.unit_price
            )
        
        return bill
    
    def create_admission_bill(self, admission_id: int, created_by_id: int, additional_charges: List[Dict[str, Any]] = None) -> Bill:
        admission = self.db.query(Admission).filter(Admission.id == admission_id).first()
        if not admission:
            raise ValueError("Admission not found")
        
        bill_number = self._generate_bill_number("ADM")
        
        # Calculate room charges
        if admission.discharge:
            days_stayed = admission.discharge.total_stay_days
        else:
            days_stayed = (datetime.now() - admission.admission_date).days + 1
        
        room_charge_per_day = admission.room.room_charge_per_day
        room_total = days_stayed * room_charge_per_day
        
        subtotal = room_total
        
        bill = Bill(
            bill_number=bill_number,
            patient_id=admission.patient_id,
            bill_type="admission",
            reference_id=admission_id,
            subtotal=subtotal,
            total_amount=subtotal,
            created_by_id=created_by_id,
            hospital_id=admission.patient.hospital_id
        )
        
        self.db.add(bill)
        self.db.commit()
        self.db.refresh(bill)
        
        # Add room charge item
        self._add_bill_item(
            bill.id,
            "room_charge",
            f"Room {admission.room.room_number} - {admission.room.room_type}",
            f"ROOM-{admission.room.room_number}",
            days_stayed,
            room_charge_per_day
        )
        
        # Add additional charges if provided
        if additional_charges:
            for charge in additional_charges:
                self._add_bill_item(
                    bill.id,
                    charge["item_type"],
                    charge["item_name"],
                    charge.get("item_code", ""),
                    charge.get("quantity", 1),
                    charge["unit_price"]
                )
        
        return bill
    
    def create_consolidated_bill(self, patient_id: int, created_by_id: int, bill_types: List[str] = None) -> Bill:
        """Create a consolidated bill combining multiple services for a patient"""
        patient = self.db.query(Patient).filter(Patient.id == patient_id).first()
        if not patient:
            raise ValueError("Patient not found")
        
        bill_number = self._generate_bill_number("CONS")
        subtotal = 0
        
        bill = Bill(
            bill_number=bill_number,
            patient_id=patient_id,
            bill_type="consolidated",
            subtotal=0,
            total_amount=0,
            created_by_id=created_by_id,
            hospital_id=patient.hospital_id
        )
        
        self.db.add(bill)
        self.db.commit()
        self.db.refresh(bill)
        
        # Add consultations
        if not bill_types or "consultation" in bill_types:
            consultations = self.db.query(Consultation).filter(
                Consultation.patient_id == patient_id,
                Consultation.status == "completed"
            ).all()
            
            for consultation in consultations:
                if consultation.consultation_fee > 0:
                    self._add_bill_item(
                        bill.id,
                        "consultation",
                        f"Consultation - {consultation.consultation_date.strftime('%Y-%m-%d')}",
                        f"CONS-{consultation.id}",
                        1,
                        consultation.consultation_fee
                    )
                    subtotal += consultation.consultation_fee
        
        # Add lab tests
        if not bill_types or "lab" in bill_types:
            lab_orders = self.db.query(PatientLabOrder).filter(
                PatientLabOrder.patient_id == patient_id,
                PatientLabOrder.status == "completed"
            ).all()
            
            for order in lab_orders:
                self._add_bill_item(
                    bill.id,
                    "lab_test",
                    order.test.name,
                    order.test.test_code,
                    1,
                    order.test.cost
                )
                subtotal += order.test.cost
        
        # Add pharmacy items
        if not bill_types or "pharmacy" in bill_types:
            prescriptions = self.db.query(Prescription).filter(
                Prescription.patient_id == patient_id,
                Prescription.status.in_(["dispensed", "partial"])
            ).all()
            
            for prescription in prescriptions:
                for item in prescription.items:
                    if item.quantity_dispensed > 0:
                        dispensed_amount = item.quantity_dispensed * item.unit_price
                        self._add_bill_item(
                            bill.id,
                            "medicine",
                            item.medicine.name,
                            item.medicine.medicine_code,
                            item.quantity_dispensed,
                            item.unit_price
                        )
                        subtotal += dispensed_amount
        
        # Update bill totals
        bill.subtotal = subtotal
        bill.total_amount = subtotal
        self.db.commit()
        self.db.refresh(bill)
        
        return bill
    
    def _generate_bill_number(self, prefix: str) -> str:
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        return f"{prefix}{timestamp}"
    
    def _add_bill_item(self, bill_id: int, item_type: str, item_name: str, item_code: str, quantity: int, unit_price: float):
        total_price = quantity * unit_price
        
        bill_item = BillItem(
            bill_id=bill_id,
            item_type=item_type,
            item_name=item_name,
            item_code=item_code,
            quantity=quantity,
            unit_price=unit_price,
            total_price=total_price
        )
        
        self.db.add(bill_item)
        self.db.commit()
    
    # Bill Management
    def get_bills(self, hospital_id: int, status: Optional[str] = None, patient_id: Optional[int] = None) -> List[Bill]:
        query = self.db.query(Bill).filter(Bill.hospital_id == hospital_id)
        
        if status:
            query = query.filter(Bill.status == status)
        
        if patient_id:
            query = query.filter(Bill.patient_id == patient_id)
        
        return query.order_by(Bill.bill_date.desc()).all()
    
    def get_bill_by_id(self, bill_id: int) -> Optional[Bill]:
        return self.db.query(Bill).filter(Bill.id == bill_id).first()
    
    def apply_discount(self, bill_id: int, discount_amount: float, discount_percentage: float = None) -> Optional[Bill]:
        bill = self.get_bill_by_id(bill_id)
        if not bill:
            return None
        
        if discount_percentage:
            discount_amount = bill.subtotal * (discount_percentage / 100)
        
        bill.discount_amount = discount_amount
        bill.total_amount = bill.subtotal + bill.tax_amount - bill.discount_amount
        
        self.db.commit()
        self.db.refresh(bill)
        return bill
    
    def apply_tax(self, bill_id: int, tax_percentage: float) -> Optional[Bill]:
        bill = self.get_bill_by_id(bill_id)
        if not bill:
            return None
        
        bill.tax_amount = (bill.subtotal - bill.discount_amount) * (tax_percentage / 100)
        bill.total_amount = bill.subtotal + bill.tax_amount - bill.discount_amount
        
        self.db.commit()
        self.db.refresh(bill)
        return bill
    
    # Payment Processing
    def record_payment(self, payment_data: Dict[str, Any]) -> Payment:
        payment_number = f"PAY{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        payment = Payment(
            payment_number=payment_number,
            bill_id=payment_data["bill_id"],
            amount_paid=payment_data["amount_paid"],
            payment_method_id=payment_data["payment_method_id"],
            transaction_reference=payment_data.get("transaction_reference"),
            notes=payment_data.get("notes"),
            received_by_id=payment_data["received_by_id"]
        )
        
        self.db.add(payment)
        self.db.commit()
        self.db.refresh(payment)
        
        # Update bill status
        self._update_bill_payment_status(payment_data["bill_id"])
        
        return payment
    
    def _update_bill_payment_status(self, bill_id: int):
        bill = self.get_bill_by_id(bill_id)
        if not bill:
            return
        
        total_paid = self.db.query(Payment).filter(
            Payment.bill_id == bill_id
        ).with_entities(
            self.db.func.sum(Payment.amount_paid)
        ).scalar() or 0
        
        if total_paid >= bill.total_amount:
            bill.status = "paid"
        elif total_paid > 0:
            bill.status = "partial"
        else:
            bill.status = "pending"
        
        self.db.commit()
    
    def get_pending_bills(self, hospital_id: int) -> List[Bill]:
        return self.db.query(Bill).filter(
            Bill.hospital_id == hospital_id,
            Bill.status.in_(["pending", "partial"])
        ).order_by(Bill.bill_date.desc()).all()
    
    def get_overdue_bills(self, hospital_id: int, days_overdue: int = 30) -> List[Bill]:
        cutoff_date = datetime.now() - timedelta(days=days_overdue)
        
        return self.db.query(Bill).filter(
            Bill.hospital_id == hospital_id,
            Bill.status.in_(["pending", "partial"]),
            Bill.due_date < cutoff_date
        ).order_by(Bill.due_date).all()
    
    # Reports and Analytics
    def get_billing_statistics(self, hospital_id: int) -> Dict[str, Any]:
        total_bills = self.db.query(Bill).filter(Bill.hospital_id == hospital_id).count()
        
        pending_bills = self.db.query(Bill).filter(
            Bill.hospital_id == hospital_id,
            Bill.status.in_(["pending", "partial"])
        ).count()
        
        total_revenue = self.db.query(Payment).join(Payment.bill).filter(
            Bill.hospital_id == hospital_id
        ).with_entities(
            self.db.func.sum(Payment.amount_paid)
        ).scalar() or 0
        
        outstanding_amount = self.db.query(Bill).filter(
            Bill.hospital_id == hospital_id,
            Bill.status.in_(["pending", "partial"])
        ).with_entities(
            self.db.func.sum(Bill.total_amount)
        ).scalar() or 0
        
        # Revenue by bill type
        revenue_by_type = {}
        bill_types = ["consultation", "lab", "pharmacy", "admission"]
        for bill_type in bill_types:
            type_revenue = self.db.query(Payment).join(Payment.bill).filter(
                Bill.hospital_id == hospital_id,
                Bill.bill_type == bill_type
            ).with_entities(
                self.db.func.sum(Payment.amount_paid)
            ).scalar() or 0
            revenue_by_type[bill_type] = float(type_revenue)
        
        return {
            "total_bills": total_bills,
            "pending_bills": pending_bills,
            "total_revenue": float(total_revenue),
            "outstanding_amount": float(outstanding_amount),
            "revenue_by_type": revenue_by_type
        }
    
    def get_daily_revenue_report(self, hospital_id: int, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        daily_revenue = self.db.query(
            self.db.func.date(Payment.payment_date).label('payment_date'),
            self.db.func.sum(Payment.amount_paid).label('total_amount'),
            self.db.func.count(Payment.id).label('payment_count')
        ).join(Payment.bill).filter(
            Bill.hospital_id == hospital_id,
            Payment.payment_date >= start_date,
            Payment.payment_date <= end_date
        ).group_by(
            self.db.func.date(Payment.payment_date)
        ).all()
        
        return [
            {
                "date": str(record.payment_date),
                "total_amount": float(record.total_amount),
                "payment_count": record.payment_count
            }
            for record in daily_revenue
        ]