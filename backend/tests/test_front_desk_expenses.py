"""Front-desk expenses are recorded by reception and deducted on the daily breakdown."""
from datetime import date, datetime, timedelta

import pytest

from app.utils.auth import create_access_token, get_password_hash


@pytest.fixture
def clear_expenses(db_session):
    yield
    from app.models.expense import FrontDeskExpense, FrontDeskExpenseCategory
    db_session.query(FrontDeskExpense).delete()
    db_session.query(FrontDeskExpenseCategory).delete()
    db_session.commit()


def _headers(username):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': username})}"}


def _frontdesk_headers(db_session, seed_data):
    from app.models.user import User, UserRole
    role = db_session.query(UserRole).filter_by(name="frontdesk").first()
    if role is None:
        role = UserRole(name="frontdesk", is_system_role=True)
        db_session.add(role)
        db_session.flush()
    user = db_session.query(User).filter_by(username="testfrontdesk").first()
    if user is None:
        user = User(
            username="testfrontdesk",
            password_hash=get_password_hash("desk123"),
            email="frontdesk@test.com",
            first_name="Front",
            last_name="Desk",
            role_id=role.id,
            hospital_id=seed_data["hospital_id"],
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
    return _headers("testfrontdesk")


def _expense(client, headers, amount=80, description="Tea for visitors", on=None, category="refreshments"):
    payload = {
        "expense_date": (on or date.today()).isoformat(),
        "amount": amount,
        "category": category,
        "description": description,
        "payment_method": "cash",
    }
    response = client.post("/api/hospital/front-desk-expenses", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


class TestFrontDeskExpenses:

    def test_frontdesk_expense_is_deducted_on_daily_breakdown(self, client, auth_headers, db_session, seed_data, clear_expenses):
        from app.models.billing import Bill, Payment
        ts = datetime.now().timestamp()
        bill = Bill(
            bill_number=f"EXP-{ts}",
            patient_id=seed_data["patient_id"],
            bill_type="consultation",
            reference_id=0,
            subtotal=500,
            tax_amount=0,
            discount_amount=0,
            total_amount=500,
            status="paid",
            bill_date=datetime.now(),
            created_by_id=seed_data["admin_user_id"],
            hospital_id=seed_data["hospital_id"],
        )
        db_session.add(bill)
        db_session.flush()
        db_session.add(Payment(
            payment_number=f"EXP-P-{ts}",
            bill_id=bill.id,
            amount_paid=500,
            payment_method_name="cash",
            payment_date=datetime.now(),
            received_by_id=seed_data["admin_user_id"],
        ))
        db_session.commit()

        desk = _frontdesk_headers(db_session, seed_data)
        created = _expense(client, desk, amount=125, description="Courier to the lab")
        assert created["amount"] == 125
        assert created["category"] == "refreshments"
        assert created["category_label"] == "Refreshments"

        today = date.today().isoformat()
        report = client.get(
            f"/api/hospital/billing/reports/daily-collection?date_from={today}&date_to={today}",
            headers=auth_headers,
        )
        assert report.status_code == 200, report.text
        body = report.json()
        assert body["expenses_applied"] is True
        row = next(item for item in body["rows"] if item["date"] == today)
        assert row["expenses"] == 125
        assert row["net"] == round(row["total"] - 125, 2)
        assert body["totals"]["expenses"] == 125
        assert body["totals"]["net_after_expenses"] == round(body["totals"]["net_collected"] - 125, 2)
        assert row["by_method"].get("cash", 0) >= 500

        listed = client.get(
            f"/api/hospital/front-desk-expenses?date_from={today}&date_to={today}",
            headers=desk,
        )
        assert listed.status_code == 200, listed.text
        assert listed.json()["total"] == 125
        assert listed.json()["expenses"][0]["description"] == "Courier to the lab"

        bills = client.get(f"/api/hospital/billing?date_from={today}&date_to={today}", headers=auth_headers)
        assert bills.status_code == 200, bills.text
        summary = bills.json()["summary"]
        assert summary["expenses_applied"] is True
        assert summary["expenses_total"] == 125
        assert summary["net_after_expenses"] == round(summary["received_total"] - 125, 2)

        scoped = client.get(
            f"/api/hospital/billing/reports/daily-collection?date_from={today}&date_to={today}&module=opd",
            headers=auth_headers,
        )
        assert scoped.json()["expenses_applied"] is False
        assert scoped.json()["totals"]["expenses"] == 0
        scoped_row = next(item for item in scoped.json()["rows"] if item["date"] == today)
        assert scoped_row["net"] == scoped_row["total"]

    def test_void_removes_the_deduction(self, client, auth_headers, clear_expenses):
        created = _expense(client, auth_headers, amount=40, description="Stationery")
        voided = client.post(
            f"/api/hospital/front-desk-expenses/{created['id']}/void",
            json={"reason": "Entered on the wrong day"},
            headers=auth_headers,
        )
        assert voided.status_code == 200, voided.text
        today = date.today().isoformat()
        report = client.get(
            f"/api/hospital/billing/reports/daily-collection?date_from={today}&date_to={today}",
            headers=auth_headers,
        )
        assert report.json()["totals"]["expenses"] == 0

    def test_expense_only_day_still_appears(self, client, auth_headers, clear_expenses):
        yesterday = date.today() - timedelta(days=1)
        _expense(client, auth_headers, amount=60, description="Night taxi", on=yesterday, category="conveyance")
        report = client.get(
            "/api/hospital/billing/reports/daily-collection",
            params={"date_from": yesterday.isoformat(), "date_to": yesterday.isoformat()},
            headers=auth_headers,
        )
        body = report.json()
        row = next(item for item in body["rows"] if item["date"] == yesterday.isoformat())
        assert row["expenses"] == 60
        assert row["net"] == round(row["total"] - 60, 2)
        assert body["totals"]["net_after_expenses"] == round(body["totals"]["net_collected"] - 60, 2)

    def test_receptionist_can_add_and_doctor_cannot(self, client, clear_expenses):
        reception = _headers("testreceptionist")
        created = _expense(client, reception, amount=15, description="Drinking water")
        assert created["created_by_name"]
        denied = client.post(
            "/api/hospital/front-desk-expenses",
            json={
                "expense_date": date.today().isoformat(),
                "amount": 10,
                "category": "other",
                "description": "Should fail",
                "payment_method": "cash",
            },
            headers=_headers("testdoctor"),
        )
        assert denied.status_code == 403

    def test_category_can_be_created_and_selected_again(self, client, auth_headers, clear_expenses):
        first = client.post(
            "/api/hospital/front-desk-expense-categories",
            json={"name": "  Laundry  "},
            headers=auth_headers,
        )
        assert first.status_code == 200, first.text
        assert first.json()["created"] is True
        assert first.json()["name"] == "Laundry"

        again = client.post(
            "/api/hospital/front-desk-expense-categories",
            json={"name": "laundry"},
            headers=auth_headers,
        )
        assert again.status_code == 200, again.text
        assert again.json()["created"] is False
        assert again.json()["id"] == first.json()["id"]

        selected = client.post(
            "/api/hospital/front-desk-expenses",
            json={
                "expense_date": date.today().isoformat(),
                "amount": 20,
                "category_id": first.json()["id"],
                "description": "Washing linen",
                "payment_method": "cash",
            },
            headers=auth_headers,
        )
        assert selected.status_code == 200, selected.text
        assert selected.json()["category_id"] == first.json()["id"]
        assert selected.json()["category_label"] == "Laundry"

        missing = client.post(
            "/api/hospital/front-desk-expense-categories",
            json={"name": " "},
            headers=auth_headers,
        )
        assert missing.status_code == 400

        denied = client.post(
            "/api/hospital/front-desk-expense-categories",
            json={"name": "Fuel"},
            headers=_headers("testdoctor"),
        )
        assert denied.status_code == 403

    def test_rejects_future_date_and_blank_description(self, client, auth_headers, clear_expenses):
        future = client.post(
            "/api/hospital/front-desk-expenses",
            json={
                "expense_date": (date.today() + timedelta(days=1)).isoformat(),
                "amount": 10,
                "category": "other",
                "description": "Tomorrow",
                "payment_method": "cash",
            },
            headers=auth_headers,
        )
        assert future.status_code == 400
        assert future.json()["detail"] == "Expense date cannot be in the future"
        blank = client.post(
            "/api/hospital/front-desk-expenses",
            json={
                "expense_date": date.today().isoformat(),
                "amount": 10,
                "category": "other",
                "description": "   ",
                "payment_method": "cash",
            },
            headers=auth_headers,
        )
        assert blank.status_code == 400

    def test_dashboard_net_is_after_expenses(self, client, auth_headers, clear_expenses):
        _expense(client, auth_headers, amount=30, description="Bulb")
        today = date.today().isoformat()
        dashboard = client.get(
            f"/api/hospital/billing/dashboard?date_from={today}&date_to={today}",
            headers=auth_headers,
        )
        assert dashboard.status_code == 200, dashboard.text
        totals = dashboard.json()["totals"]
        assert totals["expenses"] == 30
        assert totals["net_after_expenses"] == round(totals["net_receipts"] - 30, 2)
