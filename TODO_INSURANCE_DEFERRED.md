# Deferred — Insurance / TPA / Government Scheme work

Parked on 2026-04-30. Pick this up after the non-insurance roadmap is in shape.
Everything in this file is India-specific.

## 1. Pre-auth → BillSplit auto-population

On `finalize_bill`, if the admission has approved `InsurancePreAuth` records,
auto-create a `BillSplit` row of `payer_type='tpa'` for each approved amount;
remaining balance becomes a `self` split.

- File to touch: `backend/app/routes/inpatient.py` (`finalize_bill`).
- Eliminates the manual step where the biller forgets the TPA portion and
  bills the patient full. Currently fixed after the patient has left.
- Effort: ~1 hour.

## 2. TPA discharge bundle export

`GET /api/inpatient/admissions/{id}/tpa-bundle.pdf?tpa_id=<id>` that returns
one merged PDF with the standard Indian-TPA section order:

1. Cover sheet (claim/policy/admission/discharge, patient demographics)
2. Pre-auth approval letter (uploaded copy from preauth attachments)
3. Discharge summary
4. Final itemized bill (with cancelled-bill exclusion)
5. Investigation reports — relevant lab + radiology
6. OT notes (if surgery)
7. Indoor case papers (consultation notes, nursing notes)
8. Pharmacy bill
9. Implant invoices (if any) — manufacturer invoice required
10. Death summary (if applicable)

- Configurable per-TPA template — major Indian TPAs (MedAssist, Paramount,
  Vidal Health, Health India, FHPL, Star Health) each have preferred orders.
- Use PyPDF2/pypdf to merge existing PDF outputs rather than regenerating.
- Effort: ~2 days.

## 3. State government scheme support

Telangana Aarogyasri, Tamil Nadu CMCHIS, Karnataka Vajpayee Arogyashree, AP
YSR Aarogyasri, etc. Each state scheme has:

- Its own empanelment / patient eligibility portal
- A scheme-specific package code list (overlaps with PMJAY-HBP but not 1:1)
- A bill format and digital submission portal
- Per-package fixed rates (not negotiable like private TPA)

This is its own feature tier. Hospitals serving rural / tier-2 / tier-3 areas
need it; metropolitan private hospitals may not.

- Effort: ~5-7 days for one scheme; later schemes get cheaper after the first.

## 4. PMJAY (Ayushman Bharat) integration

National version of the state schemes. PMJAY-HBP has 1,949 procedure packages
with fixed rates. Required for empanelled hospitals (most non-metropolitan).

- Procedure catalog cross-reference: add `pmjay_code` column to `Procedure`.
- Empanelment status tracking on Hospital.
- TMS (Transaction Management System) integration for digital claim submission.
- Effort: ~3-4 days for catalog + cross-reference. Full TMS integration is
  bigger and depends on whether you want digital filing.

## 5. GST split on bill PDF

Healthcare services are GST-exempt, but pharmacy / implants / room upgrades
can be taxable. Today the bill PDF treats everything uniformly.

- `BillItem` already has `tax_percentage` per row.
- `pdf_service.generate_bill_pdf` should section the bill into "GST-exempt
  healthcare services" vs "Taxable items" with explicit subtotals per
  section, plus the hospital GSTIN in the footer.
- Hospital model needs a `gstin` field (probably already there — check).
- Effort: ~half day.

## 6. ABHA / Aadhaar verification flow

Patient model already has `abha_id`. Wire it to ABDM (Ayushman Bharat
Digital Mission) verification API for identity verification — patient
scans QR or types ABHA address, hospital fetches verified demographic
data. Reduces typos and fraudulent registrations.

- Requires ABDM Health Facility Registration (HFR) and Health Professional
  Registry (HPR) onboarding — paperwork-heavy.
- Effort: ~3-5 days once HFR onboarding is done.

## 7. Corporate patient PAN/GSTIN on bills

When a corporate is paying (employee reimbursement, cashless corporate
account), the bill must carry the corporate's PAN and GSTIN for their
input-tax-credit claim. Add `corporate_pan`, `corporate_gstin`,
`corporate_name` fields on Patient / Bill. Optional dropdown of frequent
corporates.

- Effort: ~half day.

## 8. e-Invoice / e-Way bill

Mandatory only if hospital aggregate turnover crosses ₹5 cr. Most
single-location hospitals don't need it; chain hospitals do. Government
e-Invoice portal integration.

- Effort: ~3-5 days.

## Suggested order when revisiting

1. (#1) Pre-auth → BillSplit auto-population — 1 hour, immediate revenue impact.
2. (#5) GST split on bill PDF — half day, low risk, compliance baseline.
3. (#7) Corporate PAN/GSTIN on bills — half day.
4. (#2) TPA discharge bundle — 2 days, biggest workflow win for billers.
5. (#4) PMJAY catalog cross-reference — 1-2 days.
6. (#3) State scheme (one at a time, customer-driven).
7. (#6) ABHA verification + (#8) e-Invoice — depends on regulatory pressure.
