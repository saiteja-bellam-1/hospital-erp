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

## Default Login Credentials

After running the setup script, you can use these credentials:

### Super Admin
- **Username**: `superadmin`
- **Password**: `admin123`

### Hospital Admin (Demo Hospital)
- **Username**: `hospitaladmin`
- **Password**: `hospital123`

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