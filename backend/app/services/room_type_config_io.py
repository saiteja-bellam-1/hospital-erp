"""Export and import room-type configuration.

The workbook has two data sheets:

* Nursing rates — default nursing charge per day for each room type
* Doctor room rates — per-doctor visit-rate overrides by room type

A guided-setup file with a single Data sheet is accepted too. Blank nursing
charges are left unchanged. Rows that are absent from the file are not deleted.
"""
from __future__ import annotations

import io
from typing import Optional

from sqlalchemy.orm import Session

from app.models.inpatient import DoctorRoomTypeRate, RoomTypeRateConfig
from app.models.user import User, UserRole
from app.services.onboarding_import import (
    RowError,
    _cell_float,
    _cell_str,
    _row_empty,
    read_csv_or_xlsx,
)
from app.services.room_type_catalog import ensure_room_type, list_room_types

ROOM_TYPE_LABELS = {
    "general": "General Ward",
    "semi_private": "Semi-Private",
    "private": "Private",
    "suite": "Suite / Deluxe",
    "icu": "ICU",
    "hdu": "HDU / Step-Down",
    "nicu": "NICU",
    "picu": "PICU",
    "isolation": "Isolation",
    "labour": "Labour & Delivery",
    "recovery": "Post-Op Recovery",
    "daycare": "Day Care",
    "emergency": "Emergency / Casualty",
    "operation": "Operation Theatre",
}

NURSING_SHEET = "Nursing rates"
DOCTOR_SHEET = "Doctor room rates"
NURSING_HEADERS = ["room_type", "room_type_label", "nursing_charge_per_visit"]
DOCTOR_HEADERS = ["doctor_username", "doctor_name", "room_type", "visit_rate"]


def _is_doctor(user: User, doctor_role_id: Optional[int]) -> bool:
    if doctor_role_id and user.role_id == doctor_role_id:
        return True
    return "doctor" in {name.lower() for name in (user.role_names or [])}


def _classify(rows: list[dict]) -> Optional[str]:
    if not rows:
        return None
    keys = set(rows[0].keys()) - {"_row"}
    if "doctor_username" in keys and "visit_rate" in keys:
        return "doctor"
    if "room_type" in keys and "nursing_charge_per_visit" in keys:
        return "nursing"
    return None


def _collect_sheets(content: bytes, filename: str) -> tuple[list[dict], list[dict]]:
    sheets = read_csv_or_xlsx(
        content,
        filename,
        [NURSING_SHEET, DOCTOR_SHEET, "Data"],
    )
    nursing: list[dict] = []
    doctor: list[dict] = []
    for name in (NURSING_SHEET, DOCTOR_SHEET, "Data"):
        rows = sheets.get(name) or []
        kind = _classify(rows)
        if kind == "nursing" and not nursing:
            nursing = rows
        elif kind == "doctor" and not doctor:
            doctor = rows
    if not nursing and not doctor:
        raise ValueError(
            "No room type configuration found. Use the Nursing rates and "
            "Doctor room rates sheets from an export, or a CSV with "
            "room_type and nursing_charge_per_visit."
        )
    return nursing, doctor


def build_room_type_config_xlsx(db: Session, hospital_id: int) -> bytes:
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    workbook = openpyxl.Workbook()
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="2563EB")

    nursing_sheet = workbook.active
    nursing_sheet.title = NURSING_SHEET
    nursing_sheet.append(NURSING_HEADERS)
    existing = {
        row.room_type: row
        for row in db.query(RoomTypeRateConfig).filter(
            RoomTypeRateConfig.hospital_id == hospital_id
        ).all()
    }
    for room_type_row in list_room_types(db, hospital_id):
        row = existing.get(room_type_row.key)
        charge = None
        if row is not None and row.nursing_charge_per_visit is not None:
            charge = float(row.nursing_charge_per_visit)
        nursing_sheet.append([
            room_type_row.key,
            room_type_row.label,
            charge,
        ])

    doctor_sheet = workbook.create_sheet(DOCTOR_SHEET)
    doctor_sheet.append(DOCTOR_HEADERS)
    rates = (
        db.query(DoctorRoomTypeRate, User)
        .join(User, User.id == DoctorRoomTypeRate.doctor_id)
        .filter(
            DoctorRoomTypeRate.hospital_id == hospital_id,
            User.is_active.is_(True),
        )
        .order_by(User.username, DoctorRoomTypeRate.room_type)
        .all()
    )
    for rate, doctor in rates:
        doctor_sheet.append([
            doctor.username,
            f"{doctor.first_name or ''} {doctor.last_name or ''}".strip(),
            rate.room_type,
            float(rate.visit_rate),
        ])

    notes = workbook.create_sheet("Instructions")
    notes.append(["KT HEALTH ERP — Room type configuration"])
    notes["A1"].font = Font(bold=True, size=14)
    notes.append([])
    for line in (
        "Nursing rates: default nursing charge per day for a room type.",
        "Leave nursing_charge_per_visit blank to keep the current value.",
        "Doctor room rates: override a doctor's inpatient fee for one room type.",
        "doctor_username must match an active doctor. doctor_name is ignored on import.",
        "A room type name that is not in the catalog is created automatically.",
        "Import updates matching rows. Rates missing from the file are kept.",
        "A CSV may contain either the nursing columns or the doctor columns, not both.",
    ):
        notes.append([line])

    for sheet in (nursing_sheet, doctor_sheet):
        for cell in sheet[1]:
            cell.font = header_font
            cell.fill = header_fill
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for column in sheet.columns:
            letter = column[0].column_letter
            width = max(len(str(cell.value or "")) for cell in column)
            sheet.column_dimensions[letter].width = min(42, max(16, width + 2))
    notes.column_dimensions["A"].width = 110

    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def import_room_type_config(
    db: Session,
    hospital_id: int,
    content: bytes,
    filename: str,
) -> dict:
    nursing_rows, doctor_rows = _collect_sheets(content, filename)
    errors: list[RowError] = []
    nursing_updated = 0
    doctor_upserted = 0

    for row in nursing_rows:
        if _row_empty(row):
            continue
        line = row.get("_row", 0)
        room_type = (_cell_str(row.get("room_type")) or "").lower()
        try:
            rate = _cell_float(row.get("nursing_charge_per_visit"), field="nursing_charge_per_visit")
        except ValueError as exc:
            errors.append(RowError(NURSING_SHEET, line, str(exc)))
            continue
        if not room_type:
            if rate is None:
                continue
            errors.append(RowError(NURSING_SHEET, line, "room_type is required"))
            continue
        try:
            room_type = ensure_room_type(db, hospital_id, room_type)
        except ValueError as exc:
            errors.append(RowError(NURSING_SHEET, line, str(exc)))
            continue
        if rate is None:
            continue
        if rate < 0:
            errors.append(RowError(NURSING_SHEET, line, "nursing_charge_per_visit cannot be negative"))
            continue
        existing = (
            db.query(RoomTypeRateConfig)
            .filter(
                RoomTypeRateConfig.hospital_id == hospital_id,
                RoomTypeRateConfig.room_type == room_type,
            )
            .first()
        )
        if existing:
            existing.nursing_charge_per_visit = rate
        else:
            db.add(RoomTypeRateConfig(
                hospital_id=hospital_id,
                room_type=room_type,
                nursing_charge_per_visit=rate,
            ))
        nursing_updated += 1

    users_by_username = {
        (user.username or "").lower(): user
        for user in db.query(User).filter(
            User.hospital_id == hospital_id,
            User.is_active.is_(True),
        ).all()
    }
    doctor_role = db.query(UserRole).filter(UserRole.name == "doctor").first()
    doctor_role_id = doctor_role.id if doctor_role else None

    for row in doctor_rows:
        if _row_empty(row):
            continue
        line = row.get("_row", 0)
        username = (_cell_str(row.get("doctor_username")) or "").lower()
        room_type = (_cell_str(row.get("room_type")) or "").lower()
        try:
            visit_rate = _cell_float(row.get("visit_rate"), field="visit_rate")
        except ValueError as exc:
            errors.append(RowError(DOCTOR_SHEET, line, str(exc)))
            continue
        if not username and not room_type and visit_rate is None:
            continue
        doctor = users_by_username.get(username)
        if not doctor:
            errors.append(RowError(DOCTOR_SHEET, line, f"Unknown doctor_username '{username}'"))
            continue
        if not _is_doctor(doctor, doctor_role_id):
            errors.append(RowError(DOCTOR_SHEET, line, f"User '{username}' is not a doctor"))
            continue
        try:
            room_type = ensure_room_type(db, hospital_id, room_type)
        except ValueError as exc:
            errors.append(RowError(DOCTOR_SHEET, line, str(exc)))
            continue
        if visit_rate is None:
            errors.append(RowError(DOCTOR_SHEET, line, "visit_rate is required"))
            continue
        if visit_rate < 0:
            errors.append(RowError(DOCTOR_SHEET, line, "visit_rate cannot be negative"))
            continue
        existing = (
            db.query(DoctorRoomTypeRate)
            .filter(
                DoctorRoomTypeRate.hospital_id == hospital_id,
                DoctorRoomTypeRate.doctor_id == doctor.id,
                DoctorRoomTypeRate.room_type == room_type,
            )
            .first()
        )
        if existing:
            existing.visit_rate = visit_rate
        else:
            db.add(DoctorRoomTypeRate(
                hospital_id=hospital_id,
                doctor_id=doctor.id,
                room_type=room_type,
                visit_rate=visit_rate,
            ))
        doctor_upserted += 1

    if errors:
        db.rollback()
        return {
            "ok": False,
            "nursing_updated": 0,
            "doctor_rates_upserted": 0,
            "errors": [err.as_dict() for err in errors],
        }

    db.commit()
    return {
        "ok": True,
        "nursing_updated": nursing_updated,
        "doctor_rates_upserted": doctor_upserted,
        "errors": [],
    }
