from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from config.database import get_db
from app.models.pharmacy import Medicine, MedicineCategory
from app.models.user import User
from app.utils.dependencies import get_current_user

router = APIRouter()

class MedicineResponse(BaseModel):
    id: int
    medicine_code: str
    name: str
    generic_name: Optional[str]
    manufacturer: Optional[str]
    category_name: str
    dosage_form: Optional[str]
    strength: Optional[str]
    unit_price: float
    description: Optional[str]
    is_active: bool
    requires_prescription: bool
    
    class Config:
        from_attributes = True

class CategoryResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    is_active: bool
    
    class Config:
        from_attributes = True

@router.get("/", response_model=List[MedicineResponse])
async def get_medicines(
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    is_active: bool = True,
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get medicines with optional filters"""
    query = db.query(Medicine).join(MedicineCategory)
    
    # Filter by hospital
    query = query.filter(Medicine.hospital_id == current_user.hospital_id)
    
    # Filter by active status
    query = query.filter(Medicine.is_active == is_active)
    
    # Search filter
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Medicine.name.ilike(search_term)) |
            (Medicine.generic_name.ilike(search_term)) |
            (Medicine.medicine_code.ilike(search_term))
        )
    
    # Category filter
    if category_id:
        query = query.filter(Medicine.category_id == category_id)
    
    medicines = query.offset(offset).limit(limit).all()
    
    # Build response
    result = []
    for medicine in medicines:
        result.append(MedicineResponse(
            id=medicine.id,
            medicine_code=medicine.medicine_code,
            name=medicine.name,
            generic_name=medicine.generic_name,
            manufacturer=medicine.manufacturer,
            category_name=medicine.category.name,
            dosage_form=medicine.dosage_form,
            strength=medicine.strength,
            unit_price=medicine.unit_price,
            description=medicine.description,
            is_active=medicine.is_active,
            requires_prescription=medicine.requires_prescription
        ))
    
    return result

@router.get("/categories", response_model=List[CategoryResponse])
async def get_medicine_categories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get medicine categories"""
    categories = db.query(MedicineCategory).filter(
        MedicineCategory.hospital_id == current_user.hospital_id,
        MedicineCategory.is_active == True
    ).all()
    
    return categories

@router.get("/{medicine_id}", response_model=MedicineResponse)
async def get_medicine(
    medicine_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific medicine"""
    medicine = db.query(Medicine).filter(
        Medicine.id == medicine_id,
        Medicine.hospital_id == current_user.hospital_id
    ).first()
    
    if not medicine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medicine not found"
        )
    
    return MedicineResponse(
        id=medicine.id,
        medicine_code=medicine.medicine_code,
        name=medicine.name,
        generic_name=medicine.generic_name,
        manufacturer=medicine.manufacturer,
        category_name=medicine.category.name,
        dosage_form=medicine.dosage_form,
        strength=medicine.strength,
        unit_price=medicine.unit_price,
        description=medicine.description,
        is_active=medicine.is_active,
        requires_prescription=medicine.requires_prescription
    )