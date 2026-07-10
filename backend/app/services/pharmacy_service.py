import uuid
from sqlalchemy.orm import Session
from app.models.pharmacy import Medicine, MedicineCategory, Prescription, PrescriptionItem, PharmacyInventory
from typing import Optional, List, Dict, Any
from datetime import datetime, date
import pandas as pd

class PharmacyService:
    def __init__(self, db: Session):
        self.db = db
    
    # Medicine Category Management
    def create_medicine_category(self, category_data: Dict[str, Any], hospital_id: int) -> MedicineCategory:
        category = MedicineCategory(
            name=category_data["name"],
            description=category_data.get("description"),
            hospital_id=hospital_id
        )
        
        self.db.add(category)
        self.db.commit()
        self.db.refresh(category)
        return category
    
    def get_medicine_categories(self, hospital_id: int) -> List[MedicineCategory]:
        return self.db.query(MedicineCategory).filter(
            MedicineCategory.hospital_id == hospital_id,
            MedicineCategory.is_active == True
        ).all()
    
    # Medicine Management
    def create_medicine(self, medicine_data: Dict[str, Any], hospital_id: int) -> Medicine:
        medicine = Medicine(
            medicine_code=medicine_data["medicine_code"],
            name=medicine_data["name"],
            generic_name=medicine_data.get("generic_name"),
            manufacturer=medicine_data.get("manufacturer"),
            category_id=medicine_data["category_id"],
            dosage_form=medicine_data.get("dosage_form"),
            strength=medicine_data.get("strength"),
            unit_price=medicine_data["unit_price"],
            description=medicine_data.get("description"),
            side_effects=medicine_data.get("side_effects"),
            contraindications=medicine_data.get("contraindications"),
            storage_conditions=medicine_data.get("storage_conditions"),
            requires_prescription=medicine_data.get("requires_prescription", True),
            hospital_id=hospital_id
        )
        
        self.db.add(medicine)
        self.db.commit()
        self.db.refresh(medicine)
        return medicine
    
    def get_medicines(self, hospital_id: int, category_id: Optional[int] = None, search_term: Optional[str] = None) -> List[Medicine]:
        query = self.db.query(Medicine).filter(
            Medicine.hospital_id == hospital_id,
            Medicine.is_active == True
        )
        
        if category_id:
            query = query.filter(Medicine.category_id == category_id)
        
        if search_term:
            query = query.filter(
                Medicine.name.ilike(f"%{search_term}%") |
                Medicine.generic_name.ilike(f"%{search_term}%") |
                Medicine.medicine_code.ilike(f"%{search_term}%")
            )
        
        return query.all()
    
    def update_medicine(self, medicine_id: int, medicine_data: Dict[str, Any]) -> Optional[Medicine]:
        medicine = self.db.query(Medicine).filter(Medicine.id == medicine_id).first()
        if not medicine:
            return None
        
        for key, value in medicine_data.items():
            if hasattr(medicine, key):
                setattr(medicine, key, value)
        
        self.db.commit()
        self.db.refresh(medicine)
        return medicine
    
    # Inventory Management
    def add_inventory_batch(self, inventory_data: Dict[str, Any], hospital_id: int) -> PharmacyInventory:
        inventory = PharmacyInventory(
            medicine_id=inventory_data["medicine_id"],
            batch_number=inventory_data["batch_number"],
            expiry_date=inventory_data["expiry_date"],
            quantity_in_stock=inventory_data["quantity_in_stock"],
            cost_price=inventory_data["cost_price"],
            selling_price=inventory_data["selling_price"],
            supplier=inventory_data.get("supplier"),
            purchase_date=inventory_data.get("purchase_date", date.today()),
            hospital_id=hospital_id
        )
        
        self.db.add(inventory)
        self.db.commit()
        self.db.refresh(inventory)
        return inventory
    
    def update_inventory_stock(self, inventory_id: int, quantity_change: int) -> Optional[PharmacyInventory]:
        inventory = self.db.query(PharmacyInventory).filter(PharmacyInventory.id == inventory_id).first()
        if not inventory:
            return None
        
        inventory.quantity_in_stock += quantity_change
        if inventory.quantity_in_stock < 0:
            inventory.quantity_in_stock = 0
        
        self.db.commit()
        self.db.refresh(inventory)
        return inventory
    
    def get_medicine_inventory(self, medicine_id: int) -> List[PharmacyInventory]:
        return self.db.query(PharmacyInventory).filter(
            PharmacyInventory.medicine_id == medicine_id,
            PharmacyInventory.is_active == True,
            PharmacyInventory.quantity_in_stock > 0
        ).order_by(PharmacyInventory.expiry_date).all()
    
    def get_low_stock_items(self, hospital_id: int, threshold: int = 10) -> List[Dict[str, Any]]:
        # Get medicines with low stock
        low_stock = []
        medicines = self.get_medicines(hospital_id)
        
        for medicine in medicines:
            total_stock = self.db.query(PharmacyInventory).filter(
                PharmacyInventory.medicine_id == medicine.id,
                PharmacyInventory.is_active == True
            ).with_entities(
                self.db.func.sum(PharmacyInventory.quantity_in_stock)
            ).scalar() or 0
            
            if total_stock <= threshold:
                low_stock.append({
                    "medicine": medicine,
                    "current_stock": total_stock,
                    "threshold": threshold
                })
        
        return low_stock
    
    def get_expiring_items(self, hospital_id: int, days_ahead: int = 30) -> List[PharmacyInventory]:
        expiry_cutoff = date.today() + pd.Timedelta(days=days_ahead)
        
        return self.db.query(PharmacyInventory).join(PharmacyInventory.medicine).filter(
            Medicine.hospital_id == hospital_id,
            PharmacyInventory.is_active == True,
            PharmacyInventory.quantity_in_stock > 0,
            PharmacyInventory.expiry_date <= expiry_cutoff
        ).order_by(PharmacyInventory.expiry_date).all()
    
    # Prescription Management
    def create_prescription(self, prescription_data: Dict[str, Any]) -> Prescription:
        prescription_number = f"RX{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        prescription = Prescription(
            prescription_number=prescription_number,
            patient_id=prescription_data["patient_id"],
            doctor_id=prescription_data["doctor_id"],
            consultation_id=prescription_data.get("consultation_id"),
            notes=prescription_data.get("notes")
        )
        
        self.db.add(prescription)
        self.db.commit()
        self.db.refresh(prescription)
        return prescription
    
    def add_prescription_item(self, prescription_id: int, item_data: Dict[str, Any]) -> PrescriptionItem:
        medicine = self.db.query(Medicine).filter(Medicine.id == item_data["medicine_id"]).first()
        if not medicine:
            raise ValueError("Medicine not found")
        
        total_price = item_data["quantity_prescribed"] * medicine.unit_price
        
        item = PrescriptionItem(
            prescription_id=prescription_id,
            medicine_id=item_data["medicine_id"],
            quantity_prescribed=item_data["quantity_prescribed"],
            dosage=item_data["dosage"],
            duration=item_data.get("duration"),
            instructions=item_data.get("instructions"),
            unit_price=medicine.unit_price,
            total_price=total_price
        )
        
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        
        # Update prescription total
        self._update_prescription_total(prescription_id)
        
        return item
    
    def _update_prescription_total(self, prescription_id: int):
        total = self.db.query(PrescriptionItem).filter(
            PrescriptionItem.prescription_id == prescription_id
        ).with_entities(
            self.db.func.sum(PrescriptionItem.total_price)
        ).scalar() or 0
        
        prescription = self.db.query(Prescription).filter(Prescription.id == prescription_id).first()
        if prescription:
            prescription.total_amount = total
            self.db.commit()
    
    def dispense_prescription(self, prescription_id: int, dispensed_by_id: int, items_to_dispense: List[Dict[str, Any]]) -> Optional[Prescription]:
        prescription = self.db.query(Prescription).filter(Prescription.id == prescription_id).first()
        if not prescription:
            return None
        
        for item_data in items_to_dispense:
            item_id = item_data["item_id"]
            quantity_dispensed = item_data["quantity_dispensed"]
            
            # Update prescription item
            item = self.db.query(PrescriptionItem).filter(PrescriptionItem.id == item_id).first()
            if item:
                item.quantity_dispensed += quantity_dispensed
                
                if item.quantity_dispensed >= item.quantity_prescribed:
                    item.status = "dispensed"
                else:
                    item.status = "partial"
                
                # Update inventory
                self._dispense_from_inventory(item.medicine_id, quantity_dispensed)
        
        # Update prescription status
        all_items = self.db.query(PrescriptionItem).filter(
            PrescriptionItem.prescription_id == prescription_id
        ).all()
        
        if all(item.status == "dispensed" for item in all_items):
            prescription.status = "dispensed"
        elif any(item.status in ["dispensed", "partial"] for item in all_items):
            prescription.status = "partial"
        
        prescription.dispensed_by_id = dispensed_by_id
        prescription.dispensed_date = datetime.now()
        
        self.db.commit()
        self.db.refresh(prescription)
        return prescription
    
    def _dispense_from_inventory(self, medicine_id: int, quantity: int):
        # FIFO: Use earliest expiring batches first
        inventory_batches = self.get_medicine_inventory(medicine_id)
        
        remaining_quantity = quantity
        for batch in inventory_batches:
            if remaining_quantity <= 0:
                break
            
            if batch.quantity_in_stock >= remaining_quantity:
                batch.quantity_in_stock -= remaining_quantity
                remaining_quantity = 0
            else:
                remaining_quantity -= batch.quantity_in_stock
                batch.quantity_in_stock = 0
        
        self.db.commit()
    
    def get_prescriptions(self, hospital_id: int, status: Optional[str] = None) -> List[Prescription]:
        # Join with patient to filter by hospital
        query = self.db.query(Prescription).join(Prescription.patient).filter(
            Prescription.patient.has(hospital_id=hospital_id)
        )
        
        if status:
            query = query.filter(Prescription.status == status)
        
        return query.order_by(Prescription.prescription_date.desc()).all()
    
    def get_patient_prescriptions(self, patient_id: int) -> List[Prescription]:
        return self.db.query(Prescription).filter(
            Prescription.patient_id == patient_id
        ).order_by(Prescription.prescription_date.desc()).all()
    
    # Import/Export Functionality
    def export_medicines(self, hospital_id: int) -> List[Dict[str, Any]]:
        medicines = self.get_medicines(hospital_id)
        export_data = []
        
        for medicine in medicines:
            medicine_data = {
                "medicine_code": medicine.medicine_code,
                "name": medicine.name,
                "generic_name": medicine.generic_name,
                "manufacturer": medicine.manufacturer,
                "category_name": medicine.category.name,
                "dosage_form": medicine.dosage_form,
                "strength": medicine.strength,
                "unit_price": medicine.unit_price,
                "description": medicine.description,
                "side_effects": medicine.side_effects,
                "contraindications": medicine.contraindications,
                "storage_conditions": medicine.storage_conditions,
                "requires_prescription": medicine.requires_prescription
            }
            export_data.append(medicine_data)
        
        return export_data
    
    def import_medicines(self, import_data: List[Dict[str, Any]], hospital_id: int) -> Dict[str, Any]:
        results = {"successful": 0, "errors": []}
        
        for medicine_data in import_data:
            try:
                # Find or create category
                category_name = medicine_data.get("category_name")
                if category_name:
                    category = self.db.query(MedicineCategory).filter(
                        MedicineCategory.name == category_name,
                        MedicineCategory.hospital_id == hospital_id
                    ).first()
                    
                    if not category:
                        category = self.create_medicine_category(
                            {"name": category_name},
                            hospital_id
                        )
                    
                    medicine_data["category_id"] = category.id
                    del medicine_data["category_name"]
                
                self.create_medicine(medicine_data, hospital_id)
                results["successful"] += 1
                
            except Exception as e:
                results["errors"].append(f"Error importing {medicine_data.get('name', 'Unknown')}: {str(e)}")
        
        return results
    
    def get_pharmacy_statistics(self, hospital_id: int) -> Dict[str, Any]:
        total_medicines = self.db.query(Medicine).filter(
            Medicine.hospital_id == hospital_id,
            Medicine.is_active == True
        ).count()
        
        total_prescriptions = self.db.query(Prescription).join(Prescription.patient).filter(
            Prescription.patient.has(hospital_id=hospital_id)
        ).count()
        
        pending_prescriptions = self.db.query(Prescription).join(Prescription.patient).filter(
            Prescription.patient.has(hospital_id=hospital_id),
            Prescription.status == "pending"
        ).count()
        
        low_stock_count = len(self.get_low_stock_items(hospital_id))
        expiring_items_count = len(self.get_expiring_items(hospital_id))
        
        return {
            "total_medicines": total_medicines,
            "total_prescriptions": total_prescriptions,
            "pending_prescriptions": pending_prescriptions,
            "low_stock_items": low_stock_count,
            "expiring_items": expiring_items_count
        }