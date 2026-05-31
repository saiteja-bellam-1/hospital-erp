"""CSV user import — parser, validator, applier.

Used in two places:

  1. Installer wizard pre-install validation (via ``installer/dbcheck/dbcheck.py``
     ``validate-users-csv`` command). dbcheck is built with ``sqlalchemy``
     excluded, so the **parse_and_validate** half of this module MUST stay
     importable without any sqlalchemy dependency. Keep all ORM work behind
     ``apply_users`` (which imports sqlalchemy lazily inside the function).

  2. First-launch bootstrap (``app.services.bootstrap_from_seed._apply_fresh``)
     which calls parse_and_validate again as defence-in-depth, then apply_users.

Policy:

  * "Normal" users only — ``doctor``, ``nurse``, ``super_admin`` are rejected.
    Doctors and nurses get dedicated in-app importers (extra profile fields).
  * Plaintext passwords in the CSV; we hash on apply and set
    ``must_change_password=True`` so the operator-supplied password is a
    one-time credential.
  * Any duplicate (within-file or against an existing DB user) BLOCKS the
    whole import — no partial application.

CSV columns (header row required, case-insensitive, whitespace stripped):

    username, email, first_name, last_name, role, password,
    phone (optional), additional_roles (optional; ``;``-separated)
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Iterable, Optional


REQUIRED_COLUMNS = ("username", "email", "first_name", "last_name", "role", "password")
OPTIONAL_COLUMNS = ("phone", "additional_roles")
ALL_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

MIN_PASSWORD_LEN = 8
MAX_USERNAME_LEN = 50
MAX_EMAIL_LEN = 100
MAX_NAME_LEN = 50
MAX_PHONE_LEN = 15

# Roles permitted in the *installer* CSV. doctor/nurse are excluded — they have
# their own in-app importers that collect extra profile columns. super_admin is
# created from the wizard's AdminPage and must not be duplicated here.
INSTALLER_ALLOWED_ROLES = frozenset({
    "hospital_admin",
    "lab_admin",
    "lab_technician",
    "pharmacy_admin",
    "pharmacist",
    "billing_admin",
    "inpatient_admin",
    "frontdesk",
    "receptionist",
})

# Doctor in-app importer — primary role is fixed to "doctor", these are the
# *additional* columns expected beyond the base set. license_number and
# specialization are required because both surface in the consultation/EHR
# screens; everything else is optional.
DOCTOR_EXTRA_REQUIRED = ("specialization", "license_number")
DOCTOR_EXTRA_OPTIONAL = (
    "qualification",
    "consultation_fee_inr",
    "inpatient_fee_inr",
    "emergency_fee_inr",
    "experience_years",
    "default_consultation_duration",
)

# Nurse in-app importer — primary role fixed to "nurse", no extra columns
# beyond the base set.
NURSE_EXTRA_REQUIRED: tuple = ()
NURSE_EXTRA_OPTIONAL: tuple = ()


@dataclass
class ParsedRow:
    line_no: int                # 1-based, matches what the operator sees in a text editor (header is line 1)
    username: str
    email: str
    first_name: str
    last_name: str
    role: str
    password: str
    phone: str = ""
    additional_roles: list = field(default_factory=list)
    # Free-form extras (used by doctor/nurse importers). Always lower-cased keys.
    extras: dict = field(default_factory=dict)


@dataclass
class ImportError:
    line_no: Optional[int]      # None for file-level errors (missing header, etc.)
    field: Optional[str]
    message: str

    def as_dict(self) -> dict:
        return {"line": self.line_no, "field": self.field, "message": self.message}


def _norm_header(h: str) -> str:
    return (h or "").strip().lower().replace(" ", "_")


def _split_additional_roles(raw: str) -> list:
    if not raw:
        return []
    return [r.strip() for r in raw.split(";") if r.strip()]


def parse_and_validate(
    csv_text: str,
    *,
    allowed_roles: Iterable[str] = INSTALLER_ALLOWED_ROLES,
    existing_usernames: Optional[Iterable[str]] = None,
    existing_emails: Optional[Iterable[str]] = None,
    extra_required: tuple = (),
    extra_optional: tuple = (),
    fixed_role: Optional[str] = None,
    allow_additional_roles: bool = True,
) -> tuple[list, list]:
    """Parse CSV text and validate every row.

    Returns ``(rows, errors)``. ``rows`` is always returned (even on errors) so
    callers can show "5 of 7 parsed" UX; but the applier MUST refuse to run
    when ``errors`` is non-empty.

    ``existing_usernames``/``existing_emails`` come from the live DB. For the
    installer's pre-install validation pass they're not available (no DB yet),
    so they default to None and the DB-collision check is skipped — the
    runtime bootstrap re-validates with the real DB before applying.
    """
    errors: list = []
    rows: list = []

    existing_usernames_l = {u.lower() for u in (existing_usernames or [])}
    existing_emails_l = {e.lower() for e in (existing_emails or [])}
    allowed_roles_l = {r.lower() for r in allowed_roles}

    reader = csv.reader(io.StringIO(csv_text))
    try:
        header = next(reader)
    except StopIteration:
        errors.append(ImportError(None, None, "CSV is empty"))
        return rows, errors

    header_norm = [_norm_header(h) for h in header]

    # When the importer pins the role (doctor/nurse paths), `role` column is
    # NOT required from the operator — we inject it. Same for additional_roles.
    base_required = tuple(c for c in REQUIRED_COLUMNS if not (fixed_role and c == "role"))
    required_here = base_required + tuple(extra_required)
    optional_here = OPTIONAL_COLUMNS + tuple(extra_optional)
    if fixed_role:
        optional_here = tuple(c for c in optional_here if c != "additional_roles") if not allow_additional_roles else optional_here
    expected_columns = required_here + optional_here

    missing = [c for c in required_here if c not in header_norm]
    if missing:
        errors.append(ImportError(
            1, None,
            f"Missing required column(s): {', '.join(missing)}. "
            f"Expected header: {','.join(expected_columns)}"
        ))
        return rows, errors

    col_idx = {c: header_norm.index(c) for c in expected_columns if c in header_norm}

    # Within-file uniqueness tracking
    seen_usernames: dict = {}   # lowercased username -> first line_no
    seen_emails: dict = {}

    for raw in reader:
        line_no = reader.line_num   # 1-based, header counted
        # Skip fully-blank lines silently — operators commonly leave trailing newlines.
        if not raw or all((c or "").strip() == "" for c in raw):
            continue

        def get(col: str) -> str:
            idx = col_idx.get(col)
            if idx is None or idx >= len(raw):
                return ""
            return (raw[idx] or "").strip()

        row_role = (fixed_role or get("role")).lower()
        addl = _split_additional_roles(get("additional_roles")) if allow_additional_roles else []
        row = ParsedRow(
            line_no=line_no,
            username=get("username"),
            email=get("email"),
            first_name=get("first_name"),
            last_name=get("last_name"),
            role=row_role,
            password=get("password"),
            phone=get("phone"),
            additional_roles=addl,
            extras={col: get(col) for col in extra_required + extra_optional},
        )

        # Required-field presence
        for col in base_required:
            if not getattr(row, col):
                errors.append(ImportError(line_no, col, f"{col} is required"))
        # Even when role is fixed, password/etc still come from the row.
        if fixed_role and not row.password:
            # Already covered by the loop above (password is in base_required),
            # but be explicit.
            pass

        for col in extra_required:
            if not row.extras.get(col):
                errors.append(ImportError(line_no, col, f"{col} is required"))

        # Length caps
        if len(row.username) > MAX_USERNAME_LEN:
            errors.append(ImportError(line_no, "username", f"username exceeds {MAX_USERNAME_LEN} chars"))
        if len(row.email) > MAX_EMAIL_LEN:
            errors.append(ImportError(line_no, "email", f"email exceeds {MAX_EMAIL_LEN} chars"))
        if len(row.first_name) > MAX_NAME_LEN:
            errors.append(ImportError(line_no, "first_name", f"first_name exceeds {MAX_NAME_LEN} chars"))
        if len(row.last_name) > MAX_NAME_LEN:
            errors.append(ImportError(line_no, "last_name", f"last_name exceeds {MAX_NAME_LEN} chars"))
        if row.phone and len(row.phone) > MAX_PHONE_LEN:
            errors.append(ImportError(line_no, "phone", f"phone exceeds {MAX_PHONE_LEN} chars"))

        # Email shape — keep it simple, not RFC-perfect
        if row.email and ("@" not in row.email or "." not in row.email.split("@")[-1]):
            errors.append(ImportError(line_no, "email", f"{row.email!r} is not a valid email"))

        # Password length
        if row.password and len(row.password) < MIN_PASSWORD_LEN:
            errors.append(ImportError(
                line_no, "password",
                f"password must be at least {MIN_PASSWORD_LEN} characters"
            ))

        # Role allow-list (primary)
        if row.role and row.role not in allowed_roles_l:
            errors.append(ImportError(
                line_no, "role",
                f"role {row.role!r} is not allowed here. "
                f"Allowed: {', '.join(sorted(allowed_roles_l))}"
            ))

        # additional_roles allow-list + no duplicate with primary
        for extra in row.additional_roles:
            extra_l = extra.lower()
            if extra_l not in allowed_roles_l:
                errors.append(ImportError(
                    line_no, "additional_roles",
                    f"additional role {extra!r} is not allowed"
                ))
            if extra_l == row.role:
                errors.append(ImportError(
                    line_no, "additional_roles",
                    f"additional role {extra!r} duplicates the primary role"
                ))

        # Within-file dup checks
        if row.username:
            ul = row.username.lower()
            if ul in seen_usernames:
                errors.append(ImportError(
                    line_no, "username",
                    f"username {row.username!r} also appears on line {seen_usernames[ul]}"
                ))
            else:
                seen_usernames[ul] = line_no
        if row.email:
            el = row.email.lower()
            if el in seen_emails:
                errors.append(ImportError(
                    line_no, "email",
                    f"email {row.email!r} also appears on line {seen_emails[el]}"
                ))
            else:
                seen_emails[el] = line_no

        # DB collision (only when caller passed an existing-set)
        if existing_usernames is not None and row.username.lower() in existing_usernames_l:
            errors.append(ImportError(
                line_no, "username",
                f"username {row.username!r} already exists in the database"
            ))
        if existing_emails is not None and row.email.lower() in existing_emails_l:
            errors.append(ImportError(
                line_no, "email",
                f"email {row.email!r} already exists in the database"
            ))

        rows.append(row)

    if not rows and not errors:
        errors.append(ImportError(None, None, "CSV has a header but no user rows"))

    return rows, errors


def parse_and_validate_file(path: str, **kwargs) -> tuple[list, list]:
    """Convenience wrapper that reads ``path`` and forwards to parse_and_validate."""
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            text = f.read()
    except FileNotFoundError:
        return [], [ImportError(None, None, f"CSV file not found: {path}")]
    except OSError as e:
        return [], [ImportError(None, None, f"Could not read CSV: {e}")]
    return parse_and_validate(text, **kwargs)


def _validate_doctor_extras(rows, errors):
    """Type-check numeric doctor extras. Mutates ``errors`` in place."""
    for row in rows:
        dur = row.extras.get("default_consultation_duration", "")
        if dur:
            try:
                v = int(dur)
                if v < 2 or v > 240:
                    errors.append(ImportError(
                        row.line_no, "default_consultation_duration",
                        "must be between 2 and 240 minutes"
                    ))
            except ValueError:
                errors.append(ImportError(
                    row.line_no, "default_consultation_duration",
                    f"{dur!r} is not a whole number"
                ))
        exp = row.extras.get("experience_years", "")
        if exp:
            try:
                v = int(exp)
                if v < 0 or v > 80:
                    errors.append(ImportError(
                        row.line_no, "experience_years",
                        "must be between 0 and 80"
                    ))
            except ValueError:
                errors.append(ImportError(
                    row.line_no, "experience_years",
                    f"{exp!r} is not a whole number"
                ))
        for fee_col in ("consultation_fee_inr", "inpatient_fee_inr", "emergency_fee_inr"):
            fee = row.extras.get(fee_col, "")
            if fee:
                try:
                    if float(fee) < 0:
                        errors.append(ImportError(row.line_no, fee_col, "must be >= 0"))
                except ValueError:
                    errors.append(ImportError(row.line_no, fee_col, f"{fee!r} is not a number"))


def parse_and_validate_doctors(
    csv_text: str,
    *,
    existing_usernames: Optional[Iterable[str]] = None,
    existing_emails: Optional[Iterable[str]] = None,
) -> tuple[list, list]:
    rows, errors = parse_and_validate(
        csv_text,
        allowed_roles=("doctor",),
        existing_usernames=existing_usernames,
        existing_emails=existing_emails,
        extra_required=DOCTOR_EXTRA_REQUIRED,
        extra_optional=DOCTOR_EXTRA_OPTIONAL,
        fixed_role="doctor",
        allow_additional_roles=False,
    )
    _validate_doctor_extras(rows, errors)
    return rows, errors


def parse_and_validate_nurses(
    csv_text: str,
    *,
    existing_usernames: Optional[Iterable[str]] = None,
    existing_emails: Optional[Iterable[str]] = None,
) -> tuple[list, list]:
    return parse_and_validate(
        csv_text,
        allowed_roles=("nurse",),
        existing_usernames=existing_usernames,
        existing_emails=existing_emails,
        extra_required=NURSE_EXTRA_REQUIRED,
        extra_optional=NURSE_EXTRA_OPTIONAL,
        fixed_role="nurse",
        allow_additional_roles=False,
    )


def apply_users(
    db,
    rows: list,
    hospital_id: int,
    *,
    allowed_roles: Iterable[str] = INSTALLER_ALLOWED_ROLES,
) -> dict:
    """Create User rows for every entry in ``rows``.

    Caller MUST have run :func:`parse_and_validate` against the same DB and
    confirmed it returned no errors. This function does a final re-check
    against the live DB (username/email collisions) inside the transaction
    and rolls back on any conflict — duplicates BLOCK, never skip.

    Returns ``{"created": int, "usernames": [...]}`` on success. Raises
    ``ValueError`` with a row-level message on failure (caller wraps for the
    bootstrap status file).
    """
    # Lazy imports so dbcheck (which excludes sqlalchemy) can still import this module.
    import uuid as _uuid
    from app.models.user import User, UserRole
    from app.utils.auth import get_password_hash

    allowed_roles_l = {r.lower() for r in allowed_roles}

    # Build name -> UserRole lookup once.
    role_objs = {r.name.lower(): r for r in db.query(UserRole).all()}
    for needed in allowed_roles_l:
        if needed not in role_objs:
            raise ValueError(
                f"Required role {needed!r} is not seeded in user_roles — "
                f"run db_seed first"
            )

    # Final DB-collision check (covers the dbcheck path which validates without a DB).
    _check_runtime_conflicts(db, rows)

    created_usernames = []
    for row in rows:
        primary = role_objs[row.role]
        user = User(
            user_id=str(_uuid.uuid4()),
            username=row.username,
            email=row.email,
            password_hash=get_password_hash(row.password),
            first_name=row.first_name,
            last_name=row.last_name,
            phone=row.phone or None,
            role_id=primary.id,
            hospital_id=hospital_id,
            is_active=True,
            must_change_password=True,
        )
        # Attach extra roles via the many-to-many association.
        extras = [role_objs[r.lower()] for r in row.additional_roles]
        if extras:
            user.roles = extras
        db.add(user)
        created_usernames.append(row.username)

    db.commit()
    return {"created": len(created_usernames), "usernames": created_usernames}


def _check_runtime_conflicts(db, rows):
    """Re-run username/email collision checks against the live DB. Raises
    ``ValueError`` with a row-level message on first batch of conflicts."""
    from app.models.user import User
    existing_usernames = {u for (u,) in db.query(User.username).all()}
    existing_emails = {e for (e,) in db.query(User.email).all()}
    conflicts = []
    for row in rows:
        if row.username in existing_usernames:
            conflicts.append(f"line {row.line_no}: username {row.username!r} already exists")
        if row.email in existing_emails:
            conflicts.append(f"line {row.line_no}: email {row.email!r} already exists")
    if conflicts:
        raise ValueError("; ".join(conflicts))


def apply_doctors(db, rows: list, hospital_id: int) -> dict:
    """Create User+DoctorAvailability for each parsed doctor row.

    Pre-condition: caller has run :func:`parse_and_validate_doctors` and seen
    no errors. We re-check DB collisions here as defence in depth and BLOCK
    the entire batch on any conflict (matches installer-CSV semantics).
    """
    import uuid as _uuid
    from app.models.user import User, UserRole
    from app.models.doctor_availability import DoctorAvailability
    from app.utils.auth import get_password_hash

    doctor_role = db.query(UserRole).filter(UserRole.name == "doctor").first()
    if doctor_role is None:
        raise ValueError("doctor role is not seeded — run db_seed first")

    _check_runtime_conflicts(db, rows)

    created = []
    for row in rows:
        try:
            exp = int(row.extras.get("experience_years") or 0) or None
        except ValueError:
            exp = None
        user = User(
            user_id=str(_uuid.uuid4()),
            username=row.username,
            email=row.email,
            password_hash=get_password_hash(row.password),
            first_name=row.first_name,
            last_name=row.last_name,
            phone=row.phone or None,
            specialization=row.extras.get("specialization") or None,
            qualification=row.extras.get("qualification") or None,
            license_number=row.extras.get("license_number") or None,
            consultation_fee_inr=row.extras.get("consultation_fee_inr") or None,
            inpatient_fee_inr=row.extras.get("inpatient_fee_inr") or None,
            emergency_fee_inr=row.extras.get("emergency_fee_inr") or None,
            experience_years=exp,
            role_id=doctor_role.id,
            hospital_id=hospital_id,
            is_active=True,
            must_change_password=True,
        )
        db.add(user)
        db.flush()  # need user.id for DoctorAvailability

        # Wire a default availability row so the appointment-slot generator
        # has a per-doctor consultation duration to work from.
        try:
            duration = int(row.extras.get("default_consultation_duration") or 10)
        except ValueError:
            duration = 10
        availability = DoctorAvailability(
            doctor_id=user.id,
            default_consultation_duration=duration,
        )
        db.add(availability)
        created.append(row.username)

    db.commit()
    return {"created": len(created), "usernames": created}


def apply_nurses(db, rows: list, hospital_id: int) -> dict:
    """Create User rows for each parsed nurse row. No extra profile tables."""
    import uuid as _uuid
    from app.models.user import User, UserRole
    from app.utils.auth import get_password_hash

    nurse_role = db.query(UserRole).filter(UserRole.name == "nurse").first()
    if nurse_role is None:
        raise ValueError("nurse role is not seeded — run db_seed first")

    _check_runtime_conflicts(db, rows)

    created = []
    for row in rows:
        user = User(
            user_id=str(_uuid.uuid4()),
            username=row.username,
            email=row.email,
            password_hash=get_password_hash(row.password),
            first_name=row.first_name,
            last_name=row.last_name,
            phone=row.phone or None,
            role_id=nurse_role.id,
            hospital_id=hospital_id,
            is_active=True,
            must_change_password=True,
        )
        db.add(user)
        created.append(row.username)

    db.commit()
    return {"created": len(created), "usernames": created}
