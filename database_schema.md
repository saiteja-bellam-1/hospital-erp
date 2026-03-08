# Hospital ERP Database Schema Design

## User Roles Hierarchy
```
Super Admin
└── Hospital Admin
    ├── Lab Admin
    ├── Pharmacy Admin
    ├── Billing Admin
    ├── Outpatient Admin
    ├── Inpatient Admin
    └── Doctors
```

## Core Tables

### 1. Users and Authentication
- `users` - Base user table
- `user_roles` - Role definitions
- `user_permissions` - Module access permissions
- `hospitals` - Hospital information
- `hospital_modules` - Module access control per hospital

### 2. Patient Management
- `patients` - Patient information with auto-generated UUID
- `patient_contacts` - Contact information
- `patient_medical_history` - Medical history records

### 3. Module-Specific Tables

#### Lab Management
- `lab_tests` - Available lab tests
- `lab_test_categories` - Test categorization
- `lab_reports` - Generated reports
- `lab_report_templates` - Configurable templates
- `patient_lab_orders` - Lab test orders

#### Pharmacy Management
- `medicines` - Medicine inventory
- `medicine_categories` - Medicine categorization
- `prescriptions` - Doctor prescriptions
- `prescription_items` - Individual prescription items
- `pharmacy_inventory` - Stock management

#### Billing Management
- `bills` - Main billing records
- `bill_items` - Individual bill line items
- `payment_methods` - Payment options
- `payments` - Payment records

#### EHR (Electronic Health Records)
- `consultations` - Doctor consultations
- `diagnosis` - Diagnosis records
- `treatment_plans` - Treatment planning
- `medical_notes` - Doctor notes

#### Outpatient Management
- `appointments` - Appointment scheduling
- `outpatient_visits` - Visit records

#### Inpatient Management
- `admissions` - Patient admissions
- `room_management` - Room allocation
- `discharge_records` - Discharge information

## Relationships
- All patient-related data linked via patient UUID
- All billing items linked to respective modules
- Role-based access control through user_permissions table
- Module access controlled at hospital level through hospital_modules table