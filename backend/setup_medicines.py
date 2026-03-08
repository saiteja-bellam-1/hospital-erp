#!/usr/bin/env python3

"""
Script to populate sample medicines for prescription functionality
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.database import SessionLocal, create_tables
from app.models.pharmacy import MedicineCategory, Medicine
from app.models.hospital import Hospital

def setup_medicines():
    db = SessionLocal()
    
    try:
        print("🏥 Setting up sample medicines...")
        
        # Get hospital (should be ID 1)
        hospital = db.query(Hospital).first()
        if not hospital:
            print("❌ No hospital found! Please run hospital setup first.")
            return
        
        print(f"📋 Using hospital: {hospital.name}")
        
        # Create medicine categories
        categories_data = [
            {"name": "Antibiotics", "description": "Antimicrobial medications"},
            {"name": "Pain Relief", "description": "Analgesics and pain management"},
            {"name": "Cardiovascular", "description": "Heart and blood pressure medications"},
            {"name": "Respiratory", "description": "Breathing and lung medications"},
            {"name": "Gastrointestinal", "description": "Stomach and digestive medications"},
            {"name": "Vitamins & Supplements", "description": "Nutritional supplements"}
        ]
        
        categories = {}
        for cat_data in categories_data:
            # Check if category already exists
            existing_cat = db.query(MedicineCategory).filter(
                MedicineCategory.name == cat_data["name"],
                MedicineCategory.hospital_id == hospital.id
            ).first()
            
            if not existing_cat:
                category = MedicineCategory(
                    name=cat_data["name"],
                    description=cat_data["description"],
                    hospital_id=hospital.id
                )
                db.add(category)
                db.flush()
                categories[cat_data["name"]] = category
                print(f"   Created category: {cat_data['name']}")
            else:
                categories[cat_data["name"]] = existing_cat
                print(f"   Using existing category: {cat_data['name']}")
        
        # Create sample medicines
        medicines_data = [
            # Antibiotics
            {"code": "AMX500", "name": "Amoxicillin 500mg", "generic": "Amoxicillin", "manufacturer": "Generic Pharma", "category": "Antibiotics", "form": "Capsule", "strength": "500mg", "price": 15.00},
            {"code": "AZM250", "name": "Azithromycin 250mg", "generic": "Azithromycin", "manufacturer": "MediCorp", "category": "Antibiotics", "form": "Tablet", "strength": "250mg", "price": 25.00},
            {"code": "CFX500", "name": "Cephalexin 500mg", "generic": "Cephalexin", "manufacturer": "PharmaTech", "category": "Antibiotics", "form": "Capsule", "strength": "500mg", "price": 20.00},
            
            # Pain Relief
            {"code": "PCM500", "name": "Paracetamol 500mg", "generic": "Paracetamol", "manufacturer": "Universal Pharma", "category": "Pain Relief", "form": "Tablet", "strength": "500mg", "price": 5.00},
            {"code": "IBU400", "name": "Ibuprofen 400mg", "generic": "Ibuprofen", "manufacturer": "PainCare Ltd", "category": "Pain Relief", "form": "Tablet", "strength": "400mg", "price": 8.00},
            {"code": "ASP325", "name": "Aspirin 325mg", "generic": "Acetylsalicylic Acid", "manufacturer": "CardioMed", "category": "Pain Relief", "form": "Tablet", "strength": "325mg", "price": 6.00},
            
            # Cardiovascular
            {"code": "ATN50", "name": "Atenolol 50mg", "generic": "Atenolol", "manufacturer": "HeartCare Pharma", "category": "Cardiovascular", "form": "Tablet", "strength": "50mg", "price": 12.00},
            {"code": "LIS10", "name": "Lisinopril 10mg", "generic": "Lisinopril", "manufacturer": "BP Control Inc", "category": "Cardiovascular", "form": "Tablet", "strength": "10mg", "price": 18.00},
            
            # Respiratory
            {"code": "SAL100", "name": "Salbutamol Inhaler", "generic": "Salbutamol", "manufacturer": "BreathEasy Corp", "category": "Respiratory", "form": "Inhaler", "strength": "100mcg", "price": 35.00},
            {"code": "CET10", "name": "Cetirizine 10mg", "generic": "Cetirizine", "manufacturer": "AllergyFree Ltd", "category": "Respiratory", "form": "Tablet", "strength": "10mg", "price": 10.00},
            
            # Gastrointestinal
            {"code": "OME20", "name": "Omeprazole 20mg", "generic": "Omeprazole", "manufacturer": "GastroMed", "category": "Gastrointestinal", "form": "Capsule", "strength": "20mg", "price": 22.00},
            {"code": "DOM10", "name": "Domperidone 10mg", "generic": "Domperidone", "manufacturer": "DigestCare", "category": "Gastrointestinal", "form": "Tablet", "strength": "10mg", "price": 14.00},
            
            # Vitamins
            {"code": "VTD1000", "name": "Vitamin D3 1000IU", "generic": "Cholecalciferol", "manufacturer": "VitaHealth", "category": "Vitamins & Supplements", "form": "Tablet", "strength": "1000IU", "price": 16.00},
            {"code": "VTB12", "name": "Vitamin B12 Complex", "generic": "Cyanocobalamin", "manufacturer": "NutriVital", "category": "Vitamins & Supplements", "form": "Tablet", "strength": "500mcg", "price": 18.00},
        ]
        
        created_count = 0
        for med_data in medicines_data:
            # Check if medicine already exists
            existing_med = db.query(Medicine).filter(
                Medicine.medicine_code == med_data["code"],
                Medicine.hospital_id == hospital.id
            ).first()
            
            if not existing_med:
                medicine = Medicine(
                    medicine_code=med_data["code"],
                    name=med_data["name"],
                    generic_name=med_data["generic"],
                    manufacturer=med_data["manufacturer"],
                    category_id=categories[med_data["category"]].id,
                    dosage_form=med_data["form"],
                    strength=med_data["strength"],
                    unit_price=med_data["price"],
                    description=f"{med_data['generic']} - {med_data['strength']} {med_data['form']}",
                    requires_prescription=True,
                    hospital_id=hospital.id
                )
                db.add(medicine)
                created_count += 1
                print(f"   Created medicine: {med_data['name']}")
            else:
                print(f"   Medicine already exists: {med_data['name']}")
        
        db.commit()
        print(f"✅ Successfully created {created_count} medicines!")
        
        # Show summary
        total_medicines = db.query(Medicine).filter(Medicine.hospital_id == hospital.id).count()
        total_categories = db.query(MedicineCategory).filter(MedicineCategory.hospital_id == hospital.id).count()
        print(f"📊 Total medicines in system: {total_medicines}")
        print(f"📊 Total categories in system: {total_categories}")
        
    except Exception as e:
        print(f"❌ Error setting up medicines: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    setup_medicines()