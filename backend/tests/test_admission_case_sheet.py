"""Admission case-sheet API: save at draft admit time, visible on discharge summary."""


class TestAdmissionCaseSheet:
    def test_case_sheet_on_draft_and_prefill_summary(
        self, client, auth_headers, seed_data, TestSessionLocal,
    ):
        # Dedicated room so we don't collide with other smoke tests sharing the session DB
        room = client.post(
            "/api/inpatient/rooms",
            json={
                "room_number": "CS-201",
                "room_type": "general",
                "floor": "2",
                "department": "Case Sheet Ward",
                "bed_count": 2,
                "room_charge_per_day": 400.0,
            },
            headers=auth_headers,
        )
        assert room.status_code == 201, room.text
        room_id = room.json()["id"]

        # Create draft admission (wizard step 3 path)
        adm = client.post(
            "/api/inpatient/admissions",
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": room_id,
                "admission_type": "elective",
                "admission_reason": "Fever for 3 days",
                "save_as_draft": True,
            },
            headers=auth_headers,
        )
        assert adm.status_code == 201, adm.text
        admission_id = adm.json()["id"]
        assert adm.json()["status"] == "draft"

        # Activate (claim bed) — still draft until complete-admission
        act = client.post(
            f"/api/inpatient/admissions/{admission_id}/activate",
            json={"deposit_amount": 0, "deposit_waived": True, "deposit_waiver_reason": "test"},
            headers=auth_headers,
        )
        assert act.status_code == 200, act.text
        assert act.json()["status"] == "draft"

        # GET prefills chief complaint from admission_reason
        get_cs = client.get(
            f"/api/inpatient/admissions/{admission_id}/admission-case-sheet",
            headers=auth_headers,
        )
        assert get_cs.status_code == 200, get_cs.text
        assert get_cs.json()["chief_complaint"] == "Fever for 3 days"
        assert get_cs.json()["summary_id"] is None

        # PUT clinical case sheet while still draft
        put_cs = client.put(
            f"/api/inpatient/admissions/{admission_id}/admission-case-sheet",
            json={
                "chief_complaint": "High fever with chills",
                "present_medical_history": "Onset 3 days ago",
                "past_history": "Diabetes mellitus",
                "family_history": "Father — HTN",
                "provisional_diagnosis": "Viral fever",
                "physical_examination_notes": "Febrile, tachycardic",
                "findings_at_admission": "Temp 102F",
            },
            headers=auth_headers,
        )
        assert put_cs.status_code == 200, put_cs.text
        body = put_cs.json()
        assert body["summary_id"] is not None
        assert body["chief_complaint"] == "High fever with chills"
        assert body["past_history"] == "Diabetes mellitus"
        assert body["provisional_diagnosis"] == "Viral fever"

        # Complete admission
        done = client.post(
            f"/api/inpatient/admissions/{admission_id}/complete-admission",
            headers=auth_headers,
        )
        assert done.status_code == 200, done.text
        assert done.json()["status"] == "admitted"

        # Discharge summary GET should show the same Complaints & History fields
        summary = client.get(
            f"/api/inpatient/admissions/{admission_id}/discharge-summary",
            headers=auth_headers,
        )
        assert summary.status_code == 200, summary.text
        s = summary.json()
        assert s["chief_complaint"] == "High fever with chills"
        assert s["present_medical_history"] == "Onset 3 days ago"
        assert s["past_history"] == "Diabetes mellitus"
        assert s["family_history"] == "Father — HTN"
        assert s["provisional_diagnosis"] == "Viral fever"
        assert s["physical_examination_notes"] == "Febrile, tachycardic"
        assert s["findings_at_admission"] == "Temp 102F"
        assert s["status"] == "draft"

        # Case sheet PDF is a valid PDF response
        pdf = client.get(
            f"/api/inpatient/admissions/{admission_id}/admission-case-sheet/pdf",
            headers=auth_headers,
        )
        assert pdf.status_code == 200, pdf.text
        assert pdf.headers.get("content-type", "").startswith("application/pdf")
        assert pdf.content[:4] == b"%PDF"
        assert len(pdf.content) > 500

        # Skip path: second patient / room — complete without case sheet PUT
        room2 = client.post(
            "/api/inpatient/rooms",
            json={
                "room_number": "CS-202",
                "room_type": "general",
                "floor": "2",
                "department": "Case Sheet Ward",
                "bed_count": 1,
                "room_charge_per_day": 400.0,
            },
            headers=auth_headers,
        )
        assert room2.status_code == 201, room2.text

        # Need another patient — create via seed helper pattern
        from app.models.patient import Patient
        from datetime import date
        import uuid
        session = TestSessionLocal()
        try:
            p = Patient(
                patient_id=str(uuid.uuid4()),
                first_name="Skip",
                last_name="Case",
                gender="female",
                date_of_birth=date(1990, 1, 1),
                primary_phone="9999999999",
                hospital_id=seed_data["hospital_id"],
            )
            session.add(p)
            session.commit()
            session.refresh(p)
            patient2_id = p.id
        finally:
            session.close()

        adm2 = client.post(
            "/api/inpatient/admissions",
            json={
                "patient_id": patient2_id,
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": room2.json()["id"],
                "admission_type": "elective",
                "admission_reason": "Checkup",
                "save_as_draft": True,
            },
            headers=auth_headers,
        )
        assert adm2.status_code == 201, adm2.text
        aid2 = adm2.json()["id"]
        act2 = client.post(
            f"/api/inpatient/admissions/{aid2}/activate",
            json={"deposit_amount": 0, "deposit_waived": True, "deposit_waiver_reason": "test"},
            headers=auth_headers,
        )
        assert act2.status_code == 200, act2.text
        done2 = client.post(
            f"/api/inpatient/admissions/{aid2}/complete-admission",
            headers=auth_headers,
        )
        assert done2.status_code == 200, done2.text

        # No summary until first edit — 404 is expected
        missing = client.get(
            f"/api/inpatient/admissions/{aid2}/discharge-summary",
            headers=auth_headers,
        )
        assert missing.status_code == 404
