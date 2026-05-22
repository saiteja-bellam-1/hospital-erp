# Inpatient Module — Gap Test Coverage

Existing `backend/tests/test_inpatient_smoke.py` has 188 passing tests but several
recently-added inpatient flows had **zero coverage**. This adds them in a new file
`backend/tests/test_inpatient_gaps.py`.

## Coverage gaps identified (uncovered routes/flows)

- [x] IP-doctor acceptance handshake — `POST /admissions/{id}/accept` + `/reject`,
      `_require_accepted` clinical lock
- [x] Gate pass (B6) — `POST/GET /admissions/{id}/gate-pass`, `/pdf`, the
      `outstanding_bill` 409 gate + override path
- [x] Bill reconciliation / Settle flow — `finalize` enriched response
      (`requires_action`/`amount_to_collect`/`amount_to_refund`), deposit auto-
      reconcile to `paid`
- [x] Credit-refund discharge gate — 409 `credit_refund_required` when overpaid
- [x] Payer schemes CRUD + mid-stay payer conversion + payer history
- [x] Doctor duty roster CRUD + `duty-doctor/on-duty`
- [x] Nursing notes CRUD

## Tasks

- [x] Research inpatient implementation flow & existing coverage
- [x] Write `test_inpatient_gaps.py`
- [x] Run new tests + full inpatient suite, confirm green
