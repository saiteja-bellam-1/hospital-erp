"""End-to-end check that LabTest.description renders in the report PDF as
the "Reference Information" block beneath Interpretation.

The user reported "I'm unable to see the reference section for new reports
I've generated now." This test recreates the full path: create a test with a
description, book an order, submit results with an interpretation, download
the PDF, and assert the description text and the section heading appear in
the rendered PDF bytes (as a plain-text fallback inside the PDF stream).
"""
from datetime import datetime
import io
import re

import pytest

from app.models.lab import (
    LabTestCategory, LabTest, LabTestParameter, PatientLabOrder, LabReport,
)
from app.models.user import UserRole, User
from app.utils.auth import create_access_token


DESCRIPTION_TEXT = "RefSectTest123 — body of the description that must show up in the PDF."


def _admin_headers(seed_data, db_session):
    """Promote the seed admin to lab_admin too (the test endpoints require
    a lab_admin role) and return the auth header."""
    role = db_session.query(UserRole).filter(UserRole.name == "lab_admin").first()
    if not role:
        role = UserRole(name="lab_admin", is_system_role=True)
        db_session.add(role)
        db_session.flush()
    user = db_session.query(User).filter(User.id == seed_data["admin_user_id"]).first()
    if role not in user.roles:
        user.roles.append(role)
    db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(data={'sub': 'testadmin'})}"}


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Pull readable text out of a ReportLab PDF using PyPDF2."""
    from PyPDF2 import PdfReader
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def test_description_renders_in_report_pdf(client, db_session, seed_data):
    headers = _admin_headers(seed_data, db_session)
    hospital_id = seed_data["hospital_id"]

    # 1. Create a category + a test with a known description
    cat = LabTestCategory(
        name=f"Cat-{datetime.now().strftime('%H%M%S%f')}",
        hospital_id=hospital_id,
    )
    db_session.add(cat)
    db_session.flush()

    test = LabTest(
        test_code=f"T-{datetime.now().strftime('%H%M%S%f')}",
        name="Reference Section Test",
        description=DESCRIPTION_TEXT,
        category_id=cat.id,
        cost=100.0,
        hospital_id=hospital_id,
        is_active=True,
    )
    db_session.add(test)
    db_session.flush()

    param = LabTestParameter(
        test_id=test.id,
        parameter_name="ParamA",
        unit="mg/dL",
        field_type="numeric",
        reference_min_default=10,
        reference_max_default=20,
        display_order=0,
    )
    db_session.add(param)
    db_session.flush()

    # 2. Book an order for the seeded patient
    order = PatientLabOrder(
        order_number=f"LAB-{datetime.now().strftime('%H%M%S%f')}",
        patient_id=seed_data["patient_id"],
        test_id=test.id,
        status="processing",
        amount=100.0,
        payment_status="paid",
    )
    db_session.add(order)
    db_session.commit()

    # 3. Submit a result with an interpretation
    payload = {
        "results": [{"parameter_id": param.id, "value": "15", "remarks": "", "manual_abnormal": False}],
        "interpretation": "Within normal limits — interpretation body.",
    }
    res = client.post(f"/api/lab/orders/{order.id}/results", json=payload, headers=headers)
    assert res.status_code == 200, res.text
    report_id = res.json()["report_id"]

    # 4. Download the PDF
    res = client.get(f"/api/lab/reports/{report_id}/download", headers=headers)
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/pdf"
    pdf_bytes = res.content

    # 5. Assert: header AND body appear in the rendered text
    text = _extract_pdf_text(pdf_bytes)
    assert "Interpretation:" in text, f"Interpretation header missing. Sample: {text[:600]}"
    assert "Reference Information:" in text, (
        f"Reference Information header missing — the 'description below interpretation' "
        f"section did NOT render. Sample: {text[:1200]}"
    )
    # Spot-check that the actual description body made it through. We use a
    # distinctive marker so this can't false-positive on boilerplate.
    assert "RefSectTest123" in text, (
        f"Description body missing from PDF. Sample: {text[:1200]}"
    )


def test_description_omitted_when_blank(client, db_session, seed_data):
    """Sanity check: when LabTest.description is empty, the Reference
    Information section is correctly skipped — confirming the conditional
    in pdf_service.py works both ways.
    """
    headers = _admin_headers(seed_data, db_session)
    hospital_id = seed_data["hospital_id"]

    cat = LabTestCategory(
        name=f"CatBlank-{datetime.now().strftime('%H%M%S%f')}",
        hospital_id=hospital_id,
    )
    db_session.add(cat)
    db_session.flush()

    test = LabTest(
        test_code=f"TB-{datetime.now().strftime('%H%M%S%f')}",
        name="Blank-desc Test",
        description="",  # explicitly blank
        category_id=cat.id,
        cost=100.0,
        hospital_id=hospital_id,
        is_active=True,
    )
    db_session.add(test)
    db_session.flush()

    param = LabTestParameter(
        test_id=test.id, parameter_name="ParamB", field_type="numeric",
        reference_min_default=0, reference_max_default=10, display_order=0,
    )
    db_session.add(param)

    order = PatientLabOrder(
        order_number=f"LAB-{datetime.now().strftime('%H%M%S%f')}",
        patient_id=seed_data["patient_id"],
        test_id=test.id,
        status="processing",
        amount=100.0,
        payment_status="paid",
    )
    db_session.add(order)
    db_session.commit()

    payload = {
        "results": [{"parameter_id": param.id, "value": "5", "remarks": "", "manual_abnormal": False}],
        "interpretation": "Normal.",
    }
    res = client.post(f"/api/lab/orders/{order.id}/results", json=payload, headers=headers)
    assert res.status_code == 200, res.text
    report_id = res.json()["report_id"]

    res = client.get(f"/api/lab/reports/{report_id}/download", headers=headers)
    assert res.status_code == 200, res.text
    text = _extract_pdf_text(res.content)
    assert "Interpretation:" in text
    assert "Reference Information:" not in text, (
        "Reference Information section unexpectedly rendered for a test with blank description"
    )
