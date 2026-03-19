from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func as sqlfunc
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, date
import uuid
import io

from config.database import get_db
from app.models.user import User
from app.models.patient import Patient
from app.models.hospital import Hospital
from app.models.permissions import HospitalSettings
from app.models.lab import (
    LabTestCategory, LabTest, LabTestParameter,
    PatientLabOrder, LabReport,
    LabTestPackageCategory, LabTestPackage, LabTestPackageItem
)
from app.utils.dependencies import get_current_user, require_permission
from app.utils.auth import Modules
from app.utils.pdf_service import pdf_service

router = APIRouter()

# ============================================================
# Pydantic Models
# ============================================================

class CategoryCreate(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = None

class CategoryResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    is_active: bool
    test_count: Optional[int] = 0
    class Config:
        from_attributes = True

class ParameterCreate(BaseModel):
    parameter_name: str = Field(..., max_length=200)
    unit: Optional[str] = None
    method: Optional[str] = None
    section: Optional[str] = None
    field_type: str = Field(default="numeric", pattern="^(numeric|less_than|greater_than|positive_negative|reactive|presence_absence|cloudy_clear|colour|manual|text|select)$")
    reference_ranges: Optional[list] = None  # [{min, max, gender, age_min, age_max, description}]
    possible_values: Optional[list] = None
    abnormal_values: Optional[list] = None
    normal_value: Optional[str] = None
    notes: Optional[str] = None
    display_order: int = 0
    # Legacy fields — kept for backward compat
    reference_min_male: Optional[float] = None
    reference_max_male: Optional[float] = None
    reference_min_female: Optional[float] = None
    reference_max_female: Optional[float] = None
    reference_min_default: Optional[float] = None
    reference_max_default: Optional[float] = None
    reference_min_child: Optional[float] = None
    reference_max_child: Optional[float] = None

class ParameterResponse(BaseModel):
    id: int
    parameter_name: str
    unit: Optional[str]
    method: Optional[str] = None
    section: Optional[str] = None
    field_type: str
    reference_ranges: Optional[list] = None
    possible_values: Optional[list]
    abnormal_values: Optional[list] = None
    normal_value: Optional[str] = None
    notes: Optional[str] = None
    display_order: int
    is_active: bool
    # Legacy
    reference_min_male: Optional[float] = None
    reference_max_male: Optional[float] = None
    reference_min_female: Optional[float] = None
    reference_max_female: Optional[float] = None
    reference_min_default: Optional[float] = None
    reference_max_default: Optional[float] = None
    reference_min_child: Optional[float] = None
    reference_max_child: Optional[float] = None
    class Config:
        from_attributes = True

class TestCreate(BaseModel):
    test_code: str = Field(..., max_length=20)
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    category_id: int
    cost: float = Field(..., ge=0)
    sample_type: Optional[str] = None
    method: Optional[str] = None
    preparation_instructions: Optional[str] = None
    parameters: Optional[List[ParameterCreate]] = None

class TestUpdate(BaseModel):
    test_code: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[int] = None
    cost: Optional[float] = None
    sample_type: Optional[str] = None
    method: Optional[str] = None
    preparation_instructions: Optional[str] = None
    is_active: Optional[bool] = None

class TestResponse(BaseModel):
    id: int
    test_code: str
    name: str
    description: Optional[str]
    category_id: int
    category_name: Optional[str] = None
    cost: float
    sample_type: Optional[str]
    method: Optional[str]
    preparation_instructions: Optional[str]
    is_active: bool
    parameters: List[ParameterResponse] = []
    class Config:
        from_attributes = True

class OrderCreate(BaseModel):
    patient_id: int
    test_ids: List[int] = Field(..., min_length=1)
    appointment_id: Optional[int] = None
    priority: str = Field(default="normal", pattern="^(normal|urgent|stat)$")
    notes: Optional[str] = None

class OrderResponse(BaseModel):
    id: int
    order_number: str
    patient_id: int
    patient_name: Optional[str] = None
    test_id: int
    test_name: Optional[str] = None
    test_code: Optional[str] = None
    doctor_id: Optional[int]
    doctor_name: Optional[str] = None
    status: str
    priority: str
    order_date: datetime
    collection_date: Optional[datetime]
    completion_date: Optional[datetime]
    notes: Optional[str]
    consultation_id: Optional[int] = None
    appointment_id: Optional[int] = None
    order_source: Optional[str] = None  # "appointment", "package", "direct"
    has_report: bool = False
    report_id: Optional[int] = None
    amount: float = 0.0
    payment_status: str = "pending"
    payment_method: Optional[str] = None
    payment_date: Optional[datetime] = None
    package_id: Optional[int] = None
    package_name: Optional[str] = None
    package_booking_id: Optional[str] = None
    sample_id: Optional[str] = None
    class Config:
        from_attributes = True

class ResultEntry(BaseModel):
    parameter_id: int
    value: str
    remarks: Optional[str] = None

class ResultSubmit(BaseModel):
    results: List[ResultEntry]
    interpretation: Optional[str] = None

class ReportParameterResult(BaseModel):
    parameter_id: int
    parameter_name: str
    value: str
    unit: Optional[str]
    reference_min: Optional[float]
    reference_max: Optional[float]
    is_abnormal: bool = False
    field_type: str = "numeric"

class ReportResponse(BaseModel):
    id: int
    order_id: int
    order_number: str
    patient_id: int
    patient_name: str
    patient_gender: Optional[str] = None
    patient_age: Optional[int] = None
    test_id: int
    test_name: str
    test_code: str
    method: Optional[str] = None
    doctor_name: Optional[str] = None
    technician_name: Optional[str] = None
    report_date: datetime
    interpretation: Optional[str]
    results: List[ReportParameterResult] = []

class StatsResponse(BaseModel):
    total_tests: int
    total_categories: int
    total_orders: int
    pending_orders: int
    completed_today: int

# --- Package Schemas ---

class PackageCategoryCreate(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = None

class PackageCategoryResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    is_active: bool
    package_count: int = 0
    class Config:
        from_attributes = True

class PackageCreate(BaseModel):
    package_code: str = Field(..., max_length=20)
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    category_id: int
    package_price: float = Field(..., ge=0)
    test_ids: List[int] = Field(..., min_length=1)

class PackageUpdate(BaseModel):
    package_code: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[int] = None
    package_price: Optional[float] = None
    test_ids: Optional[List[int]] = None
    is_active: Optional[bool] = None

class PackageTestInfo(BaseModel):
    id: int
    test_code: str
    name: str
    cost: float
    sample_type: Optional[str] = None

class PackageResponse(BaseModel):
    id: int
    package_code: str
    name: str
    description: Optional[str]
    category_id: int
    category_name: Optional[str] = None
    package_price: float
    actual_price: float
    discount_percentage: float = 0.0
    is_active: bool
    tests: List[PackageTestInfo] = []
    class Config:
        from_attributes = True

class PackageBooking(BaseModel):
    patient_id: int
    priority: str = Field(default="normal", pattern="^(normal|urgent|stat)$")
    notes: Optional[str] = None
    referred_by: Optional[str] = Field(None, max_length=100)
    payment_method: str = Field(..., pattern="^(cash|card|upi|cheque|online|insurance)$")
    include_header: bool = True

# ============================================================
# Helper
# ============================================================

def _require_lab_admin(current_user: User):
    if not any(r in current_user.role_names for r in ['super_admin', 'hospital_admin', 'lab_admin', 'lab_technician']):
        raise HTTPException(status_code=403, detail="Lab admin access required")

def _require_lab_access(current_user: User):
    if not any(r in current_user.role_names for r in ['super_admin', 'hospital_admin', 'lab_admin', 'lab_technician', 'doctor']):
        raise HTTPException(status_code=403, detail="Lab access required")

def _calculate_age(dob):
    if not dob:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

def _match_reference_range(ranges, gender, age):
    """Find the best matching reference range entry for a patient's gender and age.
    Returns (ref_min, ref_max, description).
    Priority: exact gender+age match > gender match > common+age match > common."""
    if not ranges:
        return None, None, ""
    best = None
    best_score = -1
    for r in ranges:
        score = 0
        r_gender = (r.get('gender') or 'common').lower()
        r_age_min = r.get('age_min')
        r_age_max = r.get('age_max')

        # Gender match
        if gender and r_gender == gender:
            score += 2
        elif r_gender == 'common':
            score += 1
        else:
            continue  # wrong gender, skip

        # Age match
        if age is not None and r_age_min is not None and r_age_max is not None:
            try:
                if float(r_age_min) <= age <= float(r_age_max):
                    score += 2
                else:
                    continue  # outside age range, skip
            except (ValueError, TypeError):
                pass
        elif r_age_min is None and r_age_max is None:
            score += 1  # no age restriction, broad match

        if score > best_score:
            best_score = score
            best = r

    if best:
        ref_min = best.get('min')
        ref_max = best.get('max')
        try:
            ref_min = float(ref_min) if ref_min is not None and ref_min != '' else None
        except (ValueError, TypeError):
            ref_min = None
        try:
            ref_max = float(ref_max) if ref_max is not None and ref_max != '' else None
        except (ValueError, TypeError):
            ref_max = None
        return ref_min, ref_max, best.get('description', '')
    return None, None, ""


def _build_test_response(test: LabTest, db: Session) -> dict:
    category = db.query(LabTestCategory).filter(LabTestCategory.id == test.category_id).first()
    params = db.query(LabTestParameter).filter(
        LabTestParameter.test_id == test.id,
        LabTestParameter.is_active == True
    ).order_by(LabTestParameter.display_order).all()
    return {
        "id": test.id,
        "test_code": test.test_code,
        "name": test.name,
        "description": test.description,
        "category_id": test.category_id,
        "category_name": category.name if category else None,
        "cost": test.cost,
        "sample_type": test.sample_type,
        "method": test.method,
        "preparation_instructions": test.preparation_instructions,
        "is_active": test.is_active,
        "parameters": [
            {
                "id": p.id,
                "parameter_name": p.parameter_name,
                "unit": p.unit,
                "method": p.method,
                "section": p.section,
                "field_type": p.field_type,
                "reference_min_male": p.reference_min_male,
                "reference_max_male": p.reference_max_male,
                "reference_min_female": p.reference_min_female,
                "reference_max_female": p.reference_max_female,
                "reference_min_default": p.reference_min_default,
                "reference_max_default": p.reference_max_default,
                "possible_values": p.possible_values,
                "display_order": p.display_order,
                "is_active": p.is_active
            } for p in params
        ]
    }

def _build_order_response(order: PatientLabOrder, db: Session) -> dict:
    patient = db.query(Patient).filter(Patient.id == order.patient_id).first()
    test = db.query(LabTest).filter(LabTest.id == order.test_id).first()
    doctor = db.query(User).filter(User.id == order.doctor_id).first() if order.doctor_id else None
    report = db.query(LabReport).filter(LabReport.order_id == order.id).first()
    return {
        "id": order.id,
        "order_number": order.order_number,
        "patient_id": order.patient_id,
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else None,
        "test_id": order.test_id,
        "test_name": test.name if test else None,
        "test_code": test.test_code if test else None,
        "doctor_id": order.doctor_id,
        "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else None,
        "status": order.status,
        "priority": order.priority,
        "order_date": order.order_date,
        "collection_date": order.collection_date,
        "completion_date": order.completion_date,
        "notes": order.notes,
        "consultation_id": order.consultation_id,
        "appointment_id": order.appointment_id,
        "order_source": "package" if order.package_id else ("appointment" if order.appointment_id else "direct"),
        "has_report": report is not None,
        "report_id": report.id if report else None,
        "amount": order.amount or (test.cost if test else 0.0),
        "payment_status": order.payment_status or "pending",
        "payment_method": order.payment_method,
        "payment_date": order.payment_date,
        "package_id": order.package_id,
        "package_name": order.package.name if order.package_id and order.package else None,
        "package_booking_id": order.package_booking_id,
        "sample_id": order.sample_id,
    }

def _build_report_response(report: LabReport, db: Session) -> dict:
    order = db.query(PatientLabOrder).filter(PatientLabOrder.id == report.order_id).first()
    patient = db.query(Patient).filter(Patient.id == order.patient_id).first()
    test = db.query(LabTest).filter(LabTest.id == order.test_id).first()
    doctor = db.query(User).filter(User.id == order.doctor_id).first() if order.doctor_id else None
    tech = db.query(User).filter(User.id == report.technician_id).first() if report.technician_id else None

    gender = patient.gender.lower() if patient and patient.gender else None
    age = _calculate_age(patient.date_of_birth) if patient else None

    # Build results with abnormal flags
    result_values = report.result_values or []
    results = []
    for rv in result_values:
        param = db.query(LabTestParameter).filter(LabTestParameter.id == rv.get("parameter_id")).first()
        if not param:
            continue

        # Determine reference range — use new reference_ranges if available, else legacy columns
        ref_min = None
        ref_max = None
        matched_desc = ""
        if param.reference_ranges:
            ref_min, ref_max, matched_desc = _match_reference_range(param.reference_ranges, gender, age)
        else:
            # Legacy fallback
            if gender == "male" and param.reference_min_male is not None:
                ref_min = param.reference_min_male
                ref_max = param.reference_max_male
            elif gender == "female" and param.reference_min_female is not None:
                ref_min = param.reference_min_female
                ref_max = param.reference_max_female
            else:
                ref_min = param.reference_min_default
                ref_max = param.reference_max_default

        # Check abnormal
        is_abnormal = False
        raw_value = rv.get("value", "")
        if param.field_type in ("numeric", "less_than", "greater_than") and raw_value:
            try:
                clean_val = raw_value.strip().lstrip('<>').strip()
                val = float(clean_val)
                if param.field_type == "less_than":
                    # Value should be < ref_max to be normal
                    if ref_max is not None and val >= ref_max:
                        is_abnormal = True
                elif param.field_type == "greater_than":
                    # Value should be > ref_min to be normal
                    if ref_min is not None and val <= ref_min:
                        is_abnormal = True
                else:
                    # Range: check both bounds, also handle < > prefixed values
                    if raw_value.strip().startswith('<'):
                        if ref_min is not None and val <= ref_min:
                            is_abnormal = True
                    elif raw_value.strip().startswith('>'):
                        if ref_max is not None and val >= ref_max:
                            is_abnormal = True
                    else:
                        if ref_min is not None and val < ref_min:
                            is_abnormal = True
                        if ref_max is not None and val > ref_max:
                            is_abnormal = True
            except (ValueError, TypeError):
                pass
        elif param.field_type in ("select", "text", "manual", "colour",
                                   "positive_negative", "reactive", "presence_absence", "cloudy_clear") and raw_value:
            # Check against abnormal_values list
            abnormal_list = param.abnormal_values or []
            if abnormal_list and raw_value.strip() in abnormal_list:
                is_abnormal = True

        results.append({
            "parameter_id": param.id,
            "parameter_name": param.parameter_name,
            "value": raw_value,
            "unit": param.unit,
            "method": param.method or "",
            "section": param.section or "",
            "reference_min": ref_min,
            "reference_max": ref_max,
            "normal_value": param.normal_value,
            "is_abnormal": is_abnormal,
            "field_type": param.field_type,
            "remarks": rv.get("remarks", "")
        })

    # Determine referral label: doctor = "Prescribed By", referral/self = "Referred By"
    referral_label = "Referred By"
    referral_name = "Self"
    if doctor:
        referral_label = "Prescribed By"
        referral_name = f"Dr. {doctor.first_name} {doctor.last_name}"
    elif order.referred_by:
        referral_name = order.referred_by
    elif patient and patient.referred_by:
        referral_name = patient.referred_by

    return {
        "id": report.id,
        "order_id": order.id,
        "order_number": order.order_number,
        "patient_id": patient.id if patient else 0,
        "patient_uuid": patient.patient_id if patient else "",
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else "Unknown",
        "patient_phone": patient.primary_phone if patient else "",
        "patient_gender": patient.gender if patient else None,
        "patient_age": age,
        "test_id": test.id if test else 0,
        "test_name": test.name if test else "Unknown",
        "test_code": test.test_code if test else "",
        "method": test.method if test else None,
        "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else None,
        "referral_label": referral_label,
        "referral_name": referral_name,
        "technician_name": f"{tech.first_name} {tech.last_name}" if tech else None,
        "order_date": order.order_date,
        "collection_date": order.collection_date,
        "report_date": report.report_date,
        "report_status": "Final",
        "interpretation": report.interpretation,
        "results": results
    }

# ============================================================
# Category Endpoints
# ============================================================

@router.get("/categories", response_model=List[CategoryResponse])
async def list_categories(
    current_user: User = Depends(require_permission(Modules.LAB, "read")),
    db: Session = Depends(get_db)
):
    cats = db.query(LabTestCategory).filter(
        LabTestCategory.hospital_id == current_user.hospital_id,
        LabTestCategory.is_active == True
    ).order_by(LabTestCategory.name).all()

    result = []
    for c in cats:
        count = db.query(LabTest).filter(LabTest.category_id == c.id, LabTest.is_active == True).count()
        result.append({
            "id": c.id, "name": c.name, "description": c.description,
            "is_active": c.is_active, "test_count": count
        })
    return result

@router.post("/categories", response_model=CategoryResponse)
async def create_category(
    data: CategoryCreate,
    current_user: User = Depends(require_permission(Modules.LAB, "write")),
    db: Session = Depends(get_db)
):
    _require_lab_admin(current_user)
    cat = LabTestCategory(
        name=data.name, description=data.description,
        hospital_id=current_user.hospital_id
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return {"id": cat.id, "name": cat.name, "description": cat.description, "is_active": True, "test_count": 0}

@router.put("/categories/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: int, data: CategoryCreate,
    current_user: User = Depends(require_permission(Modules.LAB, "write")),
    db: Session = Depends(get_db)
):
    _require_lab_admin(current_user)
    cat = db.query(LabTestCategory).filter(
        LabTestCategory.id == category_id,
        LabTestCategory.hospital_id == current_user.hospital_id
    ).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    cat.name = data.name
    if data.description is not None:
        cat.description = data.description
    db.commit()
    count = db.query(LabTest).filter(LabTest.category_id == cat.id, LabTest.is_active == True).count()
    return {"id": cat.id, "name": cat.name, "description": cat.description, "is_active": cat.is_active, "test_count": count}

@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: int,
    current_user: User = Depends(require_permission(Modules.LAB, "delete")),
    db: Session = Depends(get_db)
):
    _require_lab_admin(current_user)
    cat = db.query(LabTestCategory).filter(
        LabTestCategory.id == category_id,
        LabTestCategory.hospital_id == current_user.hospital_id
    ).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    cat.is_active = False
    db.commit()
    return {"message": "Category deleted"}

# ============================================================
# Lab Test Endpoints
# ============================================================

@router.get("/tests", response_model=List[TestResponse])
async def list_tests(
    category_id: Optional[int] = None,
    search: Optional[str] = None,
    include_inactive: bool = False,
    current_user: User = Depends(require_permission(Modules.LAB, "read")),
    db: Session = Depends(get_db)
):
    query = db.query(LabTest).filter(LabTest.hospital_id == current_user.hospital_id)
    if not include_inactive:
        query = query.filter(LabTest.is_active == True)
    if category_id:
        query = query.filter(LabTest.category_id == category_id)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (LabTest.name.ilike(search_term)) | (LabTest.test_code.ilike(search_term))
        )
    tests = query.order_by(LabTest.name).all()
    return [_build_test_response(t, db) for t in tests]

@router.get("/tests/{test_id}", response_model=TestResponse)
async def get_test(
    test_id: int,
    current_user: User = Depends(require_permission(Modules.LAB, "read")),
    db: Session = Depends(get_db)
):
    test = db.query(LabTest).filter(
        LabTest.id == test_id,
        LabTest.hospital_id == current_user.hospital_id
    ).first()
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")
    return _build_test_response(test, db)

@router.post("/tests", response_model=TestResponse)
async def create_test(
    data: TestCreate,
    current_user: User = Depends(require_permission(Modules.LAB, "write")),
    db: Session = Depends(get_db)
):
    _require_lab_admin(current_user)

    # Check category
    cat = db.query(LabTestCategory).filter(
        LabTestCategory.id == data.category_id,
        LabTestCategory.hospital_id == current_user.hospital_id
    ).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    # Check duplicate code
    existing = db.query(LabTest).filter(
        LabTest.test_code == data.test_code,
        LabTest.hospital_id == current_user.hospital_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Test code '{data.test_code}' already exists")

    test = LabTest(
        test_code=data.test_code, name=data.name, description=data.description,
        category_id=data.category_id, cost=data.cost, sample_type=data.sample_type,
        method=data.method, preparation_instructions=data.preparation_instructions,
        hospital_id=current_user.hospital_id
    )
    db.add(test)
    db.flush()

    # Add parameters if provided
    if data.parameters:
        for i, p in enumerate(data.parameters):
            param = LabTestParameter(
                test_id=test.id, parameter_name=p.parameter_name, unit=p.unit,
                field_type=p.field_type,
                reference_min_male=p.reference_min_male, reference_max_male=p.reference_max_male,
                reference_min_female=p.reference_min_female, reference_max_female=p.reference_max_female,
                reference_min_default=p.reference_min_default, reference_max_default=p.reference_max_default,
                possible_values=p.possible_values, display_order=p.display_order or i
            )
            db.add(param)

    db.commit()
    db.refresh(test)
    return _build_test_response(test, db)

@router.put("/tests/{test_id}", response_model=TestResponse)
async def update_test(
    test_id: int, data: TestUpdate,
    current_user: User = Depends(require_permission(Modules.LAB, "write")),
    db: Session = Depends(get_db)
):
    _require_lab_admin(current_user)
    test = db.query(LabTest).filter(
        LabTest.id == test_id, LabTest.hospital_id == current_user.hospital_id
    ).first()
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    for field in ['test_code', 'name', 'description', 'category_id', 'cost', 'sample_type', 'method', 'preparation_instructions', 'is_active']:
        val = getattr(data, field, None)
        if val is not None:
            setattr(test, field, val)

    db.commit()
    db.refresh(test)
    return _build_test_response(test, db)

@router.delete("/tests/{test_id}")
async def delete_test(
    test_id: int,
    current_user: User = Depends(require_permission(Modules.LAB, "delete")),
    db: Session = Depends(get_db)
):
    _require_lab_admin(current_user)
    test = db.query(LabTest).filter(
        LabTest.id == test_id, LabTest.hospital_id == current_user.hospital_id
    ).first()
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")
    test.is_active = False
    db.commit()
    return {"message": "Test deleted"}

# ============================================================
# Parameter Endpoints
# ============================================================

@router.post("/tests/{test_id}/parameters", response_model=ParameterResponse)
async def add_parameter(
    test_id: int, data: ParameterCreate,
    current_user: User = Depends(require_permission(Modules.LAB, "write")),
    db: Session = Depends(get_db)
):
    _require_lab_admin(current_user)
    test = db.query(LabTest).filter(
        LabTest.id == test_id, LabTest.hospital_id == current_user.hospital_id
    ).first()
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    param = LabTestParameter(test_id=test_id, **data.dict())
    db.add(param)
    db.commit()
    db.refresh(param)
    return param

# NOTE: reorder and bulk routes MUST come before {param_id} to avoid path conflict
@router.put("/tests/{test_id}/parameters/reorder")
async def reorder_parameters(
    test_id: int, order: List[int],
    current_user: User = Depends(require_permission(Modules.LAB, "write")),
    db: Session = Depends(get_db)
):
    """Update display_order for parameters. Body is a list of parameter IDs in desired order."""
    _require_lab_admin(current_user)
    for idx, param_id in enumerate(order):
        param = db.query(LabTestParameter).filter(
            LabTestParameter.id == param_id, LabTestParameter.test_id == test_id
        ).first()
        if param:
            param.display_order = idx
    db.commit()
    return {"message": f"Reordered {len(order)} parameters"}

@router.put("/tests/{test_id}/parameters/bulk")
async def bulk_upsert_parameters(
    test_id: int, parameters: List[ParameterCreate],
    current_user: User = Depends(require_permission(Modules.LAB, "write")),
    db: Session = Depends(get_db)
):
    """Replace all parameters for a test"""
    _require_lab_admin(current_user)
    test = db.query(LabTest).filter(
        LabTest.id == test_id, LabTest.hospital_id == current_user.hospital_id
    ).first()
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    # Delete existing
    db.query(LabTestParameter).filter(LabTestParameter.test_id == test_id).delete()

    # Add new
    for i, p in enumerate(parameters):
        param = LabTestParameter(
            test_id=test_id, parameter_name=p.parameter_name, unit=p.unit,
            method=p.method, section=p.section,
            field_type=p.field_type,
            reference_min_male=p.reference_min_male, reference_max_male=p.reference_max_male,
            reference_min_female=p.reference_min_female, reference_max_female=p.reference_max_female,
            reference_min_default=p.reference_min_default, reference_max_default=p.reference_max_default,
            possible_values=p.possible_values, display_order=p.display_order or i
        )
        db.add(param)

    db.commit()
    return {"message": f"Updated {len(parameters)} parameters"}

@router.put("/tests/{test_id}/parameters/{param_id}", response_model=ParameterResponse)
async def update_parameter(
    test_id: int, param_id: int, data: ParameterCreate,
    current_user: User = Depends(require_permission(Modules.LAB, "write")),
    db: Session = Depends(get_db)
):
    _require_lab_admin(current_user)
    param = db.query(LabTestParameter).filter(
        LabTestParameter.id == param_id, LabTestParameter.test_id == test_id
    ).first()
    if not param:
        raise HTTPException(status_code=404, detail="Parameter not found")

    # Update all fields from data (including nullable fields like section, method)
    update_data = data.dict()
    for field, val in update_data.items():
        setattr(param, field, val)

    db.commit()
    db.refresh(param)
    return param

@router.delete("/tests/{test_id}/parameters/{param_id}")
async def delete_parameter(
    test_id: int, param_id: int,
    current_user: User = Depends(require_permission(Modules.LAB, "delete")),
    db: Session = Depends(get_db)
):
    _require_lab_admin(current_user)
    param = db.query(LabTestParameter).filter(
        LabTestParameter.id == param_id, LabTestParameter.test_id == test_id
    ).first()
    if not param:
        raise HTTPException(status_code=404, detail="Parameter not found")
    db.delete(param)
    db.commit()
    return {"message": "Parameter deleted"}

# ============================================================
# Lab Order Endpoints
# ============================================================

@router.post("/orders", response_model=List[OrderResponse])
async def create_orders(
    data: OrderCreate,
    current_user: User = Depends(require_permission(Modules.LAB, "write")),
    db: Session = Depends(get_db)
):
    """Doctor creates lab orders for a patient"""
    patient = db.query(Patient).filter(
        Patient.id == data.patient_id,
        Patient.hospital_id == current_user.hospital_id
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    orders = []
    for test_id in data.test_ids:
        test = db.query(LabTest).filter(
            LabTest.id == test_id,
            LabTest.hospital_id == current_user.hospital_id,
            LabTest.is_active == True
        ).first()
        if not test:
            raise HTTPException(status_code=404, detail=f"Test ID {test_id} not found")

        order = PatientLabOrder(
            order_number=f"LAB-{str(uuid.uuid4())[:8].upper()}",
            patient_id=data.patient_id,
            test_id=test_id,
            doctor_id=current_user.id,
            appointment_id=data.appointment_id,
            priority=data.priority,
            notes=data.notes,
            status="ordered",
            amount=test.cost or 0.0,
            payment_status="pending"
        )
        db.add(order)
        orders.append(order)

    db.commit()
    return [_build_order_response(o, db) for o in orders]

@router.get("/orders", response_model=List[OrderResponse])
async def list_orders(
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    patient_id: Optional[int] = None,
    appointment_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(PatientLabOrder).join(Patient).filter(
        Patient.hospital_id == current_user.hospital_id
    )

    if status:
        query = query.filter(PatientLabOrder.status == status)
    if patient_id:
        query = query.filter(PatientLabOrder.patient_id == patient_id)
    if appointment_id:
        query = query.filter(PatientLabOrder.appointment_id == appointment_id)
    if date_from:
        query = query.filter(PatientLabOrder.order_date >= date_from)
    if date_to:
        query = query.filter(PatientLabOrder.order_date <= date_to + " 23:59:59")

    # For doctors, only show their orders
    if current_user.has_role('doctor'):
        query = query.filter(PatientLabOrder.doctor_id == current_user.id)

    # Lab technicians only see paid orders (payment gate)
    if current_user.has_role('lab_technician'):
        query = query.filter(PatientLabOrder.payment_status == 'paid')

    orders = query.order_by(PatientLabOrder.order_date.desc()).limit(200).all()
    return [_build_order_response(o, db) for o in orders]

@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    current_user: User = Depends(require_permission(Modules.LAB, "read")),
    db: Session = Depends(get_db)
):
    order = db.query(PatientLabOrder).join(Patient).filter(
        PatientLabOrder.id == order_id,
        Patient.hospital_id == current_user.hospital_id
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return _build_order_response(order, db)

@router.put("/orders/{order_id}/status")
async def update_order_status(
    order_id: int,
    status: str,
    current_user: User = Depends(require_permission(Modules.LAB, "write")),
    db: Session = Depends(get_db)
):
    if status not in ['ordered', 'collected', 'processing', 'completed', 'cancelled']:
        raise HTTPException(status_code=400, detail="Invalid status")

    order = db.query(PatientLabOrder).join(Patient).filter(
        PatientLabOrder.id == order_id,
        Patient.hospital_id == current_user.hospital_id
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = status
    sample_id = None
    if status == "collected":
        order.collection_date = datetime.now()
        # Auto-generate sample ID: S-YYMMDD-NNNN
        if not order.sample_id:
            from sqlalchemy import func as sql_func
            today_prefix = f"S-{datetime.now().strftime('%y%m%d')}-"
            last = db.query(PatientLabOrder).filter(
                PatientLabOrder.sample_id.like(f"{today_prefix}%")
            ).order_by(PatientLabOrder.sample_id.desc()).first()
            if last and last.sample_id:
                try:
                    seq = int(last.sample_id.split('-')[-1]) + 1
                except ValueError:
                    seq = 1
            else:
                seq = 1
            order.sample_id = f"{today_prefix}{seq:04d}"
        sample_id = order.sample_id
    elif status == "completed":
        order.completion_date = datetime.now()

    db.commit()
    return {
        "message": f"Order status updated to {status}",
        "sample_id": sample_id,
        "order_number": order.order_number,
        "patient_name": f"{order.patient.first_name} {order.patient.last_name}" if order.patient else "",
        "test_name": order.test.name if order.test else "",
    }


class LabPaymentUpdate(BaseModel):
    payment_method: str = Field(..., pattern="^(cash|card|upi|cheque|online|insurance)$")
    discount_amount: float = Field(default=0.0, ge=0)
    include_header: bool = True


@router.put("/orders/{order_id}/payment")
async def update_order_payment(
    order_id: int,
    data: LabPaymentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark a lab order as paid. Accessible by receptionist, hospital_admin, super_admin."""
    allowed = ['receptionist', 'hospital_admin', 'super_admin']
    if not any(r in current_user.role_names for r in allowed):
        raise HTTPException(status_code=403, detail="Only reception or admin can collect lab payments")

    order = db.query(PatientLabOrder).join(Patient).filter(
        PatientLabOrder.id == order_id,
        Patient.hospital_id == current_user.hospital_id
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.payment_status == 'paid':
        raise HTTPException(status_code=400, detail="Payment already collected")

    order.payment_status = "paid"
    order.payment_method = data.payment_method
    order.payment_date = datetime.now()

    db.commit()
    return _build_order_response(order, db)


@router.post("/orders/patient/{patient_id}/bill")
async def generate_lab_bill(
    patient_id: int,
    data: LabPaymentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Pay all pending lab orders for a patient and generate a combined PDF bill.
    Uses lab config provider details if available, falls back to hospital info."""
    allowed = ['receptionist', 'hospital_admin', 'super_admin']
    if not any(r in current_user.role_names for r in allowed):
        raise HTTPException(status_code=403, detail="Only reception or admin can generate lab bills")

    # Get pending orders
    orders = db.query(PatientLabOrder).join(Patient).filter(
        PatientLabOrder.patient_id == patient_id,
        Patient.hospital_id == current_user.hospital_id,
        PatientLabOrder.payment_status == "pending",
        PatientLabOrder.status != "cancelled"
    ).order_by(PatientLabOrder.order_date.desc()).all()

    if not orders:
        raise HTTPException(status_code=404, detail="No pending lab orders found")

    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Mark all orders as paid
    for order in orders:
        order.payment_status = "paid"
        order.payment_method = data.payment_method
        order.payment_date = datetime.now()

    db.commit()

    # Build bill data
    items = []
    total = 0.0
    for order in orders:
        test = db.query(LabTest).filter(LabTest.id == order.test_id).first()
        doctor = db.query(User).filter(User.id == order.doctor_id).first() if order.doctor_id else None
        amount = order.amount or (test.cost if test else 0.0)
        total += amount
        items.append({
            "item_name": test.name if test else "Lab Test",
            "item_code": test.test_code if test else "",
            "total_price": amount,
        })

    # Get hospital info
    hospital = db.query(Hospital).filter(Hospital.id == current_user.hospital_id).first()

    # Get lab config
    lab_settings = db.query(HospitalSettings).filter(
        HospitalSettings.setting_category == "lab_config"
    ).all()
    lab_config = {s.setting_key: s.setting_value for s in lab_settings}

    # Use lab provider info if available, fallback to hospital
    provider_name = lab_config.get('provider_name') or (hospital.name if hospital else 'Hospital')
    provider_address = lab_config.get('provider_address') or (hospital.address if hospital else '')
    provider_phone = lab_config.get('provider_phone') or (hospital.phone if hospital else '')
    provider_email = lab_config.get('provider_email') or (hospital.email if hospital else '')

    hospital_info = {
        "name": provider_name,
        "address": provider_address,
        "phone": provider_phone,
        "email": provider_email,
    }

    # Calculate patient age
    age = ""
    if patient.date_of_birth:
        today = date.today()
        age = str(today.year - patient.date_of_birth.year - ((today.month, today.day) < (patient.date_of_birth.month, patient.date_of_birth.day)))

    bill_number = f"LB-{datetime.now().strftime('%Y%m%d%H%M%S')}-{patient_id}"

    bill_data = {
        "bill_number": bill_number,
        "bill_date": datetime.now().isoformat(),
        "patient_name": f"{patient.first_name} {patient.last_name}",
        "patient_age": age,
        "patient_gender": patient.gender,
        "patient_phone": patient.primary_phone or "",
        "reg_no": patient.patient_id,
        "doctor_name": "",
        "payment_method": data.payment_method.capitalize(),
        "items": items,
        "subtotal": total,
        "discount_amount": data.discount_amount,
        "amount_paid": round(total - data.discount_amount, 2),
        "balance_due": 0,
        "prepared_by": f"{current_user.first_name} {current_user.last_name}",
    }

    try:
        pdf_buffer = pdf_service.generate_bill_pdf(bill_data, hospital_info, include_header=data.include_header)
        filename = f"lab_bill_{bill_number}.pdf"
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation error: {str(e)}")


@router.get("/orders/patient/{patient_id}/pending-payment", response_model=List[OrderResponse])
async def get_pending_payment_orders(
    patient_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get lab orders pending payment for a patient. For reception to collect fees."""
    orders = db.query(PatientLabOrder).join(Patient).filter(
        PatientLabOrder.patient_id == patient_id,
        Patient.hospital_id == current_user.hospital_id,
        PatientLabOrder.payment_status == "pending",
        PatientLabOrder.status != "cancelled"
    ).order_by(PatientLabOrder.order_date.desc()).all()
    return [_build_order_response(o, db) for o in orders]

@router.get("/orders/patient/{patient_id}", response_model=List[OrderResponse])
async def get_patient_orders(
    patient_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    orders = db.query(PatientLabOrder).join(Patient).filter(
        PatientLabOrder.patient_id == patient_id,
        Patient.hospital_id == current_user.hospital_id
    ).order_by(PatientLabOrder.order_date.desc()).all()
    return [_build_order_response(o, db) for o in orders]

# ============================================================
# Lab Result Entry (for technicians)
# ============================================================

@router.get("/orders/{order_id}/entry-form")
async def get_entry_form(
    order_id: int,
    current_user: User = Depends(require_permission(Modules.LAB, "read")),
    db: Session = Depends(get_db)
):
    """Get test parameters for result entry form"""
    order = db.query(PatientLabOrder).join(Patient).filter(
        PatientLabOrder.id == order_id,
        Patient.hospital_id == current_user.hospital_id
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    test = db.query(LabTest).filter(LabTest.id == order.test_id).first()
    patient = db.query(Patient).filter(Patient.id == order.patient_id).first()
    params = db.query(LabTestParameter).filter(
        LabTestParameter.test_id == test.id,
        LabTestParameter.is_active == True
    ).order_by(LabTestParameter.display_order).all()

    gender = patient.gender.lower() if patient and patient.gender else None
    age = _calculate_age(patient.date_of_birth) if patient else None

    def _resolve_range(p):
        if p.reference_ranges:
            rmin, rmax, _ = _match_reference_range(p.reference_ranges, gender, age)
            return rmin, rmax
        # Legacy fallback
        if gender == "male" and p.reference_min_male is not None:
            return p.reference_min_male, p.reference_max_male
        if gender == "female" and p.reference_min_female is not None:
            return p.reference_min_female, p.reference_max_female
        return p.reference_min_default, p.reference_max_default

    return {
        "order_id": order.id,
        "order_number": order.order_number,
        "test_name": test.name,
        "test_code": test.test_code,
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else "Unknown",
        "patient_gender": patient.gender if patient else None,
        "parameters": [
            {
                "id": p.id,
                "parameter_name": p.parameter_name,
                "unit": p.unit,
                "field_type": p.field_type,
                "reference_min": _resolve_range(p)[0],
                "reference_max": _resolve_range(p)[1],
                "possible_values": p.possible_values,
                "abnormal_values": p.abnormal_values,
                "normal_value": p.normal_value,
                "notes": p.notes,
                "display_order": p.display_order
            } for p in params
        ]
    }

@router.post("/orders/{order_id}/results")
async def submit_results(
    order_id: int, data: ResultSubmit,
    current_user: User = Depends(require_permission(Modules.LAB, "write")),
    db: Session = Depends(get_db)
):
    """Lab technician submits test results"""
    order = db.query(PatientLabOrder).join(Patient).filter(
        PatientLabOrder.id == order_id,
        Patient.hospital_id == current_user.hospital_id
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status == "completed":
        raise HTTPException(status_code=400, detail="Results already submitted")

    # Check if report already exists
    existing = db.query(LabReport).filter(LabReport.order_id == order_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Report already exists for this order")

    result_values = [{"parameter_id": r.parameter_id, "value": r.value, "remarks": r.remarks or ""} for r in data.results]

    report = LabReport(
        order_id=order_id,
        result_values=result_values,
        interpretation=data.interpretation,
        technician_id=current_user.id,
        report_date=datetime.now()
    )
    db.add(report)

    order.status = "completed"
    order.completion_date = datetime.now()

    db.commit()
    db.refresh(report)

    return {"message": "Results submitted successfully", "report_id": report.id}

@router.put("/reports/{report_id}")
async def update_report(
    report_id: int, data: ResultSubmit,
    current_user: User = Depends(require_permission(Modules.LAB, "write")),
    db: Session = Depends(get_db)
):
    """Update existing lab report"""
    report = db.query(LabReport).filter(LabReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    report.result_values = [{"parameter_id": r.parameter_id, "value": r.value} for r in data.results]
    if data.interpretation is not None:
        report.interpretation = data.interpretation

    db.commit()
    return {"message": "Report updated successfully"}

# ============================================================
# Lab Report Viewing
# ============================================================

@router.get("/reports/patient/{patient_id}", response_model=List[ReportResponse])
async def get_patient_reports(
    patient_id: int,
    current_user: User = Depends(require_permission(Modules.LAB, "read")),
    db: Session = Depends(get_db)
):
    orders = db.query(PatientLabOrder).join(Patient).filter(
        PatientLabOrder.patient_id == patient_id,
        Patient.hospital_id == current_user.hospital_id,
        PatientLabOrder.status == "completed"
    ).all()

    reports = []
    for order in orders:
        report = db.query(LabReport).filter(LabReport.order_id == order.id).first()
        if report:
            reports.append(_build_report_response(report, db))

    return reports

@router.get("/reports/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: int,
    current_user: User = Depends(require_permission(Modules.LAB, "read")),
    db: Session = Depends(get_db)
):
    report = db.query(LabReport).filter(LabReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return _build_report_response(report, db)

@router.get("/reports/{report_id}/download")
async def download_report_pdf(
    report_id: int,
    include_header: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Download lab report as PDF. Accessible by any authenticated user."""
    report = db.query(LabReport).filter(LabReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    report_data = _build_report_response(report, db)

    # Get hospital info (fallback)
    hospital = db.query(Hospital).filter(Hospital.id == current_user.hospital_id).first()
    hospital_info = {
        "name": hospital.name if hospital else "Hospital",
        "address": hospital.address if hospital else "",
        "phone": hospital.phone if hospital else "",
        "email": hospital.email if hospital else "",
        "logo_url": hospital.logo_url if hospital else ""
    }

    # Get lab-specific config from HospitalSettings
    lab_settings = db.query(HospitalSettings).filter(
        HospitalSettings.setting_category == "lab_config"
    ).all()
    lab_config = {s.setting_key: s.setting_value for s in lab_settings}

    try:
        pdf_buffer = pdf_service.generate_lab_report_pdf(report_data, hospital_info, lab_config, include_header=include_header)
        filename = f"lab_report_{report_data['order_number']}_{datetime.now().strftime('%Y%m%d')}.pdf"
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation error: {str(e)}")

@router.get("/reports/package/{package_booking_id}/download")
async def download_package_report_pdf(
    package_booking_id: str,
    include_header: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Download combined PDF for all completed tests in a package booking."""
    orders = db.query(PatientLabOrder).filter(
        PatientLabOrder.package_booking_id == package_booking_id
    ).all()
    if not orders:
        raise HTTPException(status_code=404, detail="No orders found for this package")

    # Collect all completed reports
    reports_data = []
    for order in orders:
        report = db.query(LabReport).filter(LabReport.order_id == order.id).first()
        if report:
            reports_data.append(_build_report_response(report, db))

    if not reports_data:
        raise HTTPException(status_code=404, detail="No completed reports found for this package")

    hospital = db.query(Hospital).filter(Hospital.id == current_user.hospital_id).first()
    hospital_info = {
        "name": hospital.name if hospital else "Hospital",
        "address": hospital.address if hospital else "",
        "phone": hospital.phone if hospital else "",
        "email": hospital.email if hospital else "",
        "logo_url": hospital.logo_url if hospital else ""
    }

    lab_settings = db.query(HospitalSettings).filter(
        HospitalSettings.setting_category == "lab_config"
    ).all()
    lab_config = {s.setting_key: s.setting_value for s in lab_settings}

    try:
        pdf_buffer = pdf_service.generate_combined_lab_report_pdf(
            reports_data, hospital_info, lab_config, include_header=include_header
        )
        pkg_name = orders[0].package.name if orders[0].package else "package"
        patient = db.query(Patient).filter(Patient.id == orders[0].patient_id).first()
        patient_name = f"{patient.first_name}_{patient.last_name}" if patient else "patient"
        filename = f"{patient_name}_{pkg_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"PDF generation error: {str(e)}")

# ============================================================
# Stats & Seed
# ============================================================

@router.get("/stats", response_model=StatsResponse)
async def get_lab_stats(
    current_user: User = Depends(require_permission(Modules.LAB, "read")),
    db: Session = Depends(get_db)
):
    total_tests = db.query(LabTest).filter(
        LabTest.hospital_id == current_user.hospital_id, LabTest.is_active == True
    ).count()
    total_categories = db.query(LabTestCategory).filter(
        LabTestCategory.hospital_id == current_user.hospital_id, LabTestCategory.is_active == True
    ).count()
    total_orders = db.query(PatientLabOrder).join(Patient).filter(
        Patient.hospital_id == current_user.hospital_id
    ).count()
    pending_orders = db.query(PatientLabOrder).join(Patient).filter(
        Patient.hospital_id == current_user.hospital_id,
        PatientLabOrder.status.in_(["ordered", "collected", "processing"])
    ).count()
    today = date.today()
    completed_today = db.query(PatientLabOrder).join(Patient).filter(
        Patient.hospital_id == current_user.hospital_id,
        PatientLabOrder.status == "completed",
        sqlfunc.date(PatientLabOrder.completion_date) == today
    ).count()

    return {
        "total_tests": total_tests,
        "total_categories": total_categories,
        "total_orders": total_orders,
        "pending_orders": pending_orders,
        "completed_today": completed_today
    }

@router.get("/tests/{test_id}/sample-report")
async def generate_sample_report(
    test_id: int,
    include_header: bool = True,
    current_user: User = Depends(require_permission(Modules.LAB, "read")),
    db: Session = Depends(get_db)
):
    """Generate a sample/blank lab report PDF for a test to preview the report layout."""
    test = db.query(LabTest).filter(
        LabTest.id == test_id, LabTest.hospital_id == current_user.hospital_id
    ).first()
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    params = db.query(LabTestParameter).filter(
        LabTestParameter.test_id == test_id, LabTestParameter.is_active == True
    ).order_by(LabTestParameter.display_order).all()

    # Build sample report data
    sample_results = []
    for p in params:
        ref_min = p.reference_min_default
        ref_max = p.reference_max_default
        # Use a sample value in the middle of the range if numeric
        sample_value = ""
        if p.field_type == "numeric" and ref_min is not None and ref_max is not None:
            sample_value = str(round((ref_min + ref_max) / 2, 2))
        elif p.field_type == "select" and p.possible_values:
            sample_value = p.possible_values[0] if isinstance(p.possible_values, list) else ""
        else:
            sample_value = "—"

        sample_results.append({
            "parameter_name": p.parameter_name,
            "value": sample_value,
            "unit": p.unit or "",
            "method": p.method or "",
            "section": p.section or "",
            "reference_min": ref_min,
            "reference_max": ref_max,
            "is_abnormal": False,
            "field_type": p.field_type,
        })

    report_data = {
        "test_name": test.name,
        "test_code": test.test_code,
        "method": test.method or "",
        "patient_name": "SAMPLE PATIENT",
        "patient_gender": "Male",
        "patient_age": 30,
        "doctor_name": "Dr. Sample Doctor",
        "order_number": "SAMPLE-001",
        "report_date": datetime.now().isoformat(),
        "results": sample_results,
        "interpretation": "This is a sample report for preview purposes only.",
    }

    # Get hospital info
    hospital = db.query(Hospital).filter(Hospital.id == current_user.hospital_id).first()
    hospital_info = {
        "name": hospital.name if hospital else "Hospital",
        "address": hospital.address if hospital else "",
        "phone": hospital.phone if hospital else "",
        "email": hospital.email if hospital else "",
    }

    # Get lab config
    lab_config = {}
    settings = db.query(HospitalSettings).filter(
        HospitalSettings.setting_category == "lab_config"
    ).all()
    for s in settings:
        lab_config[s.setting_key] = s.setting_value

    try:
        pdf_buffer = pdf_service.generate_lab_report_pdf(report_data, hospital_info, lab_config, include_header=include_header)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=sample_report_{test.test_code}.pdf"}
    )


# ============================================================
# Package Categories
# ============================================================

def _build_package_response(pkg: LabTestPackage, db) -> dict:
    category = db.query(LabTestPackageCategory).filter(LabTestPackageCategory.id == pkg.category_id).first()
    items = db.query(LabTestPackageItem).filter(LabTestPackageItem.package_id == pkg.id).all()
    tests = []
    for item in items:
        test = db.query(LabTest).filter(LabTest.id == item.test_id).first()
        if test:
            tests.append({
                "id": test.id,
                "test_code": test.test_code,
                "name": test.name,
                "cost": test.cost,
                "sample_type": test.sample_type,
            })
    discount_pct = round((1 - pkg.package_price / pkg.actual_price) * 100, 1) if pkg.actual_price > 0 else 0
    return {
        "id": pkg.id,
        "package_code": pkg.package_code,
        "name": pkg.name,
        "description": pkg.description,
        "category_id": pkg.category_id,
        "category_name": category.name if category else None,
        "package_price": pkg.package_price,
        "actual_price": pkg.actual_price,
        "discount_percentage": discount_pct,
        "is_active": pkg.is_active,
        "tests": tests,
    }


@router.get("/packages/categories", response_model=List[PackageCategoryResponse])
async def list_package_categories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    cats = db.query(LabTestPackageCategory).filter(
        LabTestPackageCategory.hospital_id == current_user.hospital_id
    ).order_by(LabTestPackageCategory.name).all()
    result = []
    for c in cats:
        count = db.query(sqlfunc.count(LabTestPackage.id)).filter(
            LabTestPackage.category_id == c.id, LabTestPackage.is_active == True
        ).scalar() or 0
        result.append({
            "id": c.id, "name": c.name, "description": c.description,
            "is_active": c.is_active, "package_count": count,
        })
    return result


@router.post("/packages/categories", response_model=PackageCategoryResponse)
async def create_package_category(
    data: PackageCategoryCreate,
    current_user: User = Depends(require_permission(Modules.LAB, "write")),
    db: Session = Depends(get_db)
):
    _require_lab_admin(current_user)
    cat = LabTestPackageCategory(
        name=data.name, description=data.description,
        hospital_id=current_user.hospital_id
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return {"id": cat.id, "name": cat.name, "description": cat.description,
            "is_active": cat.is_active, "package_count": 0}


@router.put("/packages/categories/{cat_id}", response_model=PackageCategoryResponse)
async def update_package_category(
    cat_id: int,
    data: PackageCategoryCreate,
    current_user: User = Depends(require_permission(Modules.LAB, "write")),
    db: Session = Depends(get_db)
):
    _require_lab_admin(current_user)
    cat = db.query(LabTestPackageCategory).filter(
        LabTestPackageCategory.id == cat_id,
        LabTestPackageCategory.hospital_id == current_user.hospital_id
    ).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Package category not found")
    cat.name = data.name
    cat.description = data.description
    db.commit()
    count = db.query(sqlfunc.count(LabTestPackage.id)).filter(
        LabTestPackage.category_id == cat.id, LabTestPackage.is_active == True
    ).scalar() or 0
    return {"id": cat.id, "name": cat.name, "description": cat.description,
            "is_active": cat.is_active, "package_count": count}


@router.delete("/packages/categories/{cat_id}")
async def delete_package_category(
    cat_id: int,
    current_user: User = Depends(require_permission(Modules.LAB, "delete")),
    db: Session = Depends(get_db)
):
    _require_lab_admin(current_user)
    cat = db.query(LabTestPackageCategory).filter(
        LabTestPackageCategory.id == cat_id,
        LabTestPackageCategory.hospital_id == current_user.hospital_id
    ).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Package category not found")
    cat.is_active = False
    db.commit()
    return {"message": "Package category deactivated"}


# ============================================================
# Packages CRUD
# ============================================================

@router.get("/packages", response_model=List[PackageResponse])
async def list_packages(
    category_id: Optional[int] = None,
    search: Optional[str] = None,
    active_only: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    q = db.query(LabTestPackage).filter(LabTestPackage.hospital_id == current_user.hospital_id)
    if active_only:
        q = q.filter(LabTestPackage.is_active == True)
    if category_id:
        q = q.filter(LabTestPackage.category_id == category_id)
    if search:
        q = q.filter(LabTestPackage.name.ilike(f"%{search}%"))
    packages = q.order_by(LabTestPackage.name).all()
    return [_build_package_response(p, db) for p in packages]


@router.get("/packages/{pkg_id}", response_model=PackageResponse)
async def get_package(
    pkg_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    pkg = db.query(LabTestPackage).filter(
        LabTestPackage.id == pkg_id,
        LabTestPackage.hospital_id == current_user.hospital_id
    ).first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    return _build_package_response(pkg, db)


@router.post("/packages", response_model=PackageResponse)
async def create_package(
    data: PackageCreate,
    current_user: User = Depends(require_permission(Modules.LAB, "write")),
    db: Session = Depends(get_db)
):
    _require_lab_admin(current_user)
    # Validate category
    cat = db.query(LabTestPackageCategory).filter(
        LabTestPackageCategory.id == data.category_id,
        LabTestPackageCategory.hospital_id == current_user.hospital_id
    ).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Package category not found")

    # Validate tests and compute actual price
    actual_price = 0.0
    tests = []
    for tid in data.test_ids:
        test = db.query(LabTest).filter(
            LabTest.id == tid, LabTest.hospital_id == current_user.hospital_id, LabTest.is_active == True
        ).first()
        if not test:
            raise HTTPException(status_code=404, detail=f"Test ID {tid} not found or inactive")
        actual_price += test.cost
        tests.append(test)

    pkg = LabTestPackage(
        package_code=data.package_code, name=data.name, description=data.description,
        category_id=data.category_id, package_price=data.package_price,
        actual_price=actual_price, hospital_id=current_user.hospital_id
    )
    db.add(pkg)
    db.flush()

    for test in tests:
        db.add(LabTestPackageItem(package_id=pkg.id, test_id=test.id))
    db.commit()
    db.refresh(pkg)
    return _build_package_response(pkg, db)


@router.put("/packages/{pkg_id}", response_model=PackageResponse)
async def update_package(
    pkg_id: int,
    data: PackageUpdate,
    current_user: User = Depends(require_permission(Modules.LAB, "write")),
    db: Session = Depends(get_db)
):
    _require_lab_admin(current_user)
    pkg = db.query(LabTestPackage).filter(
        LabTestPackage.id == pkg_id,
        LabTestPackage.hospital_id == current_user.hospital_id
    ).first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")

    if data.package_code is not None:
        pkg.package_code = data.package_code
    if data.name is not None:
        pkg.name = data.name
    if data.description is not None:
        pkg.description = data.description
    if data.category_id is not None:
        pkg.category_id = data.category_id
    if data.is_active is not None:
        pkg.is_active = data.is_active
    if data.package_price is not None:
        pkg.package_price = data.package_price

    # Update test list if provided
    if data.test_ids is not None:
        actual_price = 0.0
        for tid in data.test_ids:
            test = db.query(LabTest).filter(
                LabTest.id == tid, LabTest.hospital_id == current_user.hospital_id, LabTest.is_active == True
            ).first()
            if not test:
                raise HTTPException(status_code=404, detail=f"Test ID {tid} not found or inactive")
            actual_price += test.cost
        pkg.actual_price = actual_price
        # Replace items
        db.query(LabTestPackageItem).filter(LabTestPackageItem.package_id == pkg.id).delete()
        for tid in data.test_ids:
            db.add(LabTestPackageItem(package_id=pkg.id, test_id=tid))

    db.commit()
    db.refresh(pkg)
    return _build_package_response(pkg, db)


@router.delete("/packages/{pkg_id}")
async def delete_package(
    pkg_id: int,
    current_user: User = Depends(require_permission(Modules.LAB, "delete")),
    db: Session = Depends(get_db)
):
    _require_lab_admin(current_user)
    pkg = db.query(LabTestPackage).filter(
        LabTestPackage.id == pkg_id,
        LabTestPackage.hospital_id == current_user.hospital_id
    ).first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    pkg.is_active = False
    db.commit()
    return {"message": "Package deactivated"}


# ============================================================
# Package Booking
# ============================================================

@router.post("/packages/{pkg_id}/book")
async def book_package(
    pkg_id: int,
    data: PackageBooking,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Book a test package for a patient. Creates individual lab orders, marks as paid, returns bill PDF."""
    allowed = ['receptionist', 'hospital_admin', 'super_admin']
    if not any(r in current_user.role_names for r in allowed):
        raise HTTPException(status_code=403, detail="Only reception or admin can book packages")

    # Validate package
    pkg = db.query(LabTestPackage).filter(
        LabTestPackage.id == pkg_id,
        LabTestPackage.hospital_id == current_user.hospital_id,
        LabTestPackage.is_active == True
    ).first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found or inactive")

    # Validate patient
    patient = db.query(Patient).filter(
        Patient.id == data.patient_id,
        Patient.hospital_id == current_user.hospital_id
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Get package tests
    items = db.query(LabTestPackageItem).filter(LabTestPackageItem.package_id == pkg.id).all()
    if not items:
        raise HTTPException(status_code=400, detail="Package has no tests")

    tests = []
    for item in items:
        test = db.query(LabTest).filter(LabTest.id == item.test_id).first()
        if test:
            tests.append(test)

    if not tests:
        raise HTTPException(status_code=400, detail="No valid tests in package")

    # Proportional discount distribution
    booking_id = f"PKG-{str(uuid.uuid4())[:8].upper()}"
    now = datetime.now()
    orders = []
    distributed_total = 0.0

    for i, test in enumerate(tests):
        if i == len(tests) - 1:
            # Last test gets the remainder to avoid floating-point rounding
            amount = round(pkg.package_price - distributed_total, 2)
        else:
            amount = round((test.cost / pkg.actual_price) * pkg.package_price, 2)
            distributed_total += amount

        order = PatientLabOrder(
            order_number=f"LAB-{str(uuid.uuid4())[:8].upper()}",
            patient_id=data.patient_id,
            test_id=test.id,
            doctor_id=None,
            package_id=pkg.id,
            package_booking_id=booking_id,
            referred_by=data.referred_by,
            priority=data.priority,
            notes=data.notes,
            status="ordered",
            amount=amount,
            payment_status="paid",
            payment_method=data.payment_method,
            payment_date=now,
        )
        db.add(order)
        orders.append(order)

    db.commit()

    # Build bill PDF — single line for the package
    bill_items = [{
        "item_name": pkg.name,
        "item_code": pkg.package_code,
        "total_price": pkg.actual_price,
    }]

    hospital = db.query(Hospital).filter(Hospital.id == current_user.hospital_id).first()
    lab_settings = db.query(HospitalSettings).filter(
        HospitalSettings.setting_category == "lab_config"
    ).all()
    lab_config = {s.setting_key: s.setting_value for s in lab_settings}

    hospital_info = {
        "name": lab_config.get('provider_name') or (hospital.name if hospital else 'Hospital'),
        "address": lab_config.get('provider_address') or (hospital.address if hospital else ''),
        "phone": lab_config.get('provider_phone') or (hospital.phone if hospital else ''),
        "email": lab_config.get('provider_email') or (hospital.email if hospital else ''),
    }

    age = ""
    if patient.date_of_birth:
        today = date.today()
        age = str(today.year - patient.date_of_birth.year - ((today.month, today.day) < (patient.date_of_birth.month, patient.date_of_birth.day)))

    discount = round(pkg.actual_price - pkg.package_price, 2)
    bill_number = f"PKG-{now.strftime('%Y%m%d%H%M%S')}-{data.patient_id}"

    bill_data = {
        "bill_number": bill_number,
        "bill_date": now.isoformat(),
        "patient_name": f"{patient.first_name} {patient.last_name}",
        "patient_age": age,
        "patient_gender": patient.gender,
        "patient_phone": patient.primary_phone or "",
        "reg_no": patient.patient_id,
        "doctor_name": "",
        "payment_method": data.payment_method.capitalize(),
        "items": bill_items,
        "subtotal": pkg.actual_price,
        "discount_amount": discount,
        "amount_paid": pkg.package_price,
        "balance_due": 0,
        "prepared_by": f"{current_user.first_name} {current_user.last_name}",
        "package_name": pkg.name,
    }

    try:
        pdf_buffer = pdf_service.generate_bill_pdf(bill_data, hospital_info, include_header=data.include_header)
        filename = f"lab_package_bill_{bill_number}.pdf"
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"PDF generation error: {str(e)}")


@router.post("/seed-defaults")
async def seed_default_tests(
    current_user: User = Depends(require_permission(Modules.LAB, "write")),
    db: Session = Depends(get_db)
):
    """Seed default lab tests with parameters for the hospital"""
    _require_lab_admin(current_user)
    hospital_id = current_user.hospital_id

    # Check if already seeded
    existing = db.query(LabTest).filter(LabTest.hospital_id == hospital_id).count()
    if existing > 0:
        raise HTTPException(status_code=400, detail="Lab tests already exist for this hospital. Delete existing tests first or add manually.")

    seed_data = _get_seed_data()
    created_tests = 0

    for cat_name, tests in seed_data.items():
        cat = LabTestCategory(name=cat_name, hospital_id=hospital_id)
        db.add(cat)
        db.flush()

        for test_info in tests:
            test = LabTest(
                test_code=test_info["code"], name=test_info["name"],
                description=test_info.get("description", ""),
                category_id=cat.id, cost=test_info.get("cost", 0),
                sample_type=test_info.get("sample_type", "Blood"),
                preparation_instructions=test_info.get("instructions", ""),
                hospital_id=hospital_id
            )
            db.add(test)
            db.flush()

            for i, param in enumerate(test_info.get("parameters", [])):
                p = LabTestParameter(
                    test_id=test.id,
                    parameter_name=param["name"],
                    unit=param.get("unit"),
                    field_type=param.get("field_type", "numeric"),
                    reference_min_male=param.get("min_m"),
                    reference_max_male=param.get("max_m"),
                    reference_min_female=param.get("min_f"),
                    reference_max_female=param.get("max_f"),
                    reference_min_default=param.get("min_d"),
                    reference_max_default=param.get("max_d"),
                    possible_values=param.get("possible_values"),
                    display_order=i
                )
                db.add(p)
            created_tests += 1

    db.commit()
    return {"message": f"Seeded {created_tests} lab tests with parameters"}


def _get_seed_data():
    return {
        "Hematology": [
            {
                "code": "CBC", "name": "Complete Blood Count (CBC)",
                "description": "Measures different components of blood",
                "cost": 350, "sample_type": "Blood (EDTA)", "instructions": "No special preparation",
                "parameters": [
                    {"name": "Hemoglobin", "unit": "g/dL", "min_m": 13.0, "max_m": 17.0, "min_f": 12.0, "max_f": 16.0},
                    {"name": "RBC Count", "unit": "million/µL", "min_m": 4.5, "max_m": 5.5, "min_f": 4.0, "max_f": 5.0},
                    {"name": "WBC Count", "unit": "cells/µL", "min_d": 4000, "max_d": 11000},
                    {"name": "Platelet Count", "unit": "lakh/µL", "min_d": 1.5, "max_d": 4.0},
                    {"name": "PCV / Hematocrit", "unit": "%", "min_m": 40, "max_m": 50, "min_f": 36, "max_f": 44},
                    {"name": "MCV", "unit": "fL", "min_d": 80, "max_d": 100},
                    {"name": "MCH", "unit": "pg", "min_d": 27, "max_d": 33},
                    {"name": "MCHC", "unit": "g/dL", "min_d": 32, "max_d": 36},
                    {"name": "ESR", "unit": "mm/hr", "min_m": 0, "max_m": 15, "min_f": 0, "max_f": 20},
                ]
            },
        ],
        "Biochemistry": [
            {
                "code": "LFT", "name": "Liver Function Test (LFT)",
                "description": "Assesses liver health",
                "cost": 600, "sample_type": "Blood (Serum)", "instructions": "Fasting 8-12 hours preferred",
                "parameters": [
                    {"name": "Total Bilirubin", "unit": "mg/dL", "min_d": 0.1, "max_d": 1.2},
                    {"name": "Direct Bilirubin", "unit": "mg/dL", "min_d": 0.0, "max_d": 0.3},
                    {"name": "Indirect Bilirubin", "unit": "mg/dL", "min_d": 0.1, "max_d": 0.9},
                    {"name": "SGOT (AST)", "unit": "U/L", "min_d": 5, "max_d": 40},
                    {"name": "SGPT (ALT)", "unit": "U/L", "min_d": 7, "max_d": 56},
                    {"name": "Alkaline Phosphatase (ALP)", "unit": "U/L", "min_d": 44, "max_d": 147},
                    {"name": "Total Protein", "unit": "g/dL", "min_d": 6.0, "max_d": 8.3},
                    {"name": "Albumin", "unit": "g/dL", "min_d": 3.5, "max_d": 5.5},
                    {"name": "Globulin", "unit": "g/dL", "min_d": 2.0, "max_d": 3.5},
                ]
            },
            {
                "code": "RFT", "name": "Renal Function Test (RFT)",
                "description": "Evaluates kidney function",
                "cost": 500, "sample_type": "Blood (Serum)", "instructions": "Fasting 8-12 hours preferred",
                "parameters": [
                    {"name": "Blood Urea", "unit": "mg/dL", "min_d": 15, "max_d": 40},
                    {"name": "Serum Creatinine", "unit": "mg/dL", "min_m": 0.7, "max_m": 1.3, "min_f": 0.6, "max_f": 1.1},
                    {"name": "Uric Acid", "unit": "mg/dL", "min_m": 3.5, "max_m": 7.2, "min_f": 2.6, "max_f": 6.0},
                    {"name": "BUN", "unit": "mg/dL", "min_d": 7, "max_d": 20},
                    {"name": "Sodium", "unit": "mEq/L", "min_d": 136, "max_d": 145},
                    {"name": "Potassium", "unit": "mEq/L", "min_d": 3.5, "max_d": 5.1},
                    {"name": "Chloride", "unit": "mEq/L", "min_d": 98, "max_d": 106},
                ]
            },
            {
                "code": "LIPID", "name": "Lipid Profile",
                "description": "Measures cholesterol and triglyceride levels",
                "cost": 500, "sample_type": "Blood (Serum)", "instructions": "Fasting 12 hours required",
                "parameters": [
                    {"name": "Total Cholesterol", "unit": "mg/dL", "min_d": 0, "max_d": 200},
                    {"name": "Triglycerides", "unit": "mg/dL", "min_d": 0, "max_d": 150},
                    {"name": "HDL Cholesterol", "unit": "mg/dL", "min_m": 40, "max_m": 999, "min_f": 50, "max_f": 999},
                    {"name": "LDL Cholesterol", "unit": "mg/dL", "min_d": 0, "max_d": 100},
                    {"name": "VLDL Cholesterol", "unit": "mg/dL", "min_d": 5, "max_d": 40},
                ]
            },
        ],
        "Thyroid": [
            {
                "code": "THYROID", "name": "Thyroid Profile",
                "description": "Evaluates thyroid gland function",
                "cost": 700, "sample_type": "Blood (Serum)", "instructions": "No special preparation",
                "parameters": [
                    {"name": "T3 (Triiodothyronine)", "unit": "ng/dL", "min_d": 80, "max_d": 200},
                    {"name": "T4 (Thyroxine)", "unit": "µg/dL", "min_d": 4.5, "max_d": 12.5},
                    {"name": "TSH", "unit": "µIU/mL", "min_d": 0.4, "max_d": 4.0},
                ]
            },
        ],
        "Blood Sugar": [
            {
                "code": "FBS", "name": "Fasting Blood Sugar",
                "description": "Measures blood glucose after fasting",
                "cost": 100, "sample_type": "Blood (Fluoride)", "instructions": "Fasting 8-12 hours required",
                "parameters": [
                    {"name": "Fasting Blood Glucose", "unit": "mg/dL", "min_d": 70, "max_d": 100},
                ]
            },
            {
                "code": "PPBS", "name": "Post Prandial Blood Sugar",
                "description": "Measures blood glucose 2 hours after eating",
                "cost": 100, "sample_type": "Blood (Fluoride)", "instructions": "2 hours after meal",
                "parameters": [
                    {"name": "PP Blood Glucose", "unit": "mg/dL", "min_d": 70, "max_d": 140},
                ]
            },
            {
                "code": "RBS", "name": "Random Blood Sugar",
                "description": "Random blood glucose measurement",
                "cost": 80, "sample_type": "Blood (Fluoride)", "instructions": "No special preparation",
                "parameters": [
                    {"name": "Random Blood Glucose", "unit": "mg/dL", "min_d": 70, "max_d": 140},
                ]
            },
            {
                "code": "HBA1C", "name": "Glycated Hemoglobin (HbA1c)",
                "description": "Average blood sugar over 2-3 months",
                "cost": 450, "sample_type": "Blood (EDTA)", "instructions": "No special preparation",
                "parameters": [
                    {"name": "HbA1c", "unit": "%", "min_d": 4.0, "max_d": 5.6},
                ]
            },
        ],
        "Urine Analysis": [
            {
                "code": "URINE-R", "name": "Urine Routine & Microscopy",
                "description": "Physical, chemical and microscopic examination of urine",
                "cost": 150, "sample_type": "Urine (Mid-stream)", "instructions": "Mid-stream clean catch sample",
                "parameters": [
                    {"name": "Color", "unit": None, "field_type": "text"},
                    {"name": "Appearance", "unit": None, "field_type": "select", "possible_values": ["Clear", "Slightly Turbid", "Turbid"]},
                    {"name": "pH", "unit": None, "min_d": 4.5, "max_d": 8.0},
                    {"name": "Specific Gravity", "unit": None, "min_d": 1.005, "max_d": 1.030},
                    {"name": "Protein", "unit": None, "field_type": "select", "possible_values": ["Nil", "Trace", "+", "++", "+++"]},
                    {"name": "Glucose", "unit": None, "field_type": "select", "possible_values": ["Nil", "Trace", "+", "++", "+++"]},
                    {"name": "Ketones", "unit": None, "field_type": "select", "possible_values": ["Nil", "Trace", "+", "++", "+++"]},
                    {"name": "RBC", "unit": "/HPF", "min_d": 0, "max_d": 2},
                    {"name": "Pus Cells (WBC)", "unit": "/HPF", "min_d": 0, "max_d": 5},
                    {"name": "Epithelial Cells", "unit": "/HPF", "field_type": "select", "possible_values": ["Few", "Moderate", "Many"]},
                ]
            },
        ],
    }
