# Inpatient module — non-insurance roadmap

Started: 2026-04-30. Insurance/TPA/state-scheme work parked in
`TODO_INSURANCE_DEFERRED.md` — do not touch from this list.

Status legend: ⬜ pending · 🔄 in progress · ✅ done · ⏸ deferred

---

## A. Clinical safety & quality

- ✅ A1. MAR safety wraps (allergy x-check, narcotic 2nd witness, dup-dose window) (1.5 d)
- ✅ A2. Code-blue / RRT event log (1 d)
- ✅ A3. Nurse shift handover form + printable sheet (1 d)
- ✅ A4. Adverse-event linkage (MAR ↔ Incident) (½ d)
- ✅ A5. Doctor ward-round checklist (1 d)

## B. Operational workflows (non-billing)

- ✅ B1. DAMA form + signature flow + PDF (1 d)
- ✅ B2. LOA / pass-out (room rent skip, bed hold) (1 d)
- ⬜ B3. Birth registration (BirthRecord + baby Patient + Letter of Birth PDF) — ~1.5 d
- ⬜ B4. Attendant / relative pass log — ~1 d
- ✅ B5. Diet kitchen ticket print + per-meal log (1 d)
- ✅ B6. Death body release flow + post-mortem coordination (1 d)
- ✅ B7. Emergency / casualty workflow (MLC on admit, triage, quick-admit, arrival mode) (1.5 d)

## C. Tech / perf / correctness debt

- ⬜ C1. Split `InpatientModule.js` into per-tab lazy chunks — ~3 d
- ⬜ C2. Pagination + date filters on long lists — ~1.5 d
- ✅ C3. Datetime standardization to UTC (½ d)
- ⬜ C4. Soft-delete on clinical writes — ~1 d
- ⬜ C5. PDF rate limiting — ~½ d
- ⬜ C6. N+1 fixes in `_*_to_response` helpers — ~1 d
- ✅ C7. Replace `window.confirm` at line 553 with `ConfirmDialog` (5 min)

## D. New clinical features (non-insurance)

- ✅ D1. Room rate snapshotting (per-segment rates) (1.5 d)
- ⬜ D2. ICD-10 clinical coding (analytics + reporting use) — ~3.5 d
- ⬜ D3. Doctor visit edit/delete with bill-aware revert — ~½ d
- ⬜ D4. `OTSchedule.consent_id` FK + start-OT requires consent — ~½ d

## E. Admin / reports

- ✅ E1. Daily census report PDF (1 d)
- ✅ E2. Month-end mortality + readmission report (1 d)
- ✅ E3. Doctor productivity report (1.5 d)
- ⬜ E4. Bed occupancy heat map — ~1.5 d
- ✅ E5. Audit log search UI (1 d)

## F. Patient experience

- ⬜ F1. SMS / WhatsApp notifications (admission, daily, discharge, follow-up) — ~2 d
- ⬜ F2. Patient-facing portal (OTP login, view bill, download summary) — ~3 d
- ⬜ F3. Post-discharge feedback NPS — ~1 d

## G. Multi-hospital / multi-branch hardening

- ⬜ G1. `hospital_id` scoping audit on all list endpoints — ~1 d
- ⬜ G2. Inter-hospital referral tracking (structured) — ~1.5 d

---

## Execution order (initial batch)

⭐ marks the items in the recommended quick-impact batch:

1. C7 — Replace `window.confirm` (5 min)
2. C3 — Datetime standardization (½ d)
3. B1 — DAMA workflow (1 d)
4. B5 — Diet kitchen ticket + per-meal log (1 d)
5. B2 — LOA / pass-out (1 d)
6. D1 — Room rate snapshotting (1.5 d)
7. E1 — Daily census PDF (1 d)

Total batch: ~5.5 days. After each item: smoke tests must pass; checkmark
the row above; commit message references the item code (e.g. `B1: DAMA`).
