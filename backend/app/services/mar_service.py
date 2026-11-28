"""MAR (medication administration record) lifecycle helpers.

Scheduled MAR rows are system-generated placeholders. When the order behind
them stops (prescription cancelled, patient discharged / admission cancelled)
the not-yet-actioned future slots must disappear so nurses are never prompted
to give a medicine that is no longer ordered.
"""
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models.inpatient import MedicationAdministration


def purge_future_scheduled_doses(
    db: Session,
    *,
    admission_id: Optional[int] = None,
    prescription_item_ids: Optional[Iterable[int]] = None,
    from_time: Optional[datetime] = None,
) -> int:
    """Delete untouched ('scheduled', non-PRN) doses at/after ``from_time``.

    Never touches given/missed/refused/held rows -- those are legal record.
    Does not commit; the caller owns the transaction. Returns rows removed.
    """
    q = db.query(MedicationAdministration).filter(
        MedicationAdministration.status == "scheduled",
        MedicationAdministration.is_prn == False,  # noqa: E712
        MedicationAdministration.administered_at.is_(None),
    )
    if from_time is not None:
        q = q.filter(MedicationAdministration.scheduled_time >= from_time)
    if admission_id is not None:
        q = q.filter(MedicationAdministration.admission_id == admission_id)
    if prescription_item_ids is not None:
        ids = list(prescription_item_ids)
        if not ids:
            return 0
        q = q.filter(MedicationAdministration.prescription_item_id.in_(ids))
    elif admission_id is None:
        return 0  # refuse an unbounded purge
    return q.delete(synchronize_session=False)
