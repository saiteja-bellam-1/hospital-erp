# Lab Module - Execution Plan

## Overview
Full lab module: Admin configures tests with parameters -> Doctor orders tests for patients -> Lab technician enters results -> Doctor views results with abnormal highlighting -> PDF download

## Phase 1: Backend - Data Model (New LabTestParameter table + migration)

### 1.1 Add LabTestParameter model to app/models/lab.py
- [x] New table `lab_test_parameters`
- [x] Add `parameters` relationship on LabTest model
- [x] Migration script to create the table

### 1.2 Update LabReport model
- [x] result_values JSON stores: `[{parameter_id, value}]`
- [x] No schema change needed (already JSON)

## Phase 2: Backend - Lab API Routes (app/routes/lab.py)

### 2.1 Category endpoints (admin)
- [x] GET/POST/PUT/DELETE /api/lab/categories

### 2.2 Lab test + parameter endpoints (admin)
- [x] GET/POST/PUT/DELETE /api/lab/tests (with parameters inline)
- [x] POST/PUT/DELETE /api/lab/tests/{id}/parameters
- [x] PUT /api/lab/tests/{id}/parameters/bulk

### 2.3 Lab order endpoints (doctor + lab)
- [x] POST /api/lab/orders, GET /api/lab/orders
- [x] GET /api/lab/orders/{id}, PUT /api/lab/orders/{id}/status
- [x] GET /api/lab/orders/patient/{patient_id}

### 2.4 Lab result entry endpoints (lab tech)
- [x] GET /api/lab/orders/{id}/entry-form
- [x] POST /api/lab/orders/{id}/results
- [x] PUT /api/lab/reports/{id}

### 2.5 Lab report viewing (doctor)
- [x] GET /api/lab/reports/patient/{patient_id}
- [x] GET /api/lab/reports/{id}
- [x] GET /api/lab/reports/{id}/download (PDF)

### 2.6 Seed data + stats
- [x] POST /api/lab/seed-defaults
- [x] GET /api/lab/stats

### 2.7 Register routes
- [x] Lab router wired in main.py

## Phase 3: Backend - Seed Data (Default Lab Tests)
- [x] CBC, LFT, RFT, Lipid Profile, Thyroid, Blood Sugar (4 tests), Urine Routine
- [x] Each with gender-specific reference ranges where applicable

## Phase 4: Frontend - Admin Lab Configuration (LabModule.js rewrite)
- [x] Tab-based: Dashboard | Test Catalog | Categories
- [x] Dashboard tab: stat cards + quick actions + seed defaults button
- [x] Categories management: list, create, edit, delete
- [x] Test catalog: list with search/filter, create/edit test dialog
- [x] Parameter editor: expandable per test, add/edit/remove parameters
- [x] Parameter form: name, unit, field_type, reference ranges (male/female/default)

## Phase 5: Frontend - Lab Technician Dashboard (LabTechDashboard.js)
- [x] Stats cards (pending, collected, processing, completed today)
- [x] Pending orders list with status filter + search
- [x] Status update buttons: Mark Collected, Start Processing
- [x] Enter Results button -> result entry form
- [x] Result entry: auto-generated from parameters, abnormal auto-detection
- [x] Completed orders tab with report viewing
- [x] Registered in Dashboard.js with lab_technician role routing

## Phase 6: Frontend - Doctor Lab Results View
- [x] Lab Orders tab shows real orders with status
- [x] View Report button for completed orders -> report dialog
- [x] Abnormal values: red text + badge
- [x] Real lab ordering from appointment card (test selection from API)
- [x] Category filter + search in lab order dialog
- [x] Download PDF button

## Phase 7: PDF Lab Report
- [x] generate_lab_report_pdf() in pdf_service.py
- [x] Hospital header, patient info, test name, date
- [x] Parameters table: Name | Result | Unit | Reference Range | Status
- [x] Abnormal values highlighted in red
- [x] Interpretation section
- [x] Wired to GET /api/lab/reports/{id}/download
- [x] Download buttons in doctor and lab tech dashboards
