#!/usr/bin/env python3

import sys
import os
sys.path.insert(0, '/Users/saiteja/Documents/GitHub/hospital-ERP')
sys.path.insert(0, '/Users/saiteja/Documents/GitHub/hospital-ERP/backend')

from config.database import SessionLocal
from app.models.ehr import Consultation
from app.models.lab import LabTest, LabTestCategory
from app.models.patient import Patient
from app.models.user import User
import uuid
from datetime import datetime

def setup_consultation_test_data():
    """Create sample consultations and lab tests for testing"""
    
    db = SessionLocal()
    
    try:
        print("🔧 Setting up consultation test data...")
        
        # Get a patient and doctor for testing
        patient = db.query(Patient).first()
        doctor = db.query(User).join(User.role).filter(User.role.has(name='doctor')).first()
        
        if not patient:
            print("❌ No patients found. Please create patients first.")
            return
            
        if not doctor:
            print("❌ No doctors found. Please create doctors first.")
            return
            
        print(f"📋 Using Patient ID: {patient.id} ({patient.first_name} {patient.last_name})")
        print(f"👨‍⚕️ Using Doctor ID: {doctor.id} ({doctor.first_name} {doctor.last_name})")
        
        # Create lab test categories if they don't exist
        categories = [
            ("Blood Tests", "Basic blood analysis tests"),
            ("Urine Tests", "Urine analysis and microscopy"),
            ("Imaging", "Radiology and imaging tests"),
            ("Biochemistry", "Blood chemistry and metabolic tests")
        ]
        
        for cat_name, cat_desc in categories:
            existing_cat = db.query(LabTestCategory).filter(
                LabTestCategory.name == cat_name,
                LabTestCategory.hospital_id == doctor.hospital_id
            ).first()
            
            if not existing_cat:
                category = LabTestCategory(
                    name=cat_name,
                    description=cat_desc,
                    hospital_id=doctor.hospital_id
                )
                db.add(category)
                print(f"✅ Created category: {cat_name}")
            else:
                print(f"✅ Category already exists: {cat_name}")
        
        db.flush()  # Get category IDs
        
        # Get category IDs
        blood_cat = db.query(LabTestCategory).filter(
            LabTestCategory.name == "Blood Tests",
            LabTestCategory.hospital_id == doctor.hospital_id
        ).first()
        
        biochem_cat = db.query(LabTestCategory).filter(
            LabTestCategory.name == "Biochemistry",
            LabTestCategory.hospital_id == doctor.hospital_id
        ).first()
        
        # Create sample lab tests
        lab_tests = [
            ("CBC", "Complete Blood Count", "CBC001", blood_cat.id, 150.0, "Blood", "Fasting not required"),
            ("ESR", "Erythrocyte Sedimentation Rate", "ESR001", blood_cat.id, 100.0, "Blood", "Fasting not required"),
            ("FBS", "Fasting Blood Sugar", "FBS001", biochem_cat.id, 120.0, "Blood", "12 hours fasting required"),
            ("RBS", "Random Blood Sugar", "RBS001", biochem_cat.id, 100.0, "Blood", "No fasting required"),
            ("HbA1c", "Glycated Hemoglobin", "HBA1C", biochem_cat.id, 300.0, "Blood", "No fasting required"),
            ("Lipid Profile", "Complete Lipid Panel", "LIPID001", biochem_cat.id, 400.0, "Blood", "12 hours fasting required")
        ]
        
        for test_name, test_desc, test_code, cat_id, cost, sample_type, prep_instructions in lab_tests:
            existing_test = db.query(LabTest).filter(
                LabTest.test_code == test_code,
                LabTest.hospital_id == doctor.hospital_id
            ).first()
            
            if not existing_test:
                lab_test = LabTest(
                    test_code=test_code,
                    name=test_name,
                    description=test_desc,
                    category_id=cat_id,
                    cost=cost,
                    sample_type=sample_type,
                    preparation_instructions=prep_instructions,
                    hospital_id=doctor.hospital_id
                )
                db.add(lab_test)
                print(f"✅ Created lab test: {test_name} (₹{cost})")
            else:
                print(f"✅ Lab test already exists: {test_name}")
        
        # Create sample consultations
        consultations_data = [
            ("outpatient", "Fever and headache", "Patient complains of fever for 2 days"),
            ("outpatient", "Routine checkup", "Annual health checkup"),
            ("outpatient", "Diabetes follow-up", "Follow-up for diabetes management")
        ]
        
        for consult_type, chief_complaint, present_history in consultations_data:
            consultation = Consultation(
                consultation_number=f"CON-{str(uuid.uuid4())[:8].upper()}",
                patient_id=patient.id,
                doctor_id=doctor.id,
                consultation_type=consult_type,
                chief_complaint=chief_complaint,
                present_history=present_history,
                consultation_fee=float(doctor.consultation_fee_inr.replace('₹', '').replace(',', '')) if doctor.consultation_fee_inr else 500.0,
                status="ongoing"
            )
            db.add(consultation)
            print(f"✅ Created consultation: {chief_complaint}")
        
        db.commit()
        
        # Show summary
        consultations_count = db.query(Consultation).count()
        lab_tests_count = db.query(LabTest).filter(LabTest.hospital_id == doctor.hospital_id).count()
        
        print(f"\n🎉 Test data setup completed!")
        print(f"📊 Total consultations: {consultations_count}")
        print(f"🧪 Total lab tests: {lab_tests_count}")
        print(f"🏥 Hospital ID: {doctor.hospital_id}")
        
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    setup_consultation_test_data()