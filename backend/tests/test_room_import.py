"""Tests for inpatient room import/export.

Covers template download, dry-run, create/update/skip, CSV, round-trip,
occupancy safety, reactivation, partial-row errors, and permissions.

Uses unique room numbers so it can share the session-scoped test DB.
"""
from __future__ import annotations

import io
import json
import uuid

import openpyxl

from app.models.inpatient import Bed, RoomManagement
from app.services.room_import import BED_HEADERS, ROOM_HEADERS
from app.utils.auth import create_access_token


def _room_no(prefix: str = "IM") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _xlsx_bytes(room_rows, bed_rows=None, rooms_header=None, beds_header=None):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Rooms"
    ws.append(rooms_header or list(ROOM_HEADERS))
    for row in room_rows:
        ws.append(row)
    if bed_rows is not None:
        beds = wb.create_sheet("Beds")
        beds.append(beds_header or list(BED_HEADERS))
        for row in bed_rows:
            beds.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def _upload(client, auth_headers, content, filename, *, dry_run=False, on_duplicate="skip"):
    media = (
        "text/csv" if filename.endswith(".csv")
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return client.post(
        "/api/inpatient/rooms/import",
        headers=auth_headers,
        files={"file": (filename, io.BytesIO(content), media)},
        data={"dry_run": str(dry_run).lower(), "on_duplicate": on_duplicate},
    )


def _room(db_session, hospital_id, number):
    return (
        db_session.query(RoomManagement)
        .filter(
            RoomManagement.hospital_id == hospital_id,
            RoomManagement.room_number == number,
        )
        .first()
    )


def _beds(db_session, room_id):
    return db_session.query(Bed).filter(Bed.room_id == room_id).order_by(Bed.bed_label).all()


def test_import_template_downloads_xlsx(client, auth_headers):
    resp = client.get("/api/inpatient/rooms/import/template", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert "spreadsheet" in resp.headers.get("content-type", "")
    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    assert "Rooms" in wb.sheetnames
    assert "Beds" in wb.sheetnames
    assert "Instructions" in wb.sheetnames
    headers = [c.value for c in next(wb["Rooms"].iter_rows(min_row=1, max_row=1))]
    assert headers == list(ROOM_HEADERS)


def test_dry_run_previews_without_writing(client, auth_headers, db_session, seed_data):
    number = _room_no()
    content = _xlsx_bytes([[
        number, "general", "1", "Medicine", "Ward A", 2, 1500, 100,
        "ac;tv", "false", "mixed",
    ]])
    resp = _upload(client, auth_headers, content, "rooms.xlsx", dry_run=True)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dry_run"] is True
    assert body["created"] == 1
    assert _room(db_session, seed_data["hospital_id"], number) is None


def test_import_creates_rooms_and_auto_beds(client, auth_headers, db_session, seed_data):
    number = _room_no()
    content = _xlsx_bytes([[
        number, "icu", "2", "Critical Care", "ICU", 3, 8000, 350,
        "ac;oxygen_point", "true", "mixed",
    ]])
    resp = _upload(client, auth_headers, content, "rooms.xlsx", dry_run=False)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created"] == 1
    assert body["created_beds"] == 3
    db_session.expire_all()
    room = _room(db_session, seed_data["hospital_id"], number)
    assert room is not None
    assert room.room_type == "icu"
    assert room.bed_count == 3
    assert room.available_beds == 3
    assert room.is_isolation is True
    amenities = json.loads(room.amenities)
    assert "oxygen_point" in amenities
    labels = {b.bed_label for b in _beds(db_session, room.id)}
    assert labels == {"Bed-1", "Bed-2", "Bed-3"}


def test_import_explicit_bed_labels(client, auth_headers, db_session, seed_data):
    number = _room_no()
    content = _xlsx_bytes(
        [[number, "general", "1", "Medicine", "Male Ward", 4, 1500, 100, "call_bell", "false", "male"]],
        [[number, "A"], [number, "B"], [number, "C"], [number, "D"]],
    )
    resp = _upload(client, auth_headers, content, "rooms.xlsx")
    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    room = _room(db_session, seed_data["hospital_id"], number)
    assert room.bed_count == 4
    assert room.gender_policy == "male"
    assert {b.bed_label for b in _beds(db_session, room.id)} == {"A", "B", "C", "D"}


def test_import_csv_rooms_only(client, auth_headers, db_session, seed_data):
    number = _room_no()
    csv = (
        "room_number,room_type,floor,department,ward,bed_count,"
        "room_charge_per_day,nursing_charge_per_visit,amenities,is_isolation,gender_policy\n"
        f"{number},private,3,Surgery,Private,2,4000,200,ac;tv,false,mixed\n"
    )
    resp = _upload(client, auth_headers, csv.encode("utf-8"), "rooms.csv")
    assert resp.status_code == 200, resp.text
    assert resp.json()["created"] == 1
    db_session.expire_all()
    room = _room(db_session, seed_data["hospital_id"], number)
    assert room.room_type == "private"
    assert room.bed_count == 2
    assert len(_beds(db_session, room.id)) == 2


def test_duplicate_skip_vs_update(client, auth_headers, db_session, seed_data):
    number = _room_no()
    original = _xlsx_bytes([[
        number, "general", "1", "Medicine", "Ward A", 2, 1500, 50, "", "false", "mixed",
    ]])
    assert _upload(client, auth_headers, original, "rooms.xlsx").status_code == 200

    changed = _xlsx_bytes([[
        number, "semi_private", "2", "Medicine", "Ward B", 2, 2500, 80, "wifi", "false", "female",
    ]])
    skipped = _upload(client, auth_headers, changed, "rooms.xlsx", on_duplicate="skip")
    assert skipped.status_code == 200, skipped.text
    assert skipped.json()["skipped"] >= 1
    assert skipped.json()["updated"] == 0
    db_session.expire_all()
    room = _room(db_session, seed_data["hospital_id"], number)
    assert room.room_charge_per_day == 1500
    assert room.room_type == "general"

    updated = _upload(client, auth_headers, changed, "rooms.xlsx", on_duplicate="update")
    assert updated.status_code == 200, updated.text
    assert updated.json()["updated"] == 1
    db_session.expire_all()
    room = _room(db_session, seed_data["hospital_id"], number)
    assert room.room_charge_per_day == 2500
    assert room.room_type == "semi_private"
    assert room.ward == "Ward B"
    assert room.gender_policy == "female"


def test_export_round_trip(client, auth_headers, db_session, seed_data):
    number = _room_no()
    content = _xlsx_bytes(
        [[number, "hdu", "2", "Critical Care", "HDU", 2, 5000, 200, "ac;cardiac_monitor", "false", "mixed"]],
        [[number, "H1"], [number, "H2"]],
    )
    created = _upload(client, auth_headers, content, "rooms.xlsx")
    assert created.status_code == 200, created.text

    exported = client.get("/api/inpatient/rooms/export/xlsx", headers=auth_headers)
    assert exported.status_code == 200, exported.text
    assert "spreadsheet" in exported.headers.get("content-type", "")
    wb = openpyxl.load_workbook(io.BytesIO(exported.content))
    assert "Rooms" in wb.sheetnames
    assert "Beds" in wb.sheetnames
    room_headers = [c.value for c in next(wb["Rooms"].iter_rows(min_row=1, max_row=1))]
    assert room_headers == list(ROOM_HEADERS)

    numbers = [
        row[0].value for row in wb["Rooms"].iter_rows(min_row=2)
        if row[0].value
    ]
    assert number in numbers

    reimport = _upload(
        client, auth_headers, exported.content, "round-trip.xlsx", on_duplicate="update",
    )
    assert reimport.status_code == 200, reimport.text
    db_session.expire_all()
    room = _room(db_session, seed_data["hospital_id"], number)
    assert room.room_type == "hdu"
    assert {b.bed_label for b in _beds(db_session, room.id)} == {"H1", "H2"}
    occupied = [b for b in _beds(db_session, room.id) if b.status == "occupied"]
    assert occupied == []


def test_occupied_room_keeps_beds_on_shrink(client, auth_headers, db_session, seed_data):
    number = _room_no()
    content = _xlsx_bytes([[
        number, "general", "1", "Medicine", "Ward A", 4, 1500, 0, "", "false", "mixed",
    ]])
    assert _upload(client, auth_headers, content, "rooms.xlsx").status_code == 200
    db_session.expire_all()
    room = _room(db_session, seed_data["hospital_id"], number)
    beds = _beds(db_session, room.id)
    beds[0].status = "occupied"
    beds[1].status = "occupied"
    room.available_beds = 2
    db_session.commit()

    shrink = _xlsx_bytes([[
        number, "general", "1", "Medicine", "Ward A", 1, 1800, 0, "", "false", "mixed",
    ]])
    resp = _upload(client, auth_headers, shrink, "rooms.xlsx", on_duplicate="update")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["error_count"] >= 1
    assert any("occupied" in (e["message"] or "").lower() for e in body["errors"])
    db_session.expire_all()
    room = _room(db_session, seed_data["hospital_id"], number)
    assert room.room_charge_per_day == 1800
    assert room.bed_count == 4
    statuses = {b.bed_label: b.status for b in _beds(db_session, room.id)}
    assert list(statuses.values()).count("occupied") == 2


def test_reactivate_inactive_room(client, auth_headers, db_session, seed_data):
    number = _room_no()
    content = _xlsx_bytes([[
        number, "general", "1", "Medicine", "Ward A", 1, 1200, 0, "", "false", "mixed",
    ]])
    created = _upload(client, auth_headers, content, "rooms.xlsx")
    assert created.status_code == 200, created.text
    db_session.expire_all()
    room = _room(db_session, seed_data["hospital_id"], number)
    deactivate = client.delete(f"/api/inpatient/rooms/{room.id}", headers=auth_headers)
    assert deactivate.status_code == 200, deactivate.text

    revived = _xlsx_bytes([[
        number, "private", "1", "Medicine", "Ward A", 1, 3000, 0, "ac", "false", "mixed",
    ]])
    resp = _upload(client, auth_headers, revived, "rooms.xlsx", on_duplicate="skip")
    assert resp.status_code == 200, resp.text
    assert resp.json()["updated"] == 1
    db_session.expire_all()
    room = _room(db_session, seed_data["hospital_id"], number)
    assert room.is_active is True
    assert room.room_type == "private"
    assert room.room_charge_per_day == 3000


def test_invalid_rows_reported_valid_rows_import(client, auth_headers, db_session, seed_data):
    good = _room_no("OK")
    bad = _room_no("BAD")
    content = _xlsx_bytes([
        [good, "general", "1", "Medicine", "Ward A", 1, 1500, 0, "", "false", "mixed"],
        [bad, "spaceship", "1", "Medicine", "Ward A", 1, 1500, 0, "", "false", "mixed"],
    ])
    resp = _upload(client, auth_headers, content, "rooms.xlsx")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created"] == 1
    assert body["error_count"] >= 1
    db_session.expire_all()
    assert _room(db_session, seed_data["hospital_id"], good) is not None
    assert _room(db_session, seed_data["hospital_id"], bad) is None


def test_unsupported_file_type(client, auth_headers):
    resp = _upload(client, auth_headers, b"whatever", "rooms.txt", dry_run=True)
    assert resp.status_code == 400


def test_import_requires_auth(client):
    content = _xlsx_bytes([[_room_no(), "general", "1", "", "", 1, 100, 0, "", "false", "mixed"]])
    resp = _upload(client, {}, content, "rooms.xlsx")
    assert resp.status_code in (401, 403)


def test_import_rejects_doctor_without_manage_beds(client):
    token = create_access_token(data={"sub": "testdoctor"})
    headers = {"Authorization": f"Bearer {token}"}
    content = _xlsx_bytes([[_room_no(), "general", "1", "", "", 1, 100, 0, "", "false", "mixed"]])
    resp = _upload(client, headers, content, "rooms.xlsx")
    assert resp.status_code == 403
    tmpl = client.get("/api/inpatient/rooms/import/template", headers=headers)
    assert tmpl.status_code == 403


def test_export_requires_auth(client):
    resp = client.get("/api/inpatient/rooms/export/xlsx")
    assert resp.status_code in (401, 403)
