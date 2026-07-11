"""Daily auto-post job for inpatient charges.

Posts one doctor visit per admitted patient per day at the admitting doctor's
configured fee. Idempotent — if any doctor_visit already exists for an
admission on the target date (auto-posted or not), the job leaves it alone so
manually recorded visits always win.

Room rent is NOT auto-posted as a row: the bill calculation already accrues
`stay_days * room_charge_per_day` at finalize time. Auto-posting separate
room-rent rows would double-bill unless we change the bill calc, which is a
larger refactor (covered separately as the room-rate-snapshot follow-up).

The thread runs every hour and only fires once per calendar date (system local
time via date.today()). It does not depend on a wall-clock cron; if the server
is down at midnight, the next hourly tick after wake-up posts the missed day.
"""
import datetime
import threading
import time
import traceback

_thread = None
_running = False
_last_run_date = None  # date object — guards "ran today already"
_last_run_summary = None
_last_run_error = None


def _today_date():
    return datetime.date.today()


def auto_post_daily_visits_for_admission(db, admission, target_date=None, actor_user_id=None):
    """Post one doctor visit for `admission` on `target_date` if none exists.

    Returns the created PatientVisit id, or None if skipped.
    Skips when:
      - admission is not currently admitted
      - any visit (any type, any source) already exists for this admission on target_date
      - admitting doctor has no inpatient_fee_inr configured (defaults to 0 — still post but $0)
    """
    from app.models.inpatient import PatientVisit, Admission
    from app.models.user import User

    if admission.status != "admitted":
        return None
    if getattr(admission, "is_catch_up", False):
        return None
    if not admission.admitting_doctor_id:
        return None

    target = target_date or _today_date()

    # Idempotency: any doctor_visit on this admission with visit_datetime on `target` blocks us.
    existing = db.query(PatientVisit).filter(
        PatientVisit.admission_id == admission.id,
        PatientVisit.visit_type == "doctor_visit",
    ).all()
    for v in existing:
        vd = v.visit_datetime
        if vd is None:
            continue
        vd_date = vd.date() if hasattr(vd, "date") else None
        if vd_date == target:
            return None  # already covered for the day

    doctor = db.query(User).filter(User.id == admission.admitting_doctor_id).first()
    if not doctor:
        return None
    fee = float(getattr(doctor, "inpatient_fee_inr", 0) or 0)

    # Build a visit datetime anchored to noon of target_date so the row sorts
    # naturally between any morning manual entries and any evening ones.
    visit_dt = datetime.datetime.combine(target, datetime.time(12, 0))

    visit = PatientVisit(
        admission_id=admission.id,
        patient_id=admission.patient_id,
        visitor_id=doctor.id,
        visit_type="doctor_visit",
        visit_datetime=visit_dt,
        notes="Auto-posted daily doctor visit",
        charge_amount=fee,
        billed=False,
        auto_posted=True,
        created_by_id=actor_user_id or doctor.id,
        hospital_id=doctor.hospital_id,
    )
    db.add(visit)
    db.flush()
    return visit.id


def auto_post_daily_visits_all(db, target_date=None):
    """Post daily doctor visits for every currently-admitted patient.
    Returns a summary dict {posted, skipped, errors}."""
    from app.models.inpatient import Admission

    target = target_date or _today_date()
    posted = 0
    skipped = 0
    errors = 0
    admissions = db.query(Admission).filter(Admission.status == "admitted").all()
    for adm in admissions:
        try:
            r = auto_post_daily_visits_for_admission(db, adm, target_date=target)
            if r is None:
                skipped += 1
            else:
                posted += 1
        except Exception:
            errors += 1
            traceback.print_exc()
    db.commit()
    return {"target_date": target.isoformat(), "posted": posted, "skipped": skipped, "errors": errors}


def _loop(check_interval_seconds: int):
    """Hourly loop that runs the daily post once per calendar date."""
    global _last_run_date, _last_run_summary, _last_run_error
    from config.database import get_db as _get_db

    while _running:
        try:
            today = _today_date()
            if _last_run_date != today:
                _db = next(_get_db())
                try:
                    summary = auto_post_daily_visits_all(_db, target_date=today)
                    _last_run_summary = summary
                    _last_run_error = None
                    _last_run_date = today
                    print(f"[daily-charges] {summary}")
                finally:
                    _db.close()
        except Exception as e:
            _last_run_error = str(e)
            traceback.print_exc()
        time.sleep(check_interval_seconds)


def start_daily_charges_thread(check_interval_seconds: int = 3600):
    """Start the hourly daemon. No-op if already running."""
    global _thread, _running
    if _running:
        return
    _running = True
    _thread = threading.Thread(
        target=_loop,
        args=(check_interval_seconds,),
        daemon=True,
        name="daily-charges",
    )
    _thread.start()


def stop_daily_charges_thread():
    global _running
    _running = False


def get_status():
    return {
        "running": _running,
        "last_run_date": _last_run_date.isoformat() if _last_run_date else None,
        "last_run_summary": _last_run_summary,
        "last_run_error": _last_run_error,
    }
