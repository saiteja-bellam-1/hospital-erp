# Hospital ERP System

A comprehensive Hospital Enterprise Resource Planning (ERP) system built with React frontend and Python FastAPI backend, designed for local network deployment.

## Features

### Core Modules
- **Patient Management** - Patient registration with auto-generated UUID system
- **Laboratory Management** - Lab test configuration, orders, and reports
- **Pharmacy Management** - Medicine inventory, prescriptions, and dispensing
- **Billing Management** - Integrated billing across all modules
- **EHR (Electronic Health Records)** - Doctor consultations and patient records
- **Outpatient Management** - Appointment scheduling and visit management
- **Inpatient Management** - Admission, room management, and discharge

### User Roles & Access Control
- **Super Admin** - System-wide access, hospital and module management
- **Hospital Admin** - Full hospital access, user management
- **Module Admins** - Lab, Pharmacy, Billing, Outpatient, Inpatient admins
- **Doctors** - EHR access, prescription creation, lab orders
- **Staff** - Role-based access (Nurses, Lab Technicians, Pharmacists, Receptionists)

### Key Features
- Role-based authentication and access control
- Patient UUID system for unique identification
- Integrated billing across all services
- Import/export functionality for configurations
- Local network deployment ready
- Responsive web interface

## Technology Stack

### Backend
- **Python 3.8+** with FastAPI
- **SQLite** database
- **SQLAlchemy** ORM
- **JWT** authentication
- **Pydantic** data validation

### Frontend
- **React 18** with functional components
- **Material-UI (MUI)** for UI components
- **React Router** for navigation
- **React Query** for API state management
- **Axios** for HTTP requests

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