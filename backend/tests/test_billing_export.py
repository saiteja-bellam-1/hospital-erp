"""Tests for billing Excel export (filter-aware .xlsx)."""
from datetime import datetime, date, time
from io import BytesIO


def _paid_consultation(db_session, seed_data, fee=500.0):
    from app.models.outpatient import Appointment
    ts = datetime.now().timestamp()
    a = Appointment(
        appointment_number=f"XLS-{ts}",
        patient_id=seed_data["patient_id"],
        doctor_id=seed_data["doctor_user_id"],
        appointment_date=datetime.now(),
        appointment_time=time(10, 0),
        consultation_fee=fee,
        registration_fee=0,
        final_amount=fee,
        payment_status="paid",
        payment_method="cash",
    )
    db_session.add(a)
    db_session.commit()
    return a


class TestBillingExcelExport:

    def test_export_returns_xlsx(self, client, auth_headers, db_session, seed_data):
        _paid_consultation(db_session, seed_data)
        today = date.today().isoformat()
        r = client.get(
            f"/api/hospital/billing/export.xlsx?date_from={today}&date_to={today}",
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert "spreadsheetml" in r.headers.get("content-type", "")
        assert "billing_" in r.headers.get("content-disposition", "")
        assert r.content[:2] == b"PK"  # zip/xlsx magic

        from openpyxl import load_workbook
        wb = load_workbook(BytesIO(r.content))
        assert "Bills" in wb.sheetnames
        assert "Summary" in wb.sheetnames
        bills = wb["Bills"]
        # Header + at least one data row
        assert bills["A1"].value == "Date"
        assert bills.max_row >= 2

    def test_export_respects_bill_type_filter(self, client, auth_headers, db_session, seed_data):
        _paid_consultation(db_session, seed_data, fee=400)
        today = date.today().isoformat()
        # Lab-only filter should not include the consultation row
        r = client.get(
            f"/api/hospital/billing/export.xlsx?date_from={today}&date_to={today}&bill_type=lab",
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        from openpyxl import load_workbook
        wb = load_workbook(BytesIO(r.content))
        bills = wb["Bills"]
        types = [
            bills.cell(row=i, column=2).value
            for i in range(2, bills.max_row + 1)
            if bills.cell(row=i, column=2).value
        ]
        assert "consultation" not in types

    def test_export_empty_range_still_xlsx(self, client, auth_headers):
        r = client.get(
            "/api/hospital/billing/export.xlsx?date_from=2000-01-01&date_to=2000-01-02",
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        from openpyxl import load_workbook
        wb = load_workbook(BytesIO(r.content))
        assert wb["Bills"].max_row == 1  # header only
        assert wb["Summary"]["B3"].value == "2000-01-01"

    def test_export_allows_receptionist(self, client, db_session, seed_data):
        from app.utils.auth import create_access_token, get_password_hash
        from app.models.user import User, UserRole
        role = db_session.query(UserRole).filter_by(name="receptionist").first()
        if role is None:
            role = UserRole(name="receptionist", is_system_role=True)
            db_session.add(role)
            db_session.flush()
        user = db_session.query(User).filter_by(username="testreceptionist").first()
        if user is None:
            user = User(
                username="testreceptionist",
                password_hash=get_password_hash("recv123"),
                email="recv@test.com",
                first_name="Front",
                last_name="Desk",
                role_id=role.id,
                hospital_id=seed_data["hospital_id"],
                is_active=True,
            )
            db_session.add(user)
            db_session.commit()
        token = create_access_token(data={"sub": "testreceptionist"})
        hdr = {"Authorization": f"Bearer {token}"}
        r = client.get("/api/hospital/billing/export.xlsx", headers=hdr)
        assert r.status_code == 200

    def test_export_rejects_unprivileged(self, client, db_session, seed_data):
        from app.utils.auth import create_access_token
        token = create_access_token(data={"sub": "testdoctor"})
        hdr = {"Authorization": f"Bearer {token}"}
        r = client.get("/api/hospital/billing/export.xlsx", headers=hdr)
        assert r.status_code == 403
