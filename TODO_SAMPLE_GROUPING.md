# Lab Sample Grouping Feature

## Overview
Group lab tests by patient + sample type so one sample collection covers multiple tests. Add admin-managed sample types and a bypass option for separate collection.

## Tasks

### Backend
- [x] 1. Add `SampleType` model (id, name, description, hospital_id, is_active, created_at)
- [x] 2. Add migration for `sample_type_id` FK on `LabTest` + remove unique constraint on `sample_id`
- [x] 3. Add `SampleType` CRUD endpoints (GET, POST, PUT, DELETE)
- [x] 4. Update `TestCreate`/`TestUpdate` Pydantic models to use `sample_type_id`
- [x] 5. Update test CRUD endpoints to handle `sample_type_id`
- [x] 6. Modify sample ID generation: on "collected", find other orders for same patient + same sample_type_id with status "ordered", assign same sample_id to all
- [x] 7. Add bypass parameter to status update endpoint (`force_new_sample=true`)
- [x] 8. Return grouped order info in status update response + sample_type_name in order responses

### Frontend - Lab Admin
- [x] 9. Add "Sample Types" tab in LabModule with CRUD UI
- [x] 10. Convert test form `sample_type` text input to dropdown (from sample types list)

### Frontend - Tech Dashboard
- [x] 11. Add visual grouping indicator (patient + sample type) in order list — amber-bordered cards
- [x] 12. Update "Mark Collected" to show grouped tests confirmation dialog
- [x] 13. Add bypass option ("Collect Separate Sample") in the collection dialog
- [x] 14. Update barcode dialog to show grouped tests count + names

### Testing
- [x] 15. Backend tests pass (78 pass, 1 skip)
- [x] 16. Frontend builds successfully
