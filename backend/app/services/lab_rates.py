"""Lab selling rates (Rate A / Rate B) and third-party order pricing.

`LabTest.cost` stays in sync with Rate A so existing readers keep working.
The price charged on an order is snapshotted onto `PatientLabOrder.amount`.
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.lab import LabPartner, LabRateCard, LabTest, LabTestRate

RATE_A = "A"
RATE_B = "B"


def ensure_rate_cards(db: Session, hospital_id: int):
    """Return (rate A, rate B), creating the two cards when a hospital has none."""
    cards = db.query(LabRateCard).filter(LabRateCard.hospital_id == hospital_id).all()
    by_code = {c.code: c for c in cards}
    if RATE_A not in by_code:
        card_a = LabRateCard(
            hospital_id=hospital_id,
            code=RATE_A,
            name="Rate A",
            is_default=True,
            is_active=True,
        )
        db.add(card_a)
        db.flush()
        by_code[RATE_A] = card_a
    if RATE_B not in by_code:
        card_b = LabRateCard(
            hospital_id=hospital_id,
            code=RATE_B,
            name="Rate B",
            is_default=False,
            is_active=True,
        )
        db.add(card_b)
        db.flush()
        by_code[RATE_B] = card_b
    return by_code[RATE_A], by_code[RATE_B]


def persist_new_rate_cards(db: Session) -> None:
    """Commit rate cards created during a read, without waiting for another write."""
    if any(isinstance(obj, LabRateCard) for obj in db.new):
        db.commit()


def _upsert_rate(db: Session, test_id: int, rate_card_id: int, amount: float) -> None:
    row = db.query(LabTestRate).filter(
        LabTestRate.test_id == test_id,
        LabTestRate.rate_card_id == rate_card_id,
    ).first()
    if row:
        row.amount = float(amount)
    else:
        db.add(LabTestRate(test_id=test_id, rate_card_id=rate_card_id, amount=float(amount)))


def save_test_rates(db: Session, test: LabTest, rate_a: float, rate_b: Optional[float], *, update_b: bool) -> None:
    """Write Rate A onto the test and the rate table. Rate B is written when update_b is set."""
    card_a, card_b = ensure_rate_cards(db, test.hospital_id)
    test.cost = float(rate_a)
    _upsert_rate(db, test.id, card_a.id, rate_a)
    if update_b:
        amount_b = float(rate_a if rate_b is None else rate_b)
        _upsert_rate(db, test.id, card_b.id, amount_b)


def rates_for_test(db: Session, test: LabTest, cards=None) -> list:
    card_a, card_b = cards or ensure_rate_cards(db, test.hospital_id)
    rows = {
        r.rate_card_id: float(r.amount or 0)
        for r in db.query(LabTestRate).filter(LabTestRate.test_id == test.id).all()
    }
    fallback = float(test.cost or 0)
    payload = []
    for card in (card_a, card_b):
        payload.append({
            "rate_card_id": card.id,
            "code": card.code,
            "name": card.name,
            "amount": rows.get(card.id, fallback),
            "is_default": bool(card.is_default),
        })
    return payload


def _card_for_booking(db: Session, hospital_id: int, rate_card_id: Optional[int]) -> LabRateCard:
    card_a, _card_b = ensure_rate_cards(db, hospital_id)
    if not rate_card_id:
        return card_a if card_a.is_default else card_a
    card = db.query(LabRateCard).filter(
        LabRateCard.id == rate_card_id,
        LabRateCard.hospital_id == hospital_id,
        LabRateCard.is_active == True,
    ).first()
    if not card:
        raise HTTPException(status_code=400, detail="Unknown rate card")
    return card


def _amount_for_card(db: Session, test: LabTest, card: LabRateCard) -> float:
    row = db.query(LabTestRate).filter(
        LabTestRate.test_id == test.id,
        LabTestRate.rate_card_id == card.id,
    ).first()
    if row is not None:
        return float(row.amount or 0)
    return float(test.cost or 0)


def _active_partner(db: Session, hospital_id: int, partner_id: int) -> LabPartner:
    partner = db.query(LabPartner).filter(
        LabPartner.id == partner_id,
        LabPartner.hospital_id == hospital_id,
        LabPartner.is_active == True,
    ).first()
    if not partner:
        raise HTTPException(status_code=400, detail="Partner lab not found")
    return partner


def resolve_order_pricing(
    db: Session,
    hospital_id: int,
    test: LabTest,
    *,
    rate_card_id: Optional[int] = None,
    fulfillment: Optional[str] = None,
    partner_id: Optional[int] = None,
    partner_cost: Optional[float] = None,
    partner_reference: Optional[str] = None,
) -> dict:
    """Price and fulfillment snapshot for a patient-billed order (in-house or send-out)."""
    card = _card_for_booking(db, hospital_id, rate_card_id)
    amount = _amount_for_card(db, test, card)
    ful = (fulfillment or getattr(test, "default_fulfillment", None) or "in_house").strip()
    if ful not in ("in_house", "send_out"):
        raise HTTPException(status_code=400, detail="Fulfillment must be in-house or send-out")

    base = {
        "amount": amount,
        "rate_card_id": card.id,
        "fulfillment": "in_house",
        "partner_id": None,
        "partner_cost": None,
        "partner_status": None,
        "partner_reference": None,
        "bill_to": "patient",
        "partner_settlement_status": None,
    }
    if ful == "in_house":
        return base

    pid = partner_id if partner_id is not None else getattr(test, "default_partner_id", None)
    if not pid:
        raise HTTPException(
            status_code=400,
            detail=f"{test.name} is sent to another lab. Choose a partner lab, or set a default partner on the test.",
        )
    partner = _active_partner(db, hospital_id, pid)
    if partner.partner_role == "receive_in":
        raise HTTPException(
            status_code=400,
            detail=f"{partner.name} is not set up to process samples from this lab",
        )
    cost = partner_cost if partner_cost is not None else getattr(test, "default_partner_cost", None)
    base.update({
        "fulfillment": "send_out",
        "partner_id": partner.id,
        "partner_cost": float(cost or 0),
        "partner_status": "to_send",
        "partner_reference": (partner_reference or None),
        "partner_settlement_status": "unsettled",
    })
    return base


def resolve_receive_in_pricing(
    db: Session,
    hospital_id: int,
    test: LabTest,
    partner: LabPartner,
    *,
    rate_card_id: Optional[int] = None,
    partner_reference: Optional[str] = None,
) -> dict:
    """Price a sample that arrived from a partner lab. The partner is the bill-to party."""
    if partner.partner_role == "send_out":
        raise HTTPException(
            status_code=400,
            detail=f"{partner.name} is not set up to send samples to this lab",
        )
    chosen = rate_card_id or partner.default_rate_card_id
    card = _card_for_booking(db, hospital_id, chosen)
    return {
        "amount": _amount_for_card(db, test, card),
        "rate_card_id": card.id,
        "fulfillment": "receive_in",
        "partner_id": partner.id,
        "partner_cost": None,
        "partner_status": "received",
        "partner_reference": partner_reference or None,
        "bill_to": "partner",
        "partner_settlement_status": "unsettled",
    }


def apply_test_commercial(db: Session, test: LabTest, data, *, creating: bool) -> None:
    """Persist rate and default send-out fields from a test create/update payload."""
    if creating or getattr(data, "cost", None) is not None or getattr(data, "rate_b", None) is not None:
        rate_a = float(data.cost if getattr(data, "cost", None) is not None else (test.cost or 0))
        update_b = creating or getattr(data, "rate_b", None) is not None
        rate_b = getattr(data, "rate_b", None)
        if test.id is None:
            db.flush()
        save_test_rates(db, test, rate_a, rate_b, update_b=update_b)

    fulfillment = getattr(data, "default_fulfillment", None)
    if creating or fulfillment is not None:
        ful = (fulfillment or "in_house").strip()
        if ful not in ("in_house", "send_out"):
            raise HTTPException(status_code=400, detail="Default processing must be in-house or send-out")
        test.default_fulfillment = ful
        if ful == "in_house":
            test.default_partner_id = None
            test.default_partner_cost = None
        else:
            partner_id = getattr(data, "default_partner_id", None)
            if not partner_id:
                raise HTTPException(
                    status_code=400,
                    detail="Choose the partner lab that processes this test",
                )
            _active_partner(db, test.hospital_id, partner_id)
            test.default_partner_id = partner_id
            cost = getattr(data, "default_partner_cost", None)
            test.default_partner_cost = float(cost or 0)
    elif getattr(data, "default_partner_id", None) is not None or getattr(data, "default_partner_cost", None) is not None:
        if (test.default_fulfillment or "in_house") == "send_out":
            if getattr(data, "default_partner_id", None) is not None:
                _active_partner(db, test.hospital_id, data.default_partner_id)
                test.default_partner_id = data.default_partner_id
            if getattr(data, "default_partner_cost", None) is not None:
                test.default_partner_cost = float(data.default_partner_cost or 0)
