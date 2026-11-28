"""NEWS2 (National Early Warning Score 2, RCP 2017, SpO2 Scale 1).

Pure functions -- no DB / framework imports -- so they are trivially testable.
"""
from typing import Optional, Tuple, Dict

AVPU = ("alert", "confusion", "voice", "pain", "unresponsive")


def _band(value, bands):
    for lo, hi, pts in bands:
        if (lo is None or value >= lo) and (hi is None or value <= hi):
            return pts
    return 0


# (min, max, points) inclusive; None = open ended
_RR = [(None, 8, 3), (9, 11, 1), (12, 20, 0), (21, 24, 2), (25, None, 3)]
_SPO2 = [(None, 91, 3), (92, 93, 2), (94, 95, 1), (96, None, 0)]
_SBP = [(None, 90, 3), (91, 100, 2), (101, 110, 1), (111, 219, 0), (220, None, 3)]
_HR = [(None, 40, 3), (41, 50, 1), (51, 90, 0), (91, 110, 1), (111, 130, 2), (131, None, 3)]
_TEMP = [(None, 35.0, 3), (35.1, 36.0, 1), (36.1, 38.0, 0), (38.1, 39.0, 1), (39.1, None, 2)]


def compute_news2(v: Dict) -> Dict:
    """Return {score, risk, partial, red_flag, components}.

    ``v`` keys: respiratory_rate, spo2, bp_systolic, heart_rate, temperature_c,
    consciousness (AVPU string), on_supplemental_o2 (bool).
    Missing parameters score 0 and set ``partial=True``.
    """
    comps: Dict[str, int] = {}
    missing = 0

    def add(name, value, bands):
        nonlocal missing
        if value is None:
            missing += 1
            return
        comps[name] = _band(float(value), bands)

    add("respiratory_rate", v.get("respiratory_rate"), _RR)
    add("spo2", v.get("spo2"), _SPO2)
    add("bp_systolic", v.get("bp_systolic"), _SBP)
    add("heart_rate", v.get("heart_rate"), _HR)
    add("temperature_c", v.get("temperature_c"), _TEMP)

    cons = (v.get("consciousness") or "").strip().lower() or None
    if cons is None:
        missing += 1
    else:
        comps["consciousness"] = 0 if cons == "alert" else 3

    if v.get("on_supplemental_o2") is not None:
        comps["supplemental_o2"] = 2 if v.get("on_supplemental_o2") else 0

    score = sum(comps.values())
    red_flag = any(p == 3 for p in comps.values())
    if score >= 7:
        risk = "high"
    elif score >= 5:
        risk = "medium"
    elif red_flag:
        risk = "low_medium"   # single parameter scoring 3 => urgent ward-based review
    else:
        risk = "low"
    return {"score": score, "risk": risk, "partial": missing > 0,
            "red_flag": red_flag, "components": comps}


ESCALATION = {
    "low": "Routine monitoring (minimum 12-hourly)",
    "low_medium": "Urgent ward-based clinical review",
    "medium": "Urgent response: clinician review, increase monitoring to 1-hourly",
    "high": "Emergency response: critical-care team assessment, continuous monitoring",
}


def escalation_text(risk: str) -> Optional[str]:
    return ESCALATION.get(risk)
