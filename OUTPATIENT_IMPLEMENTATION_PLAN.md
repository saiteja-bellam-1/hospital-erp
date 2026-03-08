# Hospital ERP - Outpatient Module Implementation Plan

## Phase 1: Integration with Lab and Billing Modules (Priority 1)

### Backend Integration Tasks

#### 1.1 Lab Integration Backend
- [ ] **Create consultation lab order endpoints** - `/api/consultations/{id}/lab-orders`
  - POST: Create lab order from consultation
  - GET: List lab orders for consultation
  - PUT: Update lab order status
- [ ] **Integrate with existing lab module** 
  - Link consultation_id to lab orders
  - Auto-populate patient details in lab orders
- [ ] **Lab test recommendations system**
  - Create common test templates by specialty
  - Symptom-based test suggestions
- [ ] **Lab results integration back to consultation**
  - Update consultation when lab results available
  - Notification system for doctors

#### 1.2 Billing Integration Backend  
- [ ] **Auto-billing from consultation endpoints** - `/api/consultations/{id}/billing`
  - POST: Generate bill from consultation (consultation fee + lab orders + prescriptions)
  - GET: View consultation billing details
  - PUT: Update billing status
- [ ] **Consultation fee calculation**
  - Different fees for consultation types (follow-up, new patient, emergency)
  - Specialty-based fee structure
- [ ] **Prescription billing integration**
  - Auto-add prescription items to bill
  - Medicine stock checking before billing
- [ ] **Payment processing enhancement**
  - Support multiple payment methods
  - Partial payment tracking
  - Payment receipts generation

### Frontend Integration Tasks

#### 1.3 Doctor Dashboard Lab Integration
- [ ] **Lab order interface in consultation**
  - Quick test ordering buttons
  - Common test templates by specialty
  - Lab order history for patient
- [ ] **Lab results display**
  - Inline lab results in consultation view
  - Trend analysis for repeat patients
  - Critical value alerts

#### 1.4 Doctor Dashboard Billing Integration  
- [ ] **Billing preview in consultation**
  - Real-time billing calculation display
  - Fee adjustment interface
  - Discount application
- [ ] **Payment status tracking**
  - Payment status indicators
  - Pending payment alerts

---

## Phase 2: Walk-in Patient Workflow (Priority 2)

### Backend Walk-in System

#### 2.1 Walk-in Registration APIs
- [ ] **Quick registration endpoint** - `/api/outpatient/walk-in/register`
  - Minimal patient info for walk-ins
  - Auto-generate patient ID
  - Queue number assignment
- [ ] **Triage system endpoints** - `/api/outpatient/triage`
  - POST: Assign triage level (low, medium, high, critical)  
  - PUT: Update triage based on vitals
  - GET: Triage queue by priority
- [ ] **Queue management endpoints** - `/api/outpatient/queue`
  - GET: Current queue status
  - POST: Add patient to queue
  - PUT: Update queue position/status
  - DELETE: Remove from queue
- [ ] **Vital signs capture endpoints** - `/api/outpatient/vitals`
  - POST: Record basic vitals (BP, temp, weight, height)
  - GET: Patient vitals history

### Frontend Walk-in System

#### 2.2 Reception Walk-in Interface
- [ ] **Quick registration form**
  - Minimal fields: Name, Age, Phone, Chief complaint
  - Photo capture option
  - Emergency contact quick entry
- [ ] **Triage interface** 
  - Symptom checklist
  - Priority level assignment
  - Vitals recording form
- [ ] **Queue management dashboard**
  - Live queue display with numbers
  - Patient status updates (waiting, in-consultation, completed)
  - Estimated wait time display
- [ ] **Walk-in to appointment conversion**
  - Convert walk-in to scheduled follow-up
  - Doctor availability checking

---

## Phase 3: Enhanced Doctor Consultation Workflow (Priority 3)

### Backend Consultation Enhancement

#### 3.1 Consultation Management APIs
- [ ] **Consultation CRUD endpoints** - `/api/consultations`
  - POST: Start new consultation from appointment/walk-in
  - GET: Consultation details with history
  - PUT: Update consultation notes, diagnosis
  - POST: Complete consultation with summary
- [ ] **Medical notes and diagnosis**
  - Structured diagnosis entry (ICD-10 codes)
  - Template-based consultation notes
  - Voice-to-text integration options
- [ ] **Treatment plan endpoints**
  - Treatment recommendations
  - Follow-up scheduling from consultation
  - Referral management to other specialties
- [ ] **Patient medical history integration**
  - Previous consultation summaries
  - Chronic conditions tracking
  - Allergy and drug interaction alerts

### Frontend Doctor Consultation Interface

#### 3.2 Enhanced Doctor Dashboard
- [ ] **Comprehensive consultation interface**
  - Patient history sidebar
  - Current vitals display
  - Previous lab results summary
- [ ] **Smart consultation forms**
  - Specialty-specific templates
  - Auto-complete for common diagnoses
  - Drug interaction warnings
- [ ] **Integrated prescription writing**
  - Medicine search with stock levels
  - Dosage calculators
  - Alternative medicine suggestions
- [ ] **One-click lab ordering**
  - Specialty-specific test panels
  - Previous test comparison
  - Urgent/routine marking

---

## Phase 4: Admin Reporting and Analytics (Priority 4)

### Backend Reporting APIs

#### 4.1 Outpatient Analytics Endpoints
- [ ] **Daily reports API** - `/api/outpatient/reports/daily`
  - Patient footfall (appointments vs walk-ins)
  - Doctor consultation statistics
  - Average waiting times
  - Revenue by service type
- [ ] **Doctor performance reports** - `/api/outpatient/reports/doctors`
  - Patients seen per day/week/month
  - Average consultation time
  - Patient satisfaction scores (if implemented)
  - Revenue generated per doctor
- [ ] **Queue analytics** - `/api/outpatient/reports/queue`
  - Average wait times by time of day
  - Peak hour analysis
  - Triage level distribution
  - Patient flow optimization insights
- [ ] **Financial reports** - `/api/outpatient/reports/financial`
  - Revenue by service (consultation, lab, pharmacy)
  - Payment method distribution
  - Outstanding payments tracking
  - Discount usage analytics

### Frontend Admin Dashboard

#### 4.2 Comprehensive Admin Interface
- [ ] **Live dashboard with key metrics**
  - Today's patient count, revenue, wait times
  - Doctor availability status
  - Critical alerts and notifications
- [ ] **Interactive reports and charts**
  - Trend analysis with charts
  - Filterable date ranges
  - Export options (PDF, Excel)
- [ ] **Performance monitoring**
  - Real-time queue status
  - Doctor efficiency metrics
  - System usage statistics
- [ ] **Financial overview**
  - Daily revenue tracking
  - Payment collection status
  - Cost analysis by department

---

## Phase 5: Integrated Prescription and Bill Printout System (Priority 5)

### Backend Print Integration

#### 5.1 Print Management APIs
- [ ] **Consultation summary endpoint** - `/api/consultations/{id}/summary`
  - Complete consultation details
  - Prescription formatted for printing
  - Lab orders included
  - Follow-up instructions
- [ ] **Bill generation endpoint** - `/api/consultations/{id}/bill/generate`
  - Itemized bill with all services
  - Tax calculations
  - Discount applications
  - Payment method recording
- [ ] **Prescription formatting** - `/api/prescriptions/{id}/print`
  - Doctor letterhead integration
  - Medicine details with instructions
  - Patient information header
  - Barcode/QR code for verification

### Frontend Print Integration

#### 5.2 Print Interface Development
- [ ] **Consultation completion workflow**
  - One-click consultation summary
  - Prescription review before printing
  - Bill generation with approval
- [ ] **Print preview and customization**
  - Template selection for prescriptions
  - Bill format customization
  - Letterhead management
- [ ] **Batch printing options**
  - Print prescription + bill together
  - Queue multiple print jobs
  - Print history tracking
- [ ] **Digital alternatives**
  - Email prescription/bill option
  - SMS with prescription summary
  - QR code for digital retrieval

---

## Implementation Timeline

### Week 1-2: Lab Integration (Phase 1.1-1.2)
- Backend lab order APIs
- Basic billing integration
- Database schema updates

### Week 3-4: Frontend Lab/Billing Integration (Phase 1.3-1.4)
- Doctor dashboard lab interface
- Billing preview components
- Integration testing

### Week 5-6: Walk-in System Backend (Phase 2.1)
- Walk-in registration APIs
- Queue management system
- Triage implementation

### Week 7-8: Walk-in Frontend (Phase 2.2)
- Reception interface development
- Queue dashboard creation
- Walk-in workflow testing

### Week 9-10: Enhanced Consultation (Phase 3.1-3.2)
- Consultation API enhancement
- Doctor dashboard improvements
- Integration testing

### Week 11-12: Reporting System (Phase 4.1-4.2)
- Analytics backend development
- Admin dashboard creation
- Report generation testing

### Week 13-14: Print Integration (Phase 5.1-5.2)
- Print API development
- Frontend print interfaces
- End-to-end testing

---

## Success Metrics

### Operational Efficiency
- Reduce patient wait times by 30%
- Increase doctor consultation efficiency by 25%
- Automate 90% of billing processes

### Integration Success
- 100% lab orders integrated with consultations
- Automatic bill generation for all consultations
- Digital prescription delivery for 80% of patients

### User Adoption  
- 95% doctor adoption of integrated consultation workflow
- 100% reception staff using walk-in registration system
- Admin dashboard used daily for decision making

---

## Technical Architecture Decisions

### Database Enhancements Needed
- Add consultation_lab_orders junction table
- Add consultation_billing relationship
- Add walk_in_queue management table
- Add vitals_records table

### API Design Patterns
- RESTful APIs with consistent response formats
- Real-time endpoints using WebSocket where needed
- Batch operations for reporting APIs
- Proper error handling and validation

### Frontend Architecture
- Component reusability between modules
- Real-time updates using WebSocket/polling
- Print-friendly CSS for prescription/bill layouts
- Mobile-responsive design for tablet use

---

## Risk Mitigation

### Technical Risks
- **Integration Complexity**: Phase-wise implementation with thorough testing
- **Performance Issues**: Database indexing and query optimization
- **Real-time Requirements**: WebSocket implementation with fallback to polling

### User Adoption Risks
- **Training Requirements**: Comprehensive user training for each phase
- **Workflow Changes**: Gradual rollout with user feedback incorporation
- **System Reliability**: Robust error handling and backup systems

### Data Security
- **Patient Privacy**: HIPAA-compliant data handling
- **Access Controls**: Role-based permissions for all new features
- **Audit Trails**: Comprehensive logging for all patient interactions

---

*This plan will be updated as implementation progresses and requirements evolve.*