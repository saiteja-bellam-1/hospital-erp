# KT HEALTH ERP — Hospital Management System

A comprehensive hospital management system with React + shadcn/Tailwind frontend and FastAPI backend, designed for on-premise local network deployment. Distributed either as a Windows `.exe` bundle (PyInstaller) or run from source.

## 📚 Documentation

End-user and administrator guides live in [`docs/`](docs/):

- **[Inpatient User Guide](docs/INPATIENT_USER_GUIDE.md)** — complete feature walkthrough for clinical and operational staff, per-role capabilities, end-to-end patient journey, and FAQ
- **[Permissions Administrator Guide](docs/PERMISSIONS_ADMIN_GUIDE.md)** — how to configure role permissions, the default role→permission matrix, complete permission reference, and operational recommendations

Developer / architecture reference (for future contributors or AI-assisted coding): `CLAUDE.md` at the repo root and `backend/CLAUDE.md`.

## Features at a glance

### Core modules
- **Patient Management** — registration with auto-generated UUID
- **Outpatient** — appointments, queue management, check-in/out, visit recording
- **Inpatient** — full 5-phase lifecycle: admission, vitals/MAR/I/O, billing with interim bills + packages + TPA splits, consents, incidents, readmission detection, mortality + death certificates. See the [Inpatient User Guide](docs/INPATIENT_USER_GUIDE.md) for the full list.
- **Laboratory** — test configuration, orders, result entry with abnormal flagging, critical-value alerts, package booking, reports
- **Pharmacy** — medicine inventory, prescriptions, dispensing
- **EHR** — doctor consultations, prescriptions, lab order entry
- **Billing** — integrated across modules, with dashboards and referral/commission tracking
- **Audit & Quality** — configurable retention, incident reporting, mortality review, readmission tracking

### Access control

Fine-grained per-feature permissions for the inpatient module (~54 permission keys, 7 shipped roles). Hospital admins can customise role grants through the **Hospital Administration → Role Permissions** screen. See the [Permissions Admin Guide](docs/PERMISSIONS_ADMIN_GUIDE.md) for the default matrix and the complete permission reference.

Two bypass roles:
- **Super Admin** — vendor/IT senior, unrestricted
- **Hospital Admin** — hospital IT head, unrestricted within one hospital

Operational roles: `doctor`, `nurse`, `inpatient_admin`, `billing_admin`, `receptionist`, `frontdesk`, plus module admins (`lab_admin`, `pharmacy_admin`, etc.) and technicians (`lab_technician`, `pharmacist`).

## Technology stack

### Backend
- Python 3.8+ with **FastAPI**
- **SQLite** database (`kthealth_erp.db`)
- **SQLAlchemy 2.x** ORM
- **JWT** authentication (HS256, 24h expiry, bcrypt passwords)
- **Pydantic** data validation
- **ReportLab** for PDF generation
- **Ed25519** signed `.lic` license files bound to a machine ID

### Frontend
- **React 18** with functional components + hooks
- **Tailwind CSS + shadcn/ui** (Radix primitives) for UI
- **React Router** for navigation
- **@tanstack/react-query** for server state
- **react-hook-form** for forms
- **lucide-react** for icons
- **recharts** for trend graphs

## Installation & Setup

### Quick Start (Automated)

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd hospital-ERP
   ```

2. **Run the automated installer**
   ```bash
   python3 install_and_setup.py
   ```

This will automatically:
- Create a Python virtual environment
- Install all dependencies
- Set up the database with sample data
- Create default admin users

3. **Start the application**

   **Terminal 1 - Backend:**
   ```bash
   python3 run_backend.py
   ```

   **Terminal 2 - Frontend:**
   ```bash
   python3 run_frontend.py
   ```

   **Alternative (using shell scripts):**
   ```bash
   # Terminal 1
   ./start_backend.sh
   
   # Terminal 2  
   ./start_frontend.sh
   ```

### Manual Setup (if needed)

### Prerequisites
- Python 3.8 or higher
- Node.js 16 or higher
- npm or yarn

### Backend Setup

1. **Set up Python virtual environment**
   ```bash
   cd backend
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Initialize the database**
   ```bash
   cd ..
   python3 setup_database_fixed.py
   ```

4. **Start the backend server**
   ```bash
   cd backend
   source venv/bin/activate
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

### Frontend Setup

1. **Install Node.js dependencies**
   ```bash
   cd frontend
   npm install
   ```

2. **Start the development server**
   ```bash
   npm start
   ```

The application will be available at:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

## First Launch — Setup Wizard

The installer no longer creates any default accounts. The first time you open
the app in a browser (`http://localhost:3000`), the Setup Wizard runs and asks
for your hospital details and the admin username/password you want to use. No
hardcoded credentials ship with the product.

If you reset another user's password from the admin panel, that user is forced
to choose a new password the next time they log in.

## Upgrading In Place

The Windows `.exe` distribution is designed to be replaced in place: drop the
new `KTHEALTHERP.exe` over the old one in the install folder, double-click,
and the launcher will:

1. Detect the version bump by comparing the embedded `APP_VERSION` to
   `data/version.txt`. Bumps are recorded in `data/.upgrade_history.json`.
2. Boot the FastAPI server, which then runs every pending schema migration
   under the `schema_migrations` tracker. **A failed migration aborts boot**
   instead of silently serving a half-migrated DB — the failure is recorded
   for the admin Diagnostics page and surfaced by the
   `GET /api/system/health-check` endpoint.
3. Preserve `data/` (DB, uploads, `config.json`, backups) across upgrades.
   The Inno Setup installer also leaves `data/` untouched on uninstall and
   asks before wiping it.

For source installs: `git pull`, re-run `python3 install_and_setup.py` to
sync deps from `requirements.lock`, then restart the backend. The same
schema-migration runner handles the data side.

To roll back: stop the app, restore `data/kthealth_erp.db` from a snapshot
or mirror via **Dashboard → Backup Management → Restore**.

## Troubleshooting

**License upload says "wrong machine"** — The `.lic` file is bound to one
machine ID. Open **Dashboard → License**, click **Generate Rebind Request**,
send the downloaded `.rebind.json` to your vendor; they upload it to their
License Manager and email you back a fresh `.lic` for the new machine. No
manual data entry, signature proof verifies the request authenticity.

**App won't start after an upgrade** — Migration probably failed. Check
`data/logs/launcher.log` (also exposed via `GET /api/system/logs` once the
backend is up) and the `schema_migrations` table in the DB. `GET
/api/system/diagnostics` returns the migration history with error messages.

**Backup destination silently stopped working** — Open **Dashboard → Backup
Management** and look at the per-location status row. `last_error` plus a
live `writable` probe will show which destination is dead.

**Setup wizard keeps reappearing after I created the DB** — The sentinel
check now looks for an actual seeded `users` table, not just a non-empty
DB file. If the wizard reappears, the DB is either missing or has no user
rows; restore from backup or re-run the wizard.

**Default credentials don't work** — There aren't any. The Setup Wizard is
the only path that creates an admin account, with the password the operator
chose. If you've forgotten it, reset by running
`./venv/bin/python -m app.scripts.reset_admin <username>` (TODO: not yet
shipped — for now, restore from a backup).

**Forced password change dialog won't go away** — Means the `must_change_password`
flag is set on your user (either you were just seeded, or an admin reset
your password). Pick a new password to clear it; the dialog disappears
immediately on success.

**Launcher fails to create a desktop shortcut on Windows** — Look at
**Dashboard → Diagnostics** (or `GET /api/system/diagnostics`) — the
shortcut outcome is recorded in `data/.shortcut_status.json` instead of
being silently swallowed. Common causes: roaming profile with no Desktop
folder, locked-down corporate machine, or PowerShell execution policy.

## Network Deployment

For local network deployment:

1. **Update CORS settings** in `backend/main.py`:
   ```python
   allow_origins=["http://your-server-ip:3000"]
   ```

2. **Update API base URL** in frontend to point to your server IP

3. **Build production frontend**:
   ```bash
   cd frontend
   npm run build
   ```

4. **Start backend with network access**:
   ```bash
   cd backend
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

## Module Configuration

### Super Admin Tasks
- Create and manage hospitals
- Enable/disable modules for hospitals
- Create hospital administrators
- View system-wide statistics

### Hospital Admin Tasks
- Create module administrators
- Manage doctors and staff
- Configure hospital-specific settings
- View hospital statistics

### Module Admin Tasks
- Configure lab tests and templates (Lab Admin)
- Manage medicine inventory (Pharmacy Admin)
- Set up billing methods (Billing Admin)
- Configure outpatient/inpatient settings

## API Documentation

Once the backend is running, visit http://localhost:8000/docs for interactive API documentation powered by Swagger UI.

## Database Schema

The system uses SQLite with the following main entities:
- Users and Roles
- Hospitals and Module Configuration
- Patients and Medical Records
- Lab Tests and Reports
- Medicines and Prescriptions
- Billing and Payments
- Consultations and EHR
- Appointments and Visits
- Admissions and Rooms

## Import/Export Features

Module administrators can:
- Export configurations to Excel/CSV
- Import bulk configurations
- Backup and restore module data

## Security Features

- JWT-based authentication
- Role-based access control
- Password hashing with bcrypt
- Input validation and sanitization
- CORS protection
- SQL injection prevention through ORM

## Development

### Adding New Modules
1. Create database models in `backend/app/models/`
2. Create service layer in `backend/app/services/`
3. Create API routes in `backend/app/routes/`
4. Create frontend components in `frontend/src/pages/modules/`

### Database Migrations
For schema changes, modify models and restart the application. SQLAlchemy will handle basic updates.

## Support

For issues and questions:
1. Check the API documentation at `/docs`
2. Review the database schema in `database_schema.md`
3. Check server logs for error details

## License

This Hospital ERP system is proprietary software designed for healthcare institutions.

---

**Note**: This system is designed for local network deployment and contains demo data. Ensure proper security measures and data backup procedures before production use.