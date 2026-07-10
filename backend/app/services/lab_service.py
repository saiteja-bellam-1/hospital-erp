import uuid
from sqlalchemy.orm import Session
from app.models.lab import LabTest, LabTestCategory, LabReport, LabReportTemplate, PatientLabOrder
from app.models.billing import Bill, BillItem
from typing import Optional, List, Dict, Any
from datetime import datetime
import pandas as pd
import json

class LabService:
    def __init__(self, db: Session):
        self.db = db
    
    # Category Management
    def create_test_category(self, category_data: Dict[str, Any], hospital_id: int) -> LabTestCategory:
        category = LabTestCategory(
            name=category_data["name"],
            description=category_data.get("description"),
            hospital_id=hospital_id
        )
        
        self.db.add(category)
        self.db.commit()
        self.db.refresh(category)
        return category
    
    def get_categories(self, hospital_id: int) -> List[LabTestCategory]:
        return self.db.query(LabTestCategory).filter(
            LabTestCategory.hospital_id == hospital_id,
            LabTestCategory.is_active == True
        ).all()
    
    # Lab Test Management
    def create_lab_test(self, test_data: Dict[str, Any], hospital_id: int) -> LabTest:
        test = LabTest(
            test_code=test_data["test_code"],
            name=test_data["name"],
            description=test_data.get("description"),
            category_id=test_data["category_id"],
            cost=test_data["cost"],
            sample_type=test_data.get("sample_type"),
            preparation_instructions=test_data.get("preparation_instructions"),
            normal_range=test_data.get("normal_range"),
            unit=test_data.get("unit"),
            hospital_id=hospital_id
        )
        
        self.db.add(test)
        self.db.commit()
        self.db.refresh(test)
        return test
    
    def get_lab_tests(self, hospital_id: int, category_id: Optional[int] = None) -> List[LabTest]:
        query = self.db.query(LabTest).filter(
            LabTest.hospital_id == hospital_id,
            LabTest.is_active == True
        )
        
        if category_id:
            query = query.filter(LabTest.category_id == category_id)
        
        return query.all()
    
    def update_lab_test(self, test_id: int, test_data: Dict[str, Any]) -> Optional[LabTest]:
        test = self.db.query(LabTest).filter(LabTest.id == test_id).first()
        if not test:
            return None
        
        for key, value in test_data.items():
            if hasattr(test, key):
                setattr(test, key, value)
        
        self.db.commit()
        self.db.refresh(test)
        return test
    
    # Report Template Management
    def create_report_template(self, template_data: Dict[str, Any], hospital_id: int) -> LabReportTemplate:
        template = LabReportTemplate(
            name=template_data["name"],
            test_id=template_data["test_id"],
            template_fields=template_data["template_fields"],
            hospital_id=hospital_id
        )
        
        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)
        return template
    
    def get_report_templates(self, hospital_id: int) -> List[LabReportTemplate]:
        return self.db.query(LabReportTemplate).filter(
            LabReportTemplate.hospital_id == hospital_id,
            LabReportTemplate.is_active == True
        ).all()
    
    # Lab Order Management
    def create_lab_order(self, order_data: Dict[str, Any]) -> PatientLabOrder:
        order_number = f"LAB{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        order = PatientLabOrder(
            order_number=order_number,
            patient_id=order_data["patient_id"],
            test_id=order_data["test_id"],
            doctor_id=order_data.get("doctor_id"),
            priority=order_data.get("priority", "normal"),
            notes=order_data.get("notes")
        )
        
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order
    
    def update_order_status(self, order_id: int, status: str, notes: Optional[str] = None) -> Optional[PatientLabOrder]:
        order = self.db.query(PatientLabOrder).filter(PatientLabOrder.id == order_id).first()
        if not order:
            return None
        
        order.status = status
        if notes:
            order.notes = notes
        
        if status == "collected":
            order.collection_date = datetime.now()
        elif status == "completed":
            order.completion_date = datetime.now()
        
        self.db.commit()
        self.db.refresh(order)
        return order
    
    def get_lab_orders(self, hospital_id: int, status: Optional[str] = None) -> List[PatientLabOrder]:
        # Join with patient to filter by hospital
        query = self.db.query(PatientLabOrder).join(PatientLabOrder.patient).filter(
            PatientLabOrder.patient.has(hospital_id=hospital_id)
        )
        
        if status:
            query = query.filter(PatientLabOrder.status == status)
        
        return query.all()
    
    # Lab Report Management
    def create_lab_report(self, report_data: Dict[str, Any]) -> LabReport:
        report = LabReport(
            order_id=report_data["order_id"],
            template_id=report_data.get("template_id"),
            result_values=report_data["result_values"],
            interpretation=report_data.get("interpretation"),
            technician_id=report_data["technician_id"]
        )
        
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        
        # Update order status to completed
        self.update_order_status(report_data["order_id"], "completed")
        
        return report
    
    def verify_report(self, report_id: int, verified_by_id: int) -> Optional[LabReport]:
        report = self.db.query(LabReport).filter(LabReport.id == report_id).first()
        if not report:
            return None
        
        report.is_verified = True
        report.verified_by_id = verified_by_id
        report.verification_date = datetime.now()
        
        self.db.commit()
        self.db.refresh(report)
        return report
    
    def get_patient_reports(self, patient_id: int) -> List[LabReport]:
        return self.db.query(LabReport).join(LabReport.order).filter(
            PatientLabOrder.patient_id == patient_id
        ).all()
    
    # Import/Export Functionality
    def export_lab_tests(self, hospital_id: int) -> List[Dict[str, Any]]:
        tests = self.get_lab_tests(hospital_id)
        export_data = []
        
        for test in tests:
            test_data = {
                "test_code": test.test_code,
                "name": test.name,
                "description": test.description,
                "category_name": test.category.name,
                "cost": test.cost,
                "sample_type": test.sample_type,
                "preparation_instructions": test.preparation_instructions,
                "normal_range": test.normal_range,
                "unit": test.unit
            }
            export_data.append(test_data)
        
        return export_data
    
    def import_lab_tests(self, import_data: List[Dict[str, Any]], hospital_id: int) -> Dict[str, Any]:
        results = {"successful": 0, "errors": []}
        
        for test_data in import_data:
            try:
                # Find or create category
                category_name = test_data.get("category_name")
                if category_name:
                    category = self.db.query(LabTestCategory).filter(
                        LabTestCategory.name == category_name,
                        LabTestCategory.hospital_id == hospital_id
                    ).first()
                    
                    if not category:
                        category = self.create_test_category(
                            {"name": category_name},
                            hospital_id
                        )
                    
                    test_data["category_id"] = category.id
                    del test_data["category_name"]
                
                self.create_lab_test(test_data, hospital_id)
                results["successful"] += 1
                
            except Exception as e:
                results["errors"].append(f"Error importing {test_data.get('name', 'Unknown')}: {str(e)}")
        
        return results
    
    def export_to_excel(self, hospital_id: int) -> bytes:
        tests_data = self.export_lab_tests(hospital_id)
        categories_data = [
            {"name": cat.name, "description": cat.description}
            for cat in self.get_categories(hospital_id)
        ]
        
        # Create Excel file
        with pd.ExcelWriter("lab_configuration.xlsx", engine='openpyxl') as writer:
            pd.DataFrame(tests_data).to_excel(writer, sheet_name='Lab Tests', index=False)
            pd.DataFrame(categories_data).to_excel(writer, sheet_name='Categories', index=False)
        
        with open("lab_configuration.xlsx", "rb") as f:
            return f.read()
    
    def get_lab_statistics(self, hospital_id: int) -> Dict[str, Any]:
        total_tests = self.db.query(LabTest).filter(
            LabTest.hospital_id == hospital_id,
            LabTest.is_active == True
        ).count()
        
        total_orders = self.db.query(PatientLabOrder).join(PatientLabOrder.patient).filter(
            PatientLabOrder.patient.has(hospital_id=hospital_id)
        ).count()
        
        pending_orders = self.db.query(PatientLabOrder).join(PatientLabOrder.patient).filter(
            PatientLabOrder.patient.has(hospital_id=hospital_id),
            PatientLabOrder.status.in_(["ordered", "collected", "processing"])
        ).count()
        
        completed_orders = self.db.query(PatientLabOrder).join(PatientLabOrder.patient).filter(
            PatientLabOrder.patient.has(hospital_id=hospital_id),
            PatientLabOrder.status == "completed"
        ).count()
        
        return {
            "total_tests": total_tests,
            "total_orders": total_orders,
            "pending_orders": pending_orders,
            "completed_orders": completed_orders
        }