import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  ChevronRight,
  ChevronDown,
  Book,
  ArrowLeft,
  Search,
  Home,
  Users,
  Stethoscope,
  Calendar,
  FileText,
  Settings,
  Shield,
  Database,
  TestTube,
  Heart,
  ClipboardList,
  Menu,
  X,
} from 'lucide-react';
import hospitalLogo from '../assets/Final Logo KT (1).jpg';

// ─── Documentation Content ────────────────────────────────────────────────────

const docs = {
  'getting-started': {
    title: 'Getting Started',
    icon: <Home className="h-4 w-4" />,
    sections: {
      'overview': {
        title: 'Overview',
        content: `
# Overview

**KT Health Soft** is a comprehensive KT HEALTH ERP (Enterprise Resource Planning) system designed for managing all aspects of hospital operations — from patient registration and appointments to lab diagnostics, prescriptions, and administration.

## Key Features

- **Multi-role access** — Super Admin, Hospital Admin, Doctor, Receptionist, Nurse, Lab Admin, Lab Technician, and Pharmacist each get a tailored interface
- **Outpatient management** — Patient registration, appointment scheduling, queue management, check-in/check-out
- **Electronic Health Records (EHR)** — Complete patient history with consultations, prescriptions, lab results, and vitals
- **Laboratory module** — Test configuration, order management, result entry with abnormal detection, PDF reports
- **Prescription system** — Create, print, and track prescriptions with dosage schedules
- **Doctor availability** — Weekly schedules, special schedules (leave/holidays), real-time status
- **Administration** — User management, role permissions, module enable/disable, hospital configuration
- **License management** — Upload and track software license status
- **Backup system** — Configure backup locations and run manual backups
- **Single executable** — Packaged as a Windows .exe for easy deployment; no separate server setup needed

## System Requirements

- **Operating System**: Windows 10 or later (for .exe deployment)
- **Browser**: Google Chrome, Microsoft Edge, or Firefox (latest version recommended)
- **Network**: All devices must be on the same local network (LAN) for multi-device access
- **Storage**: Minimum 500 MB free disk space for the application and database

## Architecture

The application runs as a local web server. When you launch the application:

1. A server starts on your computer (the host machine)
2. A browser window opens automatically to the application
3. Other computers on the same network can access it via the host's IP address
4. All data is stored locally in a SQLite database file
        `
      },
      'setup-wizard': {
        title: 'Setup Wizard',
        content: `
# Setup Wizard

The Setup Wizard runs automatically on the first launch of the application. It guides you through the initial configuration.

## Step 1: Welcome

A welcome screen introduces the application. Click **Next** to begin.

## Step 2: Hospital Information

Enter your hospital details:

| Field | Required | Description |
|-------|----------|-------------|
| Hospital Name | Yes | Your hospital or clinic name |
| Address | No | Physical address |
| Phone | No | Contact phone number |
| Email | No | Contact email address |

## Step 3: Database Location

Choose where the application database will be stored:

- **Default location** — The database is stored in the application's data folder (recommended for most users)
- **Custom location** — Click the **Browse** button to open a folder picker and select a custom directory

> **Tip**: Choose a location on a reliable drive. The database contains all patient records and hospital data.

## Step 4: Admin Account

Create the first administrator account (Super Admin):

| Field | Required | Description |
|-------|----------|-------------|
| Username | Yes | Login username (e.g., "admin") |
| Email | Yes | Admin email address |
| Password | Yes | Minimum 6 characters |
| First Name | No | Defaults to "System" |
| Last Name | No | Defaults to "Administrator" |

> **Important**: Remember these credentials. This is the only account that exists after setup. You'll use it to create all other user accounts.

## Step 5: Backup Locations

Add one or more folders where database backups will be saved:

1. Click the **Browse** button to open the folder picker
2. Select a folder (e.g., an external drive or network share)
3. Click **Add** to add it to the list
4. Repeat for additional backup locations

> **Best Practice**: Add at least one backup location on a different drive than the database.

## Step 6: Review & Install

Review all your settings and click **Complete Setup** to:

- Create the database at the chosen location
- Set up default user roles and permissions
- Create system modules
- Register the hospital
- Create your admin account

After setup completes, you'll be redirected to the login page.
        `
      },
      'first-login': {
        title: 'First Login',
        content: `
# First Login

After completing the Setup Wizard, you'll see the login page.

## Logging In

1. Enter the **Username** and **Password** you created during setup
2. Click **Sign In**
3. You'll be taken to the Dashboard

## After First Login — Recommended Steps

As the Super Admin, complete these steps to set up your hospital:

### 1. Upload Your License
- Go to **Settings > License** in the sidebar
- Click **Upload License** and select your \`.lic\` file
- The license status will update to show validity period

### 2. Configure Hospital Details
- Go to **Settings > Hospital Config**
- Fill in complete hospital information (address, city, state, etc.)
- Upload hospital logo if available

### 3. Create User Accounts
- Go to **Settings > Administration > Users** tab
- Click **Add User** to create accounts for:
  - Hospital Admins
  - Doctors (with specialization details)
  - Receptionists
  - Nurses
  - Lab Technicians
  - Lab Admins

### 4. Configure Doctor Profiles
- Go to **Settings > Hospital Config > Doctor Profiles**
- For each doctor, set:
  - Specialization
  - Consultation fee
  - Qualifications
  - Experience

### 5. Set Registration Fee
- Go to **Settings > Hospital Config > Registration Fee**
- Set the patient registration fee amount

### 6. Enable Modules
- Go to **Settings > Administration > Modules** tab
- Enable the modules your hospital needs:
  - **Laboratory** — for lab test management
  - **Pharmacy** — for medication management
  - **Inpatient** — for ward/bed management

### 7. Set Up Lab (if enabled)
- Go to **Laboratory** in the sidebar
- Use **Seed Default Templates** to load common tests (CBC, LFT, etc.)
- Customize test categories, tests, and parameters as needed

### 8. Configure Backup
- Go to **Settings > Backup**
- Verify backup locations
- Run a manual backup to confirm it works
        `
      },
    }
  },
  'super-admin': {
    title: 'Super Admin',
    icon: <Shield className="h-4 w-4" />,
    sections: {
      'dashboard': {
        title: 'Dashboard',
        content: `
# Super Admin Dashboard

The Super Admin dashboard provides a high-level overview of hospital operations.

## Statistics Cards

- **Total Patients** — Number of registered patients
- **Today's Appointments** — Appointments scheduled for today
- **Active Users** — Number of active user accounts
- **Active Modules** — Number of enabled system modules

## Navigation

The sidebar provides access to all modules and settings:

### Overview
- **Dashboard** — Main overview page
- **Patients** — Patient registry and management

### Modules (if enabled)
- **Laboratory** — Lab test configuration and management
- **Pharmacy** — Medication management
- **Billing** — Financial management
- **EHR** — Electronic Health Records
- **Outpatient** — Appointment scheduling
- **Inpatient** — Ward and bed management

### Settings
- **Administration** — Users, roles, and module management
- **Hospital Config** — Hospital details, doctor profiles, fees
- **License** — Software license management
- **Backup** — Database backup management
        `
      },
      'user-management': {
        title: 'User Management',
        content: `
# User Management

Manage all user accounts from **Settings > Administration > Users**.

## Viewing Users

The Users tab displays all registered users with:
- Name and username
- Role
- Email
- Active/Inactive status

## Creating a New User

1. Click **Add User**
2. Fill in the required fields:

| Field | Required | Description |
|-------|----------|-------------|
| Username | Yes | Unique login name |
| Email | Yes | User's email address |
| Password | Yes | Minimum 6 characters |
| First Name | Yes | User's first name |
| Last Name | Yes | User's last name |
| Role | Yes | Select from available roles |

3. Click **Create User**

## Editing a User

1. Click the **Edit** button on any user row
2. Modify the fields as needed
3. Leave password blank to keep the existing password
4. Click **Save Changes**

## Deactivating a User

1. Click the **Edit** button on the user
2. Toggle the **Active** status off
3. Save changes

> **Note**: Deactivated users cannot log in but their data is preserved.

## Available Roles

| Role | Description |
|------|-------------|
| Super Admin | Full system access — manages everything |
| Hospital Admin | Hospital-level admin — manages users, settings, and operations |
| Doctor | Clinical access — consultations, prescriptions, lab orders |
| Receptionist | Front desk — patient registration, appointments, payments |
| Nurse | Patient care support — vitals recording, patient monitoring |
| Lab Admin | Lab management — configure tests, categories, parameters |
| Lab Technician | Lab operations — process orders, enter results |
| Pharmacist | Pharmacy operations — dispense medications, manage inventory |
        `
      },
      'role-management': {
        title: 'Role & Permission Management',
        content: `
# Role & Permission Management

Manage roles and their permissions from **Settings > Administration > Roles**.

## Default Roles

The system comes with 8 pre-configured roles. Each role has specific module access and permissions.

## Viewing Role Permissions

1. Go to **Administration > Roles** tab
2. Click on any role to view its permissions
3. Permissions are organized by module

## Permission Structure

Permissions follow a module-action pattern:

### Admin Module
- \`manage_users\` — Create, edit, delete users
- \`manage_roles\` — Create, edit, delete roles
- \`manage_modules\` — Enable/disable system modules
- \`view_system_reports\` — View system-wide reports
- \`manage_settings\` — Modify system settings

### Outpatient Module
- \`schedule_appointments\` — Create and schedule appointments
- \`manage_schedules\` — Manage doctor schedules
- \`register_patients\` — Register new patients
- \`manage_queues\` — Manage patient queues and tokens
- \`view_appointments\` — View appointment lists
- \`cancel_appointments\` — Cancel existing appointments

### Laboratory Module
- \`manage_tests\` — Create and configure lab tests
- \`set_rates\` — Set test prices
- \`view_reports\` — View lab reports
- \`create_reports\` — Enter lab results and create reports
- \`manage_equipment\` — Manage lab equipment records
- \`manage_templates\` — Manage test templates

### EHR Module
- \`view_records\` — View patient health records
- \`edit_records\` — Edit/create consultation records
- \`create_prescriptions\` — Write prescriptions
- \`view_history\` — View patient history
- \`generate_reports\` — Generate health reports

### Pharmacy Module
- \`manage_inventory\` — Manage medication stock
- \`dispense_medications\` — Dispense drugs to patients
- \`view_prescriptions\` — View patient prescriptions

### Billing Module
- \`process_payments\` — Accept and process payments
- \`generate_invoices\` — Create invoices/bills
- \`view_financial_reports\` — View financial data
- \`manage_insurance\` — Manage insurance details
        `
      },
      'module-management': {
        title: 'Module Management',
        content: `
# Module Management

Enable or disable hospital modules from **Settings > Administration > Modules**.

## System Modules

| Module | Default | Can Disable | Description |
|--------|---------|-------------|-------------|
| Outpatient | Enabled | No (Core) | Patient appointments and queue management |
| EHR | Enabled | No (Core) | Electronic Health Records |
| Admin | Enabled | No (Core) | System administration |
| Laboratory | Disabled | Yes | Lab test management and reporting |
| Pharmacy | Disabled | Yes | Medication inventory and dispensing |
| Inpatient | Disabled | Yes | Ward and bed management |

## Enabling a Module

1. Go to **Administration > Modules** tab
2. Find the module you want to enable
3. Toggle the switch to **Enabled**
4. The module will appear in the sidebar for authorized roles

## Disabling a Module

1. Toggle the module switch to **Disabled**
2. The module will be hidden from the sidebar
3. Existing data is preserved — you can re-enable it later

> **Note**: Core modules (Outpatient, EHR, Admin) cannot be disabled as they are essential for basic hospital operations.
        `
      },
    }
  },
  'hospital-admin': {
    title: 'Hospital Admin',
    icon: <Settings className="h-4 w-4" />,
    sections: {
      'hospital-info': {
        title: 'Hospital Information',
        content: `
# Hospital Information

Manage hospital details from **Settings > Hospital Config > Hospital Info**.

## Editable Fields

| Field | Description |
|-------|-------------|
| Hospital Name | Official name of the hospital |
| Address | Street address |
| City | City/Town |
| State | State/Province |
| Phone | Primary contact number |
| Email | Official email address |
| Website | Hospital website URL |
| License Number | Government-issued license/registration number |
| Tax ID | Tax identification number (GST, TIN, etc.) |

## Updating Hospital Information

1. Navigate to **Hospital Config**
2. Click the **Hospital Info** tab
3. Edit the fields as needed
4. Click **Save Changes**

> **Note**: Hospital name and details appear on printed bills, prescriptions, and lab reports.
        `
      },
      'doctor-profiles': {
        title: 'Doctor Profiles',
        content: `
# Doctor Profiles

Configure doctor-specific information from **Settings > Hospital Config > Doctor Profiles**.

## Managing Doctor Profiles

1. Navigate to **Hospital Config > Doctor Profiles** tab
2. Select a doctor from the list
3. Update their profile details

## Profile Fields

| Field | Description |
|-------|-------------|
| Specialization | Medical specialty (e.g., General Medicine, Cardiology) |
| Consultation Fee | Fee charged per consultation |
| Qualifications | Degrees and certifications (e.g., MBBS, MD) |
| Experience | Years of experience |
| Registration Number | Medical council registration number |

## Why This Matters

- **Consultation Fee** is used when generating bills for patient visits
- **Specialization** helps receptionists direct patients to the right doctor
- **Qualifications** appear on prescriptions and consultation records
        `
      },
      'registration-fee': {
        title: 'Registration Fee',
        content: `
# Registration Fee

Set the patient registration fee from **Settings > Hospital Config > Registration Fee**.

## What Is the Registration Fee?

The registration fee is a one-time charge collected when a new patient is registered at the hospital. This covers:
- Patient file creation
- Initial record setup
- Hospital registration card

## Setting the Fee

1. Go to **Hospital Config > Registration Fee** tab
2. Enter the fee amount
3. Click **Save**

> **Note**: Set to 0 if your hospital doesn't charge a registration fee.
        `
      },
      'module-settings': {
        title: 'Module Settings',
        content: `
# Module Settings

Configure module-specific settings from **Settings > Hospital Config > Module Settings**.

## Available Settings

Settings vary by module. Select a module tab to configure its specific settings.

### Laboratory Settings
- Lab provider name (appears on reports)
- Lab provider address
- Report header/footer text
- Default test pricing

### Outpatient Settings
- Appointment slot duration
- Maximum appointments per slot
- Working hours configuration

> **Note**: Module settings only appear for modules that are currently enabled.
        `
      },
    }
  },
  'reception': {
    title: 'Reception',
    icon: <Calendar className="h-4 w-4" />,
    sections: {
      'dashboard': {
        title: 'Reception Dashboard',
        content: `
# Reception Dashboard

The Reception Dashboard is the home screen for receptionists, providing quick access to common tasks.

## Dashboard Sections

### Statistics Cards
- **Today's Appointments** — Count of appointments for today
- **Checked In** — Patients currently checked in
- **Completed** — Consultations completed today
- **Pending** — Appointments waiting to be seen

### Today's Appointments
Shows the 5 most recent appointments with:
- Patient name and appointment time
- Doctor name and status
- Click any appointment to navigate to the Appointments page

### Today's Lab Orders
Displays lab orders for today with:
- Patient name and test name
- Amount and payment status (Paid/Unpaid)
- **Collect Payment** button for unpaid orders
- **Download Report** button for completed tests

> **Key Responsibility**: When you see an **Unpaid** lab order, collect payment as soon as possible. The lab technician **cannot see or process** the order until it is marked as Paid. If the lab team reports a missing order, check this section first.

### Recent Prescriptions
Lists the latest prescriptions with:
- Patient name and doctor
- Date issued

### Quick Actions
- **Register New Patient** — Opens a registration form dialog
- **Schedule Appointment** — Opens the appointment scheduling dialog
        `
      },
      'patients': {
        title: 'Patient Management',
        content: `
# Patient Management

Access from **Patients** in the sidebar.

## Registering a New Patient

1. Click **Register Patient** (or use Quick Action on Dashboard)
2. Fill in the patient details:

| Field | Required | Description |
|-------|----------|-------------|
| First Name | Yes | Patient's first name |
| Last Name | Yes | Patient's last name |
| Date of Birth | Yes | For age calculation |
| Gender | Yes | Male / Female / Other |
| Phone | Yes | Primary contact number |
| Email | No | Patient's email |
| Address | No | Residential address |
| Blood Group | No | A+, A-, B+, B-, O+, O-, AB+, AB- |
| Emergency Contact Name | No | Emergency contact person |
| Emergency Contact Phone | No | Emergency contact number |

3. Click **Register** to save

## Searching for Patients

Use the search bar to find patients by:
- **Name** — First or last name
- **Phone number** — Mobile or landline
- Use **Advanced Search** for filtering by gender, blood group, or age range

## Viewing Patient Details

Click on any patient to view:
- Personal information
- Appointment history
- Vitals records
- Prescriptions
- Lab results

## Editing Patient Information

1. Click the **Edit** button on a patient card
2. Update the necessary fields
3. Click **Save Changes**
        `
      },
      'appointments': {
        title: 'Appointments',
        content: `
# Appointments

Access from **Appointments** in the sidebar.

## Creating an Appointment

1. Click **Schedule Appointment**
2. Fill in the form:

| Field | Required | Description |
|-------|----------|-------------|
| Patient | Yes | Search and select a registered patient |
| Doctor | Yes | Select from available doctors |
| Date | Yes | Appointment date |
| Time Slot | Yes | Select from available time slots |
| Reason | No | Reason for visit |

3. Click **Book Appointment**

> **Note**: Only available time slots are shown based on the doctor's schedule and existing bookings.

## Appointment Status Flow

\`\`\`
Scheduled → Checked In → Checked Out / Completed
    ↓            ↓
Cancelled    Cancelled
    ↓
Rescheduled → Scheduled
\`\`\`

## Check-In

1. Find the appointment in today's list
2. Click **Check In**
3. A queue token number is automatically assigned
4. The patient appears in the doctor's queue

## Check-Out

1. After the doctor completes the consultation
2. Click **Check Out** on the appointment
3. The appointment status changes to Completed

## Rescheduling

1. Click **Reschedule** on an appointment
2. Select a new date and time slot
3. Confirm the reschedule

## Cancelling

1. Click **Cancel** on an appointment
2. Enter a reason for cancellation
3. Confirm the cancellation

## Appointment Card Actions

Each appointment card shows:
- Patient name and age/gender
- Doctor name and time
- Status badge (Scheduled, Checked In, Completed, Cancelled)
- Action buttons based on current status

### Available Actions by Status

| Status | Available Actions |
|--------|-------------------|
| Scheduled | Check In, Reschedule, Cancel, Notes |
| Checked In | Check Out, View Prescription, Lab Payment, Cancel |
| Completed | View Prescription, View Bill, Download Lab Report |
| Cancelled | (No actions — view only) |

## Lab Payments

Lab tests ordered by a doctor must be **paid at reception** before the lab technician can process them. This is a critical step in the workflow.

### How Lab Payment Works

\`\`\`
Doctor orders lab tests → Order created (status: "Unpaid")
     ↓
Reception collects payment → Order becomes "Paid"
     ↓
Lab technician can now see and process the order
\`\`\`

### Collecting Lab Payment

1. Find the patient's appointment (status: **Checked In** or later)
2. Click **Lab Payment** on the appointment card
3. A dialog opens showing all **unpaid lab tests** for that patient:
   - Test name
   - Test amount
   - Total amount due
4. Select the **Payment Method** (Cash, Card, UPI, etc.)
5. Click **Collect Payment**
6. A **Lab Bill PDF** is generated and downloaded automatically
7. The lab orders are now marked as **Paid**

> **Important**: The lab technician's dashboard **only shows paid orders**. If the receptionist forgets to collect payment, the lab technician will not see the order at all. Always collect lab payment promptly after the doctor places the order.

### Common Scenarios

| Scenario | What to do |
|----------|------------|
| Lab tech says "I don't see the order" | Check if payment was collected — open the patient's appointment and look for unpaid lab tests |
| Patient wants to pay later | The order stays in "Unpaid" status. Lab work cannot begin until payment is collected |
| Multiple tests ordered | All unpaid tests for the patient are shown together. Payment is collected for all at once |
| Doctor orders additional tests after initial payment | A new payment collection is needed for the newly ordered tests |

### Where to Find Lab Payment Button

- **Appointments page** — On appointment cards with status "Checked In" or later
- **Reception Dashboard** — In the "Today's Lab Orders" section, unpaid orders show a "Collect Payment" button

## Viewing Bills & Prescriptions

- Click **View Prescription** to see/print the prescription
- Click **View Bill** to see the consultation bill
- Click **Download Report** to get completed lab reports as PDF

> **Note**: Consultation bills and lab bills are **separate**. The consultation bill covers the doctor's fee and registration charges. The lab bill covers only lab test charges.
        `
      },
      'doctor-schedule': {
        title: 'Doctor Schedule',
        content: `
# Doctor Schedule

View doctor availability from **Doctor Schedule** in the sidebar.

## Viewing Schedules

1. Select a doctor from the dropdown
2. Toggle between **Day View** and **Week View**
3. Navigate dates using the arrow buttons

## Schedule Information

- **Green slots** — Available for booking
- **Gray slots** — Already booked or unavailable
- **Special schedules** — Holidays, leave days, or modified hours are highlighted

## Using Schedule for Booking

When a patient requests a specific doctor or time, use this page to:
1. Check the doctor's availability
2. Identify open slots
3. Navigate to Appointments to book the slot
        `
      },
      'reports': {
        title: 'Reports',
        content: `
# Reception Reports

Access from **Reports** in the sidebar.

## Daily Summary

View a summary of the day's activity:
- Total appointments
- Completed vs. cancelled
- Revenue collected
- Patient registrations

## Report Filters

- **Date range** — Select start and end dates
- **Doctor** — Filter by specific doctor

## Report Sections

### Appointment Statistics
- Total appointments by status
- Completion rate
- Average wait time

### Revenue Breakdown
- Consultation fees collected
- Registration fees
- Lab payment collections

### Doctor-wise Statistics
- Appointments per doctor
- Completion rate per doctor
- Revenue per doctor
        `
      },
    }
  },
  'doctor': {
    title: 'Doctor',
    icon: <Stethoscope className="h-4 w-4" />,
    sections: {
      'dashboard': {
        title: 'Doctor Dashboard',
        content: `
# Doctor Dashboard

The Doctor Dashboard is the primary workspace for doctors, showing appointments, patient queue, and quick access to clinical functions.

## Dashboard Layout

### Today's Appointments
Lists all appointments for the current day:
- Patient name, age, and gender
- Appointment time
- Status (Scheduled, Checked In, In Progress, Completed)
- Click any appointment to start/view consultation

### Queue View
Shows the current patient queue across all doctors:
- Token numbers
- Patient names
- Wait time
- Current status

### Statistics
- **Today's Patients** — Total appointments today
- **In Progress** — Currently being consulted
- **Completed** — Finished consultations
- **Pending** — Waiting in queue

## Auto-Refresh

The dashboard automatically refreshes every 30 seconds to show:
- New check-ins
- Updated queue positions
- Status changes
        `
      },
      'consultation': {
        title: 'Consultation',
        content: `
# Recording a Consultation

When a checked-in patient is ready, click their appointment to begin the consultation.

## Consultation Form

### Vitals (Optional)
Record patient vital signs:
- Blood Pressure (systolic/diastolic)
- Heart Rate (BPM)
- Temperature (°F/°C)
- Weight (kg)
- Height (cm)
- Respiratory Rate
- SpO2 (Oxygen saturation)

### Clinical Information

| Field | Description |
|-------|-------------|
| Consultation Type | Outpatient, Follow-up, Emergency |
| Chief Complaint | Primary reason for visit |
| Present History | History of present illness |
| Examination Findings | Physical examination notes |
| Diagnosis | Clinical diagnosis |
| Notes | Additional clinical notes |
| Follow-up Date | Next visit recommendation |

### Saving the Consultation

1. Fill in the relevant fields
2. Click **Save Consultation**
3. The consultation is recorded in the patient's EHR
4. You can then proceed to write prescriptions or order lab tests
        `
      },
      'prescriptions': {
        title: 'Prescriptions',
        content: `
# Writing Prescriptions

After recording a consultation, you can write a prescription for the patient.

## Creating a Prescription

1. From the consultation view, click **Write Prescription**
2. Add medications:

### For Each Medication

| Field | Description |
|-------|-------------|
| Medicine Name | Name of the drug |
| Dosage | Dose amount (e.g., 500mg) |
| Frequency | Schedule pattern using 1-0-0 format |
| Duration | Number of days/weeks |
| Food Timing | Before food, After food, With food, Empty stomach, Anytime |
| Quantity | Total quantity to dispense |
| Instructions | Special instructions |

### Frequency Format (1-0-0)

The frequency uses a three-number pattern: **Morning - Afternoon - Night**

| Pattern | Meaning |
|---------|---------|
| 1-0-0 | Once daily, morning only |
| 1-0-1 | Twice daily, morning and night |
| 1-1-1 | Three times daily |
| 0-0-1 | Once daily, night only |
| 1-1-0 | Twice daily, morning and afternoon |

## Adding Multiple Medications

Click **Add Medicine** to add more medications to the same prescription.

## Diagnosis & Notes

- Enter the **Diagnosis** for the prescription
- Add any **Notes** for the patient or pharmacy

## Saving & Printing

1. Click **Save Prescription** to save
2. Click **Print Preview** to see the formatted prescription
3. Click **Print** to send to printer

The printed prescription includes:
- Hospital name and logo
- Doctor name and qualifications
- Patient details
- All medications with dosage instructions
- Diagnosis
- Prescription ID (RX-YYYYMMDD-XXXX)
        `
      },
      'lab-orders': {
        title: 'Lab Orders',
        content: `
# Ordering Lab Tests

Doctors can order lab tests directly from the consultation screen.

## Creating a Lab Order

1. From the consultation view, click **Order Lab Tests**
2. Browse or search available tests
3. Select the tests to order
4. Set priority:
   - **Normal** — Standard processing
   - **Urgent** — Priority processing
5. Add any notes for the lab
6. Click **Place Order**

## Lab Order Flow

\`\`\`
Doctor Orders Lab Test
     ↓
Order created (status: Unpaid, visible to Reception)
     ↓
Reception collects payment from patient (status: Paid)
     ↓
Lab Technician sees the order in their dashboard
     ↓
Lab Tech: Collect Sample → Process → Enter Results
     ↓
Results available to Doctor (and downloadable as PDF)
\`\`\`

> **Important**: Lab technicians will **only** see orders after the reception has collected payment. If you've ordered a test but the lab team hasn't received it, ask the reception to check the payment status.

### What Happens After You Order

1. The order appears in the **Reception Dashboard** under "Today's Lab Orders" as **Unpaid**
2. The receptionist collects payment from the patient and marks it as **Paid**
3. The order then appears in the **Lab Technician's dashboard**
4. Once results are entered, you'll see them in the patient's appointment view with abnormal values highlighted

## Viewing Lab Results

1. From the patient's appointment, click **View Lab Results**
2. Results show:
   - Test name and parameters
   - Patient values vs. reference ranges
   - **Abnormal values** are highlighted in red
   - Interpretation notes from the lab technician
3. Click **Download Report** to get the PDF

## Lab Results Indicators

- **Normal** — Value within reference range (shown in green)
- **Abnormal** — Value outside reference range (shown in red with highlighting)
- **Pending** — Results not yet entered
        `
      },
      'availability': {
        title: 'Availability Management',
        content: `
# Availability Management

Manage your schedule from **Availability** in the sidebar.

## Weekly Schedule

Set your regular working hours for each day of the week:

1. Go to **Availability**
2. For each day (Monday through Sunday):
   - Toggle the day **On/Off**
   - Set **Start Time** and **End Time**
   - Add **Break Time** (e.g., lunch break)
3. Configure global settings:
   - **Slot Duration** — Length of each appointment slot (e.g., 15 min, 30 min)
   - **Buffer Time** — Gap between appointments
   - **Max Advance Booking** — How many days ahead patients can book
4. Click **Save Schedule**

## Special Schedules

For one-time schedule changes (holidays, leave, modified hours):

1. Click **Add Special Schedule**
2. Select the type:
   - **Holiday** — Hospital is closed
   - **Leave** — You're on leave
   - **Modified Hours** — Different timing for a specific day
   - **Emergency Only** — Only emergency appointments accepted
3. Set the **Date** and **Reason**
4. For modified hours, enter the new start/end times
5. Click **Save**

## Current Status

Update your real-time availability status:

| Status | Meaning |
|--------|---------|
| Available | Ready to see patients |
| Busy | Temporarily unavailable |
| In Consultation | Currently with a patient |
| On Break | On scheduled break |
| Unavailable | Not available for consultations |

You can also set:
- **Status Message** — Brief note (e.g., "Back in 15 minutes")
- **Expected Return Time** — When you'll be available again
- **Emergency Only** — Accept only emergency cases
        `
      },
    }
  },
  'laboratory': {
    title: 'Laboratory',
    icon: <TestTube className="h-4 w-4" />,
    sections: {
      'admin-config': {
        title: 'Lab Admin Configuration',
        content: `
# Lab Admin Configuration

Lab Admins configure tests, categories, and parameters from **Laboratory** in the sidebar.

## Categories

Organize tests into categories (e.g., Hematology, Biochemistry, Microbiology).

### Creating a Category
1. Go to **Laboratory > Categories** tab
2. Click **Add Category**
3. Enter the category name and description
4. Click **Save**

## Tests

### Creating a Test
1. Go to **Laboratory > Tests** tab
2. Click **Add Test**
3. Fill in the details:

| Field | Description |
|-------|-------------|
| Test Name | Name of the test (e.g., Complete Blood Count) |
| Short Name | Abbreviation (e.g., CBC) |
| Category | Select from created categories |
| Sample Type | Blood, Urine, Stool, etc. |
| Method | Testing methodology |
| Cost | Test price |
| TAT (hours) | Turnaround time |
| Preparation | Patient preparation instructions |

4. Click **Save**

## Parameters

Each test can have multiple parameters (e.g., CBC has Hemoglobin, WBC, RBC, Platelets, etc.).

### Adding a Parameter
1. Select a test
2. Click **Add Parameter**
3. Configure:

| Field | Description |
|-------|-------------|
| Parameter Name | Name (e.g., Hemoglobin) |
| Short Name | Abbreviation (e.g., Hb) |
| Unit | Measurement unit (e.g., g/dL) |
| Field Type | Numeric, Text, or Select |
| Reference Range (Male) | Normal range for males |
| Reference Range (Female) | Normal range for females |
| Possible Values | For Select type — dropdown options |

4. Click **Save**

> **Note**: Gender-specific reference ranges are used to detect abnormal values automatically.

## Seed Templates

Load pre-configured test templates to get started quickly:

1. Go to **Laboratory > Dashboard** tab
2. Click **Load Default Templates**
3. The following templates are loaded:
   - **CBC** (Complete Blood Count)
   - **LFT** (Liver Function Test)
   - **RFT** (Renal Function Test)
   - **Lipid Profile**
   - **Thyroid Profile**
   - **Blood Sugar**
   - **Urine Routine**

Each template includes the test, all parameters, and gender-specific reference ranges.
        `
      },
      'technician-workflow': {
        title: 'Lab Technician Workflow',
        content: `
# Lab Technician Workflow

Lab technicians process orders and enter results from the **Lab Dashboard**.

## Dashboard Overview

The Lab Dashboard shows:
- **Pending Orders** — Orders waiting to be processed
- **In Progress** — Currently being processed
- **Completed** — Finished orders

> **Important**: Only orders with payment status **"Paid"** appear in the lab dashboard. Unpaid orders are completely hidden until the reception collects payment.

## Why Can't I See a Lab Order?

If a doctor has ordered a test but you don't see it in your dashboard, the most common reason is that **payment has not been collected yet**.

### Payment Gate — How It Works

\`\`\`
Doctor orders test → Order is "Unpaid" → NOT visible to Lab Tech
                          ↓
              Reception collects payment
                          ↓
                   Order is "Paid" → NOW visible to Lab Tech
\`\`\`

### What to Do

1. **Contact reception** and ask them to check if the patient's lab payment has been collected
2. The receptionist can find the order in:
   - **Reception Dashboard > Today's Lab Orders** (shows Unpaid badge)
   - **Appointments page** — click **Lab Payment** on the patient's appointment
3. Once the receptionist collects payment, the order will **immediately appear** in your dashboard
4. **Refresh your dashboard** (or wait for auto-refresh) to see newly paid orders

> **Tip**: If you're expecting an order and it's not showing up, always check with reception first. The system is designed this way to ensure all lab work is billed before processing begins.

## Processing an Order

### Step 1: Collect Sample
1. Find the order in the pending list
2. Click **Collect Sample**
3. The order status changes to "Collected"

### Step 2: Process Sample
1. Click **Start Processing**
2. The order status changes to "Processing"

### Step 3: Enter Results
1. Click **Enter Results** on the order
2. For each parameter, enter the patient's value
3. The system automatically flags abnormal values:
   - Values outside the reference range are highlighted
   - Uses gender-specific ranges when available
4. Add **Interpretation** notes (optional)
5. Add **Technical Notes** (optional)
6. Click **Submit Results**

### Step 4: Report Generated
- The system generates a lab report automatically
- The report is available for download as PDF
- Doctors can view results in their dashboard
- Receptionists can download reports for patients

## Searching Orders

Use the search bar to find orders by:
- Patient name
- Order number
- Test name

## Filtering Orders

Filter the order list by:
- **Status** — All, Pending, Collected, Processing, Completed
- **Date** — Today, This Week, Custom Range
        `
      },
      'reports': {
        title: 'Lab Reports',
        content: `
# Lab Reports

## Report Contents

Each lab report PDF includes:
- **Header** — Lab provider name and address (or hospital info if not configured)
- **Patient Details** — Name, age, gender, patient ID
- **Doctor Details** — Ordering doctor's name
- **Test Results** — All parameters with:
  - Parameter name and unit
  - Patient's value
  - Reference range
  - Abnormal flag (if outside range)
- **Interpretation** — Lab technician's interpretation
- **Footer** — Report date, order number

## Downloading Reports

### For Doctors
- From the consultation view, click **View Lab Results**
- Click **Download Report** for any completed test

### For Receptionists
- From the appointment card, click **Download Report**
- From the Reception Dashboard, click download icon on completed lab orders

### For Lab Technicians
- From the Lab Dashboard, click download icon on completed orders

## Lab Provider Configuration

To customize the lab report header:
1. Go to **Hospital Config > Module Settings > Laboratory**
2. Set:
   - Lab Provider Name
   - Lab Provider Address
   - Report header text
3. If not set, hospital information is used as fallback
        `
      },
    }
  },
  'nurse': {
    title: 'Nurse',
    icon: <Heart className="h-4 w-4" />,
    sections: {
      'dashboard': {
        title: 'Nurse Dashboard',
        content: `
# Nurse Dashboard

The Nurse Station is the primary workspace for nurses.

## Features

### Patient List
- View all patients currently checked in
- Search patients by name or phone
- Quick access to patient vitals

### Today's Appointments
- View appointments for today
- See patient status (waiting, with doctor, completed)

## Recording Vitals

1. Select a patient from the list
2. Click **Record Vitals**
3. Enter the measurements:

| Vital Sign | Unit | Description |
|------------|------|-------------|
| Blood Pressure | mmHg | Systolic/Diastolic (e.g., 120/80) |
| Heart Rate | BPM | Beats per minute |
| Temperature | °F/°C | Body temperature |
| Weight | kg | Patient weight |
| Height | cm | Patient height |
| Respiratory Rate | breaths/min | Breathing rate |
| SpO2 | % | Oxygen saturation |

4. Click **Save Vitals**

> **Note**: Vitals are saved to the patient's EHR and are visible to doctors during consultations.
        `
      },
    }
  },
  'ehr': {
    title: 'Electronic Health Records',
    icon: <FileText className="h-4 w-4" />,
    sections: {
      'overview': {
        title: 'EHR Overview',
        content: `
# Electronic Health Records (EHR)

Access from **EHR** in the sidebar (available to Super Admin, Hospital Admin, and Doctors).

## Patient Search

1. Search for a patient using the search bar
2. Search by name, phone number, or patient ID
3. Select a patient from the results

## Patient History Timeline

The EHR displays a complete timeline of the patient's medical history:

### Consultations
- Date and time
- Consulting doctor
- Chief complaint and diagnosis
- Examination findings
- Follow-up recommendations

### Prescriptions
- All prescribed medications with dosage details
- Prescription status (Active, Completed, Cancelled)
- Prescription ID for reference

### Lab Results
- Ordered tests and their results
- Parameter values with reference ranges
- Abnormal value highlighting
- Download links for PDF reports

### Vitals History
- All recorded vital signs over time
- Trend visualization

## Expanding Details

- Click on any record to expand and see full details
- Use the **Collapse All** button to minimize all sections
- Records are displayed in reverse chronological order (newest first)

## PDF Export

Click **Export PDF** to generate a comprehensive patient report containing:
- Patient demographics
- Complete consultation history
- All prescriptions
- Lab results summary
- Vitals trends
        `
      },
    }
  },
  'license-backup': {
    title: 'License & Backup',
    icon: <Database className="h-4 w-4" />,
    sections: {
      'license': {
        title: 'License Management',
        content: `
# License Management

Access from **Settings > License** in the sidebar.

## License Status

The license page shows:
- **Current Status** — Active, Expiring Soon, Grace Period, Expired, or No License
- **Days Remaining** — Number of days until expiration
- **License Details** — License type and validity period

## Status Indicators

| Status | Color | Description |
|--------|-------|-------------|
| Active | Green | License is valid and active |
| Expiring Soon | Yellow | Less than 30 days remaining |
| Grace Period | Orange | License expired but in grace period |
| Expired | Red | License has fully expired |
| No License | Gray | No license file uploaded |

## Uploading a License

1. Go to **License** page
2. Click **Upload License**
3. Select your \`.lic\` file
4. The system validates and activates the license
5. Status updates immediately

## License Banner

When the license is expiring or expired, a banner appears at the top of every page:
- **Yellow banner** — License expiring soon (reminder to renew)
- **Red banner** — License expired (limited functionality)

> **Contact your software provider to obtain or renew your license file.**
        `
      },
      'backup': {
        title: 'Backup Management',
        content: `
# Backup Management

Access from **Settings > Backup** in the sidebar.

## Why Backup?

The application stores all data in a local SQLite database. Regular backups protect against:
- Hardware failure
- Accidental data deletion
- System crashes
- Ransomware or malware

## Configuring Backup Locations

1. Go to **Backup** page
2. Click **Add Location**
3. Enter or browse for a folder path
4. Click **Validate** to check if the path is writable
5. Click **Save**

### Recommended Backup Locations
- External USB drive
- Network-attached storage (NAS)
- A different hard drive partition
- Cloud-synced folder (Dropbox, OneDrive, Google Drive)

## Running a Backup

1. Go to **Backup** page
2. Click **Run Backup Now**
3. The system copies the database to all configured locations
4. A timestamped copy is created (e.g., \`kthealth_erp_2026-03-13_14-30-00.db\`)
5. Success/failure status is shown for each location

## Backup Best Practices

- Run backups **daily** at minimum
- Keep at least **3 backup copies** at all times
- Use **multiple locations** (don't rely on a single backup)
- **Test your backups** periodically by restoring to a test environment
- Store at least one backup **off-site** (external drive stored elsewhere)

> **Important**: The backup copies the entire database. To restore, simply replace the main database file with a backup copy and restart the application.
        `
      },
    }
  },
  'troubleshooting': {
    title: 'Troubleshooting',
    icon: <ClipboardList className="h-4 w-4" />,
    sections: {
      'common-issues': {
        title: 'Common Issues',
        content: `
# Troubleshooting

## Common Issues

### Cannot Login
- **Check credentials** — Verify username and password are correct
- **Check license** — An expired license may block login
- **Clear browser cache** — Press Ctrl+Shift+Delete and clear cached data
- **Check server** — Ensure the application (KTHEALTHERP.exe) is running

### Application Won't Start
- **Port conflict** — Another application may be using port 8000. The launcher will try ports 8001, 8002, etc.
- **Missing data folder** — The application creates a \`data/\` folder on first run. Ensure the directory is writable
- **Antivirus blocking** — Some antivirus software may flag the .exe. Add it to your exceptions list

### Cannot Access from Another Computer
- **Same network** — Both computers must be on the same LAN/WiFi network
- **Use correct IP** — Use the IP address shown in the launcher console (e.g., http://192.168.1.100:8000)
- **Firewall** — Windows Firewall may block the connection. Allow the application through the firewall
- **Port** — Ensure you're using the correct port (shown in the launcher)

### Lab Orders Not Showing for Lab Tech

This is the most common support question. The system uses a **payment gate** — lab technicians can only see and process orders that have been paid.

**Step-by-step resolution:**

1. **Ask reception to check payment** — The receptionist should open the patient's appointment and look for unpaid lab orders
2. **Receptionist collects payment** — Click "Lab Payment" on the appointment card, select payment method, and click "Collect Payment"
3. **Lab tech refreshes dashboard** — The order will now appear in the lab dashboard
4. **If payment was already collected** — Try refreshing the page (F5). Check the date filter — the order may be from a different date

**Why this happens:**
- The doctor orders a test during consultation
- The order is created with status "Unpaid"
- The receptionist must explicitly collect payment before the lab can begin work
- This ensures no lab work is done without billing

### Lab Payment Button Not Visible on Appointment
- The appointment must be in **Checked In** status or later
- There must be **unpaid lab orders** for that patient
- If the patient has no pending lab orders, the button won't appear

### Prescription Not Printing
- **Browser popup blocker** — Allow popups for the application URL
- **Printer offline** — Check printer connection and status
- **Try PDF download** — Use the download option instead of direct print

### Database Errors
- **Disk full** — Ensure the drive has sufficient free space
- **File locked** — Close any other programs that might be accessing the database file
- **Corrupt database** — Restore from the most recent backup

## Getting Help

If you encounter issues not listed here:
1. Check the application console window for error messages
2. Note the exact error message and steps to reproduce
3. Contact your system administrator or software support
        `
      },
      'keyboard-shortcuts': {
        title: 'Tips & Shortcuts',
        content: `
# Tips & Shortcuts

## Browser Tips

| Action | Shortcut |
|--------|----------|
| Refresh page | F5 or Ctrl+R |
| Hard refresh (clear cache) | Ctrl+Shift+R |
| Print current page | Ctrl+P |
| Zoom in | Ctrl++ |
| Zoom out | Ctrl+- |
| Reset zoom | Ctrl+0 |
| Full screen | F11 |

## Application Tips

### For Receptionists
- Use the **Dashboard Quick Actions** for fastest patient registration and appointment scheduling
- The **Doctor Schedule** page helps quickly find available slots
- Check appointment status colors at a glance: Green = Completed, Blue = Checked In, Yellow = Scheduled, Red = Cancelled

### For Doctors
- The dashboard **auto-refreshes** every 30 seconds — no need to manually reload
- Use the **1-0-0 format** for prescription frequency (Morning-Afternoon-Night)
- **Abnormal lab values** are automatically highlighted in red — no manual checking needed

### For Lab Technicians
- Orders appear only after **payment is collected** — if you don't see an expected order, check with reception
- **Abnormal detection** is automatic based on reference ranges — just enter the values
- Use **Seed Templates** to quickly set up standard tests with proper reference ranges

### For Administrators
- **Disable unused modules** to keep the interface clean for all users
- Set up **backup locations** on multiple drives for safety
- Review **role permissions** to ensure proper access control
- Keep the **license** updated to avoid service interruptions

## Data Safety

- The application auto-saves all data — there's no "Save" button needed for most operations
- **Never close the server while users are working** — announce maintenance windows
- Run backups before any system updates or changes
- Keep a copy of your license file in a safe location
        `
      },
    }
  },
};

// ─── Documentation Viewer Component ──────────────────────────────────────────

const HelpDocs = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedSections, setExpandedSections] = useState({});
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  // Get current page from URL params
  const currentCategory = searchParams.get('category') || 'getting-started';
  const currentSection = searchParams.get('section') || Object.keys(docs[currentCategory]?.sections || {})[0] || '';

  // Initialize expanded sections
  useEffect(() => {
    setExpandedSections(prev => ({ ...prev, [currentCategory]: true }));
  }, [currentCategory]);

  const navigateTo = (category, section) => {
    setSearchParams({ category, section });
    setMobileSidebarOpen(false);
    window.scrollTo(0, 0);
  };

  const toggleSection = (key) => {
    setExpandedSections(prev => ({ ...prev, [key]: !prev[key] }));
  };

  // Get current content
  const currentDoc = docs[currentCategory];
  const currentContent = currentDoc?.sections?.[currentSection]?.content || '';

  // Search functionality
  const searchResults = searchQuery.trim()
    ? Object.entries(docs).flatMap(([catKey, cat]) =>
        Object.entries(cat.sections)
          .filter(([, sec]) =>
            sec.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
            sec.content.toLowerCase().includes(searchQuery.toLowerCase())
          )
          .map(([secKey, sec]) => ({
            category: catKey,
            categoryTitle: cat.title,
            section: secKey,
            title: sec.title,
          }))
      )
    : [];

  // Simple markdown renderer
  const renderMarkdown = (md) => {
    const lines = md.trim().split('\n');
    const elements = [];
    let i = 0;
    let inTable = false;
    let tableRows = [];
    let inCodeBlock = false;
    let codeLines = [];
    let listItems = [];
    let inBlockquote = false;
    let blockquoteLines = [];

    const flushList = () => {
      if (listItems.length > 0) {
        elements.push(
          <ul key={`list-${elements.length}`} className="space-y-1.5 my-3 ml-1">
            {listItems.map((item, idx) => (
              <li key={idx} className="flex gap-2 text-[14px] leading-relaxed text-gray-700">
                <span className="text-primary mt-1.5 flex-shrink-0">•</span>
                <span dangerouslySetInnerHTML={{ __html: inlineFormat(item) }} />
              </li>
            ))}
          </ul>
        );
        listItems = [];
      }
    };

    const flushBlockquote = () => {
      if (blockquoteLines.length > 0) {
        elements.push(
          <div key={`bq-${elements.length}`} className="border-l-4 border-blue-400 bg-blue-50 px-4 py-3 my-4 rounded-r-lg">
            {blockquoteLines.map((line, idx) => (
              <p key={idx} className="text-[13.5px] text-blue-800" dangerouslySetInnerHTML={{ __html: inlineFormat(line) }} />
            ))}
          </div>
        );
        blockquoteLines = [];
        inBlockquote = false;
      }
    };

    const flushTable = () => {
      if (tableRows.length > 0) {
        const headerRow = tableRows[0];
        const dataRows = tableRows.slice(1).filter(r => !r.match(/^\|[\s-:|]+\|$/));
        elements.push(
          <div key={`table-${elements.length}`} className="my-4 overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="bg-gray-50">
                  {headerRow.split('|').filter(c => c.trim()).map((cell, idx) => (
                    <th key={idx} className="px-4 py-2.5 text-left font-semibold text-gray-700 border-b border-gray-200">
                      {cell.trim()}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {dataRows.map((row, rIdx) => (
                  <tr key={rIdx} className={rIdx % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'}>
                    {row.split('|').filter(c => c.trim()).map((cell, cIdx) => (
                      <td key={cIdx} className="px-4 py-2 text-gray-600 border-b border-gray-100" dangerouslySetInnerHTML={{ __html: inlineFormat(cell.trim()) }} />
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
        tableRows = [];
        inTable = false;
      }
    };

    const inlineFormat = (text) => {
      return text
        .replace(/`([^`]+)`/g, '<code class="px-1.5 py-0.5 bg-gray-100 rounded text-[12.5px] font-mono text-rose-600">$1</code>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong class="font-semibold text-gray-900">$1</strong>')
        .replace(/\*([^*]+)\*/g, '<em>$1</em>')
        .replace(/\\`/g, '`');
    };

    while (i < lines.length) {
      const line = lines[i];

      // Code blocks
      if (line.trim().startsWith('```')) {
        if (inCodeBlock) {
          flushList();
          elements.push(
            <pre key={`code-${elements.length}`} className="bg-gray-900 text-gray-100 p-4 rounded-lg my-4 overflow-x-auto text-[13px] font-mono leading-relaxed">
              {codeLines.join('\n')}
            </pre>
          );
          codeLines = [];
          inCodeBlock = false;
        } else {
          flushList();
          flushBlockquote();
          flushTable();
          inCodeBlock = true;
        }
        i++;
        continue;
      }
      if (inCodeBlock) {
        codeLines.push(line);
        i++;
        continue;
      }

      // Empty line
      if (line.trim() === '') {
        flushList();
        flushBlockquote();
        flushTable();
        i++;
        continue;
      }

      // Headings
      if (line.startsWith('# ')) {
        flushList(); flushBlockquote(); flushTable();
        elements.push(
          <h1 key={`h1-${i}`} className="text-2xl font-bold text-gray-900 mb-2 mt-1 pb-3 border-b border-gray-200">
            {line.replace('# ', '')}
          </h1>
        );
        i++;
        continue;
      }
      if (line.startsWith('## ')) {
        flushList(); flushBlockquote(); flushTable();
        elements.push(
          <h2 key={`h2-${i}`} className="text-xl font-semibold text-gray-800 mt-8 mb-3">
            {line.replace('## ', '')}
          </h2>
        );
        i++;
        continue;
      }
      if (line.startsWith('### ')) {
        flushList(); flushBlockquote(); flushTable();
        elements.push(
          <h3 key={`h3-${i}`} className="text-base font-semibold text-gray-700 mt-6 mb-2">
            {line.replace('### ', '')}
          </h3>
        );
        i++;
        continue;
      }

      // Blockquotes
      if (line.startsWith('> ')) {
        flushList(); flushTable();
        inBlockquote = true;
        blockquoteLines.push(line.replace(/^>\s*/, ''));
        i++;
        continue;
      }

      // Tables
      if (line.trim().startsWith('|')) {
        flushList(); flushBlockquote();
        inTable = true;
        tableRows.push(line.trim());
        i++;
        continue;
      }

      // Unordered list
      if (line.match(/^-\s/) || line.match(/^\s+-\s/)) {
        flushBlockquote(); flushTable();
        listItems.push(line.replace(/^\s*-\s/, ''));
        i++;
        continue;
      }

      // Paragraph
      flushList(); flushBlockquote(); flushTable();
      elements.push(
        <p key={`p-${i}`} className="text-[14px] leading-relaxed text-gray-700 my-2" dangerouslySetInnerHTML={{ __html: inlineFormat(line) }} />
      );
      i++;
    }

    flushList();
    flushBlockquote();
    flushTable();

    return elements;
  };

  return (
    <div className="flex h-screen bg-white">
      {/* Sidebar */}
      <aside className={`
        ${mobileSidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        fixed inset-y-0 left-0 z-50 w-[280px] flex flex-col bg-gray-50 border-r border-gray-200
        transform transition-transform duration-300 ease-in-out
        lg:translate-x-0 lg:static lg:inset-0
      `}>
        {/* Header */}
        <div className="flex items-center justify-between h-14 px-4 border-b border-gray-200 flex-shrink-0">
          <div className="flex items-center gap-2.5">
            <Book className="h-5 w-5 text-primary" />
            <span className="font-semibold text-gray-800 text-[15px]">Documentation</span>
          </div>
          <button
            className="lg:hidden p-1 rounded hover:bg-gray-200"
            onClick={() => setMobileSidebarOpen(false)}
          >
            <X className="h-5 w-5 text-gray-500" />
          </button>
        </div>

        {/* Back button */}
        <div className="px-3 py-2 border-b border-gray-200">
          <button
            onClick={() => navigate('/dashboard')}
            className="flex items-center gap-2 text-[13px] text-gray-500 hover:text-gray-700 transition-colors px-2 py-1.5 rounded hover:bg-gray-100 w-full"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to Dashboard
          </button>
        </div>

        {/* Search */}
        <div className="px-3 py-2 border-b border-gray-200">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-400" />
            <input
              type="text"
              placeholder="Search docs..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-2 text-[13px] bg-white border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
            />
          </div>
          {/* Search results dropdown */}
          {searchQuery.trim() && searchResults.length > 0 && (
            <div className="absolute z-50 mt-1 left-3 right-3 bg-white border border-gray-200 rounded-lg shadow-lg max-h-64 overflow-y-auto">
              {searchResults.map((result, idx) => (
                <button
                  key={idx}
                  onClick={() => {
                    navigateTo(result.category, result.section);
                    setSearchQuery('');
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-gray-50 border-b border-gray-100 last:border-0"
                >
                  <p className="text-[13px] font-medium text-gray-800">{result.title}</p>
                  <p className="text-[11px] text-gray-400">{result.categoryTitle}</p>
                </button>
              ))}
            </div>
          )}
          {searchQuery.trim() && searchResults.length === 0 && (
            <div className="absolute z-50 mt-1 left-3 right-3 bg-white border border-gray-200 rounded-lg shadow-lg p-3">
              <p className="text-[13px] text-gray-500 text-center">No results found</p>
            </div>
          )}
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-2 px-2">
          {Object.entries(docs).map(([catKey, cat]) => (
            <div key={catKey} className="mb-0.5">
              <button
                onClick={() => toggleSection(catKey)}
                className={`
                  w-full flex items-center gap-2 px-3 py-2 rounded-lg text-[13px] font-medium transition-colors
                  ${currentCategory === catKey ? 'text-primary bg-primary/5' : 'text-gray-700 hover:bg-gray-100'}
                `}
              >
                <span className="flex-shrink-0 opacity-70">{cat.icon}</span>
                <span className="flex-1 text-left">{cat.title}</span>
                {expandedSections[catKey]
                  ? <ChevronDown className="h-3.5 w-3.5 opacity-50" />
                  : <ChevronRight className="h-3.5 w-3.5 opacity-50" />
                }
              </button>
              {expandedSections[catKey] && (
                <div className="ml-5 pl-3 border-l border-gray-200 mt-0.5 mb-1">
                  {Object.entries(cat.sections).map(([secKey, sec]) => (
                    <button
                      key={secKey}
                      onClick={() => navigateTo(catKey, secKey)}
                      className={`
                        w-full text-left px-3 py-1.5 rounded text-[12.5px] transition-colors block
                        ${currentCategory === catKey && currentSection === secKey
                          ? 'text-primary font-medium bg-primary/5'
                          : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                        }
                      `}
                    >
                      {sec.title}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </nav>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-gray-200 flex-shrink-0">
          <div className="flex items-center gap-2">
            <img src={hospitalLogo} alt="KT Health Soft" className="h-6 w-auto rounded" />
            <span className="text-[11px] text-gray-400">KT Health Soft Documentation</span>
          </div>
        </div>
      </aside>

      {/* Mobile overlay */}
      {mobileSidebarOpen && (
        <div
          className="fixed inset-0 bg-black/30 z-40 lg:hidden"
          onClick={() => setMobileSidebarOpen(false)}
        />
      )}

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <div className="flex items-center gap-3 h-14 px-4 lg:px-6 border-b border-gray-200 bg-white flex-shrink-0">
          <button
            className="lg:hidden p-2 -ml-2 rounded-lg hover:bg-gray-100"
            onClick={() => setMobileSidebarOpen(true)}
          >
            <Menu className="h-5 w-5 text-gray-600" />
          </button>
          {/* Breadcrumb */}
          <div className="flex items-center gap-1.5 text-[13px]">
            <button
              onClick={() => navigateTo('getting-started', 'overview')}
              className="text-gray-400 hover:text-gray-600 transition-colors"
            >
              Docs
            </button>
            <ChevronRight className="h-3 w-3 text-gray-300" />
            <span className="text-gray-400">{currentDoc?.title}</span>
            <ChevronRight className="h-3 w-3 text-gray-300" />
            <span className="text-gray-700 font-medium">{currentDoc?.sections?.[currentSection]?.title}</span>
          </div>
        </div>

        {/* Content area */}
        <main className="flex-1 overflow-y-auto">
          <div className="max-w-3xl mx-auto px-6 lg:px-10 py-8">
            {renderMarkdown(currentContent)}

            {/* Navigation footer */}
            <div className="flex items-center justify-between mt-12 pt-6 border-t border-gray-200">
              {(() => {
                const allPages = Object.entries(docs).flatMap(([catKey, cat]) =>
                  Object.keys(cat.sections).map(secKey => ({ category: catKey, section: secKey }))
                );
                const currentIdx = allPages.findIndex(p => p.category === currentCategory && p.section === currentSection);
                const prevPage = currentIdx > 0 ? allPages[currentIdx - 1] : null;
                const nextPage = currentIdx < allPages.length - 1 ? allPages[currentIdx + 1] : null;

                return (
                  <>
                    {prevPage ? (
                      <button
                        onClick={() => navigateTo(prevPage.category, prevPage.section)}
                        className="flex items-center gap-2 text-[13px] text-gray-500 hover:text-primary transition-colors px-3 py-2 rounded-lg hover:bg-gray-50"
                      >
                        <ArrowLeft className="h-3.5 w-3.5" />
                        <div className="text-left">
                          <p className="text-[11px] text-gray-400">Previous</p>
                          <p className="font-medium">{docs[prevPage.category].sections[prevPage.section].title}</p>
                        </div>
                      </button>
                    ) : <div />}
                    {nextPage ? (
                      <button
                        onClick={() => navigateTo(nextPage.category, nextPage.section)}
                        className="flex items-center gap-2 text-[13px] text-gray-500 hover:text-primary transition-colors px-3 py-2 rounded-lg hover:bg-gray-50"
                      >
                        <div className="text-right">
                          <p className="text-[11px] text-gray-400">Next</p>
                          <p className="font-medium">{docs[nextPage.category].sections[nextPage.section].title}</p>
                        </div>
                        <ChevronRight className="h-3.5 w-3.5" />
                      </button>
                    ) : <div />}
                  </>
                );
              })()}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
};

export default HelpDocs;
