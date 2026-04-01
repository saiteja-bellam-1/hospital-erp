"""
KT HEALTH ERP — License Manager
Standalone internal tool for generating and managing license files.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timedelta, timezone
import sqlite3
import uuid
import json
import os
import sys
import base64

app = FastAPI(title="KT HEALTH ERP — License Manager", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# When running as frozen .exe, store data (DB + keys) next to the .exe, not in temp dir
if getattr(sys, 'frozen', False):
    DATA_DIR = os.path.dirname(sys.executable)
else:
    DATA_DIR = BASE_DIR

DB_PATH = os.path.join(DATA_DIR, "licenses.db")


# ============================================================
# Database
# ============================================================

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hospital_name TEXT NOT NULL,
            hospital_id TEXT,
            contact_person TEXT,
            phone TEXT,
            email TEXT,
            address TEXT,
            machine_id TEXT,
            notes TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_id TEXT UNIQUE NOT NULL,
            customer_id INTEGER,
            hospital_id TEXT NOT NULL,
            hospital_name TEXT NOT NULL,
            machine_id TEXT NOT NULL,
            plan TEXT DEFAULT 'standard',
            max_users INTEGER DEFAULT 50,
            features TEXT DEFAULT '[]',
            modules TEXT DEFAULT '[]',
            issued_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            days INTEGER DEFAULT 365,
            status TEXT DEFAULT 'active',
            lic_file_content TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            license_id TEXT,
            payment_type TEXT DEFAULT 'license',
            payment_mode TEXT DEFAULT 'cash',
            amount REAL NOT NULL,
            invoice_number TEXT,
            description TEXT,
            payment_date TEXT DEFAULT CURRENT_TIMESTAMP,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sellers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            address TEXT,
            phone TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Add customer_id column to licenses if missing (migration for existing DBs)
    try:
        conn.execute("ALTER TABLE licenses ADD COLUMN customer_id INTEGER REFERENCES customers(id)")
    except Exception:
        pass
    conn.commit()
    conn.close()


init_db()


# ============================================================
# Crypto — Keys embedded directly (single source of truth)
# ============================================================

PRIVATE_KEY_PEM = """-----BEGIN PRIVATE KEY-----
MC4CAQAwBQYDK2VwBCIEIDYWgUAsDV5wahp2+aCkZ0wAnkS9A/jNKDqVJTfsVYw+
-----END PRIVATE KEY-----"""

PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAxtFBGBmkF6F6hdfnaC4KSVD1wbJoO5G3dP6U0juNzfs=
-----END PUBLIC KEY-----"""


def sign_license_data(license_data: dict) -> str:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    private_key = serialization.load_pem_private_key(
        PRIVATE_KEY_PEM.strip().encode(), password=None
    )
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("Invalid key type: expected Ed25519 private key")

    license_json = json.dumps(license_data, sort_keys=True, default=str)
    license_bytes = license_json.encode("utf-8")
    signature = private_key.sign(license_bytes)

    license_b64 = base64.b64encode(license_bytes).decode("utf-8")
    signature_b64 = base64.b64encode(signature).decode("utf-8")
    return f"{license_b64}\n{signature_b64}"


# ============================================================
# Schemas
# ============================================================

class CustomerCreate(BaseModel):
    hospital_name: str = Field(..., max_length=100)
    hospital_id: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    machine_id: Optional[str] = None
    notes: Optional[str] = None


class CustomerUpdate(BaseModel):
    hospital_name: Optional[str] = None
    hospital_id: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    machine_id: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[int] = None


class PaymentCreate(BaseModel):
    customer_id: int
    license_id: Optional[str] = None
    payment_type: str = Field(default="license")
    payment_mode: str = Field(default="cash")
    amount: float = Field(..., gt=0)
    invoice_number: Optional[str] = None
    description: Optional[str] = None


class SellerInfo(BaseModel):
    name: str = Field(..., max_length=200)
    address: Optional[str] = Field(None, max_length=500)
    phone: Optional[str] = Field(None, max_length=20)


class LicenseCreate(BaseModel):
    customer_id: Optional[int] = None
    hospital_id: str = Field(..., max_length=20)
    hospital_name: str = Field(..., max_length=100)
    machine_id: str = Field(..., max_length=20)
    plan: str = Field(default="standard")
    max_users: int = Field(default=50)
    days: int = Field(default=365, ge=1)
    features: List[str] = ["outpatient", "lab", "ehr", "admin"]
    modules: List[str] = []
    notes: Optional[str] = None
    seller: Optional[SellerInfo] = None


class LicenseRenew(BaseModel):
    days: int = Field(default=365, ge=1)


# ============================================================
# API Endpoints
# ============================================================

@app.get("/api/dashboard")
def dashboard():
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()

    total = conn.execute("SELECT COUNT(*) FROM licenses").fetchone()[0]
    active = conn.execute("SELECT COUNT(*) FROM licenses WHERE expires_at > ? AND status='active'", (now,)).fetchone()[0]

    soon_date = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    expiring_soon = conn.execute(
        "SELECT COUNT(*) FROM licenses WHERE expires_at <= ? AND expires_at > ? AND status='active'",
        (soon_date, now)
    ).fetchone()[0]

    expired = conn.execute("SELECT COUNT(*) FROM licenses WHERE expires_at <= ? OR status='expired'", (now,)).fetchone()[0]

    total_customers = conn.execute("SELECT COUNT(*) FROM customers WHERE is_active=1").fetchone()[0]
    total_revenue = conn.execute("SELECT COALESCE(SUM(amount),0) FROM payments").fetchone()[0]

    conn.close()
    return {
        "total": total,
        "active": active,
        "expiring_soon": expiring_soon,
        "expired": expired,
        "total_customers": total_customers,
        "total_revenue": total_revenue,
    }


@app.get("/api/licenses")
def list_licenses(search: Optional[str] = None, status: Optional[str] = None):
    conn = get_db()
    query = "SELECT * FROM licenses ORDER BY created_at DESC"
    rows = conn.execute(query).fetchall()
    conn.close()

    now = datetime.now(timezone.utc)
    results = []
    for r in rows:
        exp = datetime.fromisoformat(r["expires_at"]).replace(tzinfo=timezone.utc)
        days_left = (exp - now).days
        computed_status = "active" if days_left > 0 else "expired"
        if days_left <= 30 and days_left > 0:
            computed_status = "expiring_soon"

        record = dict(r)
        record["days_left"] = days_left
        record["computed_status"] = computed_status
        record["features"] = json.loads(record["features"]) if record["features"] else []
        record["modules"] = json.loads(record["modules"]) if record["modules"] else []

        # Apply filters
        if status and status != "all" and computed_status != status:
            continue
        if search:
            q = search.lower()
            if q not in record["hospital_name"].lower() and q not in record["hospital_id"].lower() and q not in record["machine_id"].lower():
                continue

        results.append(record)

    return results


@app.post("/api/licenses")
def create_license(data: LicenseCreate):
    now = datetime.now(timezone.utc)
    license_id = str(uuid.uuid4())

    license_data = {
        "license_id": license_id,
        "hospital_id": data.hospital_id,
        "hospital_name": data.hospital_name,
        "machine_id": data.machine_id,
        "plan": data.plan,
        "max_users": data.max_users,
        "features": data.features,
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(days=data.days)).isoformat(),
    }
    if data.seller:
        license_data["seller"] = data.seller.model_dump()

    lic_content = sign_license_data(license_data)

    conn = get_db()
    conn.execute("""
        INSERT INTO licenses (license_id, customer_id, hospital_id, hospital_name, machine_id, plan, max_users,
            features, modules, issued_at, expires_at, days, status, lic_file_content, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
    """, (
        license_id, data.customer_id, data.hospital_id, data.hospital_name, data.machine_id,
        data.plan, data.max_users,
        json.dumps(data.features), json.dumps(data.modules),
        now.isoformat(), (now + timedelta(days=data.days)).isoformat(),
        data.days, lic_content, data.notes,
    ))
    conn.commit()
    conn.close()

    return {"message": "License generated", "license_id": license_id}


@app.post("/api/licenses/{license_id}/renew")
def renew_license(license_id: str, data: LicenseRenew):
    conn = get_db()
    row = conn.execute("SELECT * FROM licenses WHERE license_id = ?", (license_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="License not found")

    now = datetime.now(timezone.utc)
    new_license_id = str(uuid.uuid4())

    license_data = {
        "license_id": new_license_id,
        "hospital_id": row["hospital_id"],
        "hospital_name": row["hospital_name"],
        "machine_id": row["machine_id"],
        "plan": row["plan"],
        "max_users": row["max_users"],
        "features": json.loads(row["features"]) if row["features"] else [],
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(days=data.days)).isoformat(),
    }

    lic_content = sign_license_data(license_data)

    # Mark old as expired
    conn.execute("UPDATE licenses SET status = 'renewed' WHERE license_id = ?", (license_id,))

    # Insert new
    conn.execute("""
        INSERT INTO licenses (license_id, hospital_id, hospital_name, machine_id, plan, max_users,
            features, modules, issued_at, expires_at, days, status, lic_file_content, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
    """, (
        new_license_id, row["hospital_id"], row["hospital_name"], row["machine_id"],
        row["plan"], row["max_users"],
        row["features"], row["modules"],
        now.isoformat(), (now + timedelta(days=data.days)).isoformat(),
        data.days, lic_content, f"Renewed from {license_id}",
    ))
    conn.commit()
    conn.close()

    return {"message": "License renewed", "license_id": new_license_id}


@app.get("/api/licenses/{license_id}/download")
def download_license(license_id: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM licenses WHERE license_id = ?", (license_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="License not found")

    filename = f"{row['hospital_name'].replace(' ', '_')}_{row['machine_id']}.lic"
    return Response(
        content=row["lic_file_content"],
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.delete("/api/licenses/{license_id}")
def delete_license(license_id: str):
    conn = get_db()
    conn.execute("DELETE FROM licenses WHERE license_id = ?", (license_id,))
    conn.commit()
    conn.close()
    return {"message": "License deleted"}


@app.get("/api/keys/status")
def keys_status():
    return {
        "private_key_exists": True,
        "public_key_exists": True,
        "public_key": PUBLIC_KEY_PEM.strip(),
    }


# ============================================================
# Customer Endpoints
# ============================================================

@app.get("/api/customers")
def list_customers(search: Optional[str] = None):
    conn = get_db()
    rows = conn.execute("SELECT * FROM customers ORDER BY created_at DESC").fetchall()
    conn.close()
    results = []
    for r in rows:
        rec = dict(r)
        if search:
            q = search.lower()
            if q not in rec["hospital_name"].lower() and q not in (rec["contact_person"] or "").lower() and q not in (rec["phone"] or ""):
                continue
        results.append(rec)
    return results


@app.post("/api/customers")
def create_customer(data: CustomerCreate):
    conn = get_db()
    cur = conn.execute("""
        INSERT INTO customers (hospital_name, hospital_id, contact_person, phone, email, address, machine_id, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (data.hospital_name, data.hospital_id, data.contact_person, data.phone, data.email, data.address, data.machine_id, data.notes))
    conn.commit()
    cid = cur.lastrowid
    conn.close()
    return {"message": "Customer created", "id": cid}


@app.get("/api/customers/{customer_id}")
def get_customer(customer_id: int):
    conn = get_db()
    customer = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if not customer:
        conn.close()
        raise HTTPException(status_code=404, detail="Customer not found")

    now = datetime.now(timezone.utc)
    licenses = conn.execute("SELECT * FROM licenses WHERE customer_id = ? ORDER BY created_at DESC", (customer_id,)).fetchall()
    payments = conn.execute("SELECT * FROM payments WHERE customer_id = ? ORDER BY payment_date DESC", (customer_id,)).fetchall()
    conn.close()

    lic_list = []
    for r in licenses:
        rec = dict(r)
        exp = datetime.fromisoformat(rec["expires_at"]).replace(tzinfo=timezone.utc)
        rec["days_left"] = (exp - now).days
        rec["computed_status"] = "active" if rec["days_left"] > 30 else ("expiring_soon" if rec["days_left"] > 0 else "expired")
        if rec["status"] == "renewed":
            rec["computed_status"] = "renewed"
        rec["features"] = json.loads(rec["features"]) if rec["features"] else []
        lic_list.append(rec)

    total_paid = sum(dict(p)["amount"] for p in payments)
    active_licenses = sum(1 for l in lic_list if l["computed_status"] in ("active", "expiring_soon"))

    return {
        "customer": dict(customer),
        "licenses": lic_list,
        "payments": [dict(p) for p in payments],
        "summary": {
            "total_licenses": len(lic_list),
            "active_licenses": active_licenses,
            "total_paid": total_paid,
            "total_payments": len(payments),
        }
    }


@app.put("/api/customers/{customer_id}")
def update_customer(customer_id: int, data: CustomerUpdate):
    conn = get_db()
    existing = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Customer not found")

    updates = {k: v for k, v in data.dict(exclude_unset=True).items() if v is not None}
    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE customers SET {set_clause} WHERE id = ?", (*updates.values(), customer_id))
        conn.commit()
    conn.close()
    return {"message": "Customer updated"}


@app.delete("/api/customers/{customer_id}")
def delete_customer(customer_id: int):
    conn = get_db()
    conn.execute("DELETE FROM payments WHERE customer_id = ?", (customer_id,))
    conn.execute("DELETE FROM licenses WHERE customer_id = ?", (customer_id,))
    conn.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
    conn.commit()
    conn.close()
    return {"message": "Customer and related records deleted"}


# ============================================================
# Seller Endpoints
# ============================================================

class SellerCreate(BaseModel):
    name: str = Field(..., max_length=200)
    address: Optional[str] = Field(None, max_length=500)
    phone: Optional[str] = Field(None, max_length=20)


@app.get("/api/sellers")
def list_sellers():
    conn = get_db()
    rows = conn.execute("SELECT * FROM sellers WHERE is_active=1 ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/sellers")
def create_seller(data: SellerCreate):
    conn = get_db()
    conn.execute("INSERT INTO sellers (name, address, phone) VALUES (?, ?, ?)",
                 (data.name, data.address, data.phone))
    conn.commit()
    conn.close()
    return {"message": "Seller created"}


@app.put("/api/sellers/{seller_id}")
def update_seller(seller_id: int, data: SellerCreate):
    conn = get_db()
    conn.execute("UPDATE sellers SET name=?, address=?, phone=? WHERE id=?",
                 (data.name, data.address, data.phone, seller_id))
    conn.commit()
    conn.close()
    return {"message": "Seller updated"}


@app.delete("/api/sellers/{seller_id}")
def delete_seller(seller_id: int):
    conn = get_db()
    conn.execute("UPDATE sellers SET is_active=0 WHERE id=?", (seller_id,))
    conn.commit()
    conn.close()
    return {"message": "Seller deactivated"}


# ============================================================
# Payment Endpoints
# ============================================================

@app.post("/api/payments")
def create_payment(data: PaymentCreate):
    conn = get_db()
    customer = conn.execute("SELECT * FROM customers WHERE id = ?", (data.customer_id,)).fetchone()
    if not customer:
        conn.close()
        raise HTTPException(status_code=404, detail="Customer not found")

    conn.execute("""
        INSERT INTO payments (customer_id, license_id, payment_type, payment_mode, amount, invoice_number, description)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (data.customer_id, data.license_id, data.payment_type, data.payment_mode, data.amount, data.invoice_number, data.description))
    conn.commit()
    conn.close()
    return {"message": "Payment recorded"}


@app.delete("/api/payments/{payment_id}")
def delete_payment(payment_id: int):
    conn = get_db()
    conn.execute("DELETE FROM payments WHERE id = ?", (payment_id,))
    conn.commit()
    conn.close()
    return {"message": "Payment deleted"}


# Serve frontend
if getattr(sys, 'frozen', False):
    frontend_dir = os.path.join(sys._MEIPASS, 'frontend_build')
else:
    frontend_dir = os.path.join(os.path.dirname(BASE_DIR), "frontend", "build")
if os.path.isdir(frontend_dir):
    app.mount("/static", StaticFiles(directory=os.path.join(frontend_dir, "static")), name="static")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        file_path = os.path.join(frontend_dir, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dir, "index.html"))
