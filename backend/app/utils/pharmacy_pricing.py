"""Shared pharmacy pricing and tablet/strip unit conversion helpers.

MRP and Rate A/B are stored per strip. Per-tab price = strip price / tablets_per_strip.
POS lines may specify qty in tabs and/or strips on the same row.

All money fields (rates, prices, line totals) are rounded to 2 decimal places.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from app.models.pharmacy import Medicine


def round_money(val: float | None) -> float:
    """Round a currency amount to 2 decimal places."""
    if val is None:
        return 0.0
    return round(float(val), 2)


MEDICINE_PRICE_ATTRS = (
    "unit_price", "mrp", "purchase_rate", "rate_a", "rate_b",
    "cost_pcs", "default_discount_pct", "item_discount_pct",
)


def apply_medicine_price_rounding(medicine: "Medicine") -> None:
    """Normalize stored medicine price fields to 2dp."""
    for attr in MEDICINE_PRICE_ATTRS:
        if hasattr(medicine, attr):
            setattr(medicine, attr, round_money(getattr(medicine, attr)))


def units_per_strip(medicine: "Medicine") -> int:
    """Tablets (or smallest sellable pieces) in one strip/sheet."""
    return max(1, int(getattr(medicine, "strip_conversion_factor", None) or 1))


def supports_strip_sale(medicine: "Medicine") -> bool:
    return units_per_strip(medicine) > 1


def strip_sale_rate(medicine: "Medicine", *, tier: str = "A") -> float:
    """Sale rate per strip — Rate A/B first, then MRP, then legacy unit_price."""
    raw = float(medicine.rate_b if tier == "B" else medicine.rate_a or 0)
    if raw <= 0:
        raw = float(medicine.mrp or 0)
    if raw <= 0:
        raw = float(medicine.unit_price or 0)
    return round_money(raw)


def tab_sale_rate(medicine: "Medicine", *, tier: str = "A", strip_rate: float | None = None) -> float:
    """Per-tab price derived from strip/MRP rate."""
    sr = strip_rate if strip_rate is not None and strip_rate > 0 else strip_sale_rate(medicine, tier=tier)
    if sr <= 0:
        return 0.0
    return round_money(sr / units_per_strip(medicine))


def combined_base_qty(qty_tabs: float, qty_strips: float, medicine: "Medicine") -> float:
    """Total tablets to deduct from stock."""
    return float(qty_tabs or 0) + float(qty_strips or 0) * units_per_strip(medicine)


def resolve_pos_sale_line(
    medicine: "Medicine",
    *,
    qty_tabs: float = 0.0,
    qty_strips: float = 0.0,
    tier: str = "A",
    override_strip_rate: float | None = None,
) -> Tuple[float, float, float, float, float]:
    """Return (base_qty, tab_rate, strip_rate, qty_tabs, qty_strips)."""
    tabs = float(qty_tabs or 0)
    strips = float(qty_strips or 0)
    base_qty = combined_base_qty(tabs, strips, medicine)
    strip_r = (
        round_money(float(override_strip_rate))
        if override_strip_rate is not None and override_strip_rate > 0
        else strip_sale_rate(medicine, tier=tier)
    )
    tab_r = tab_sale_rate(medicine, tier=tier, strip_rate=strip_r)
    return base_qty, tab_r, strip_r, tabs, strips


def line_subtotal_before_tax(
    *,
    qty_tabs: float,
    qty_strips: float,
    tab_rate: float,
    strip_rate: float,
    discount_pct: float = 0.0,
) -> float:
    base = float(qty_tabs or 0) * tab_rate + float(qty_strips or 0) * strip_rate
    return round_money(base * (1 - float(discount_pct or 0) / 100.0))


def format_sale_qty_display(
    *,
    quantity: float,
    sale_qty_tabs: float | None = None,
    sale_qty_strips: float | None = None,
    sale_qty: float | None = None,
    sale_qty_unit: str | None = None,
) -> str:
    """Human-readable qty for invoices."""
    parts: list[str] = []
    if sale_qty_tabs is not None and sale_qty_tabs > 0:
        parts.append(f"{sale_qty_tabs:g} tab{'s' if sale_qty_tabs != 1 else ''}")
    if sale_qty_strips is not None and sale_qty_strips > 0:
        parts.append(f"{sale_qty_strips:g} strip{'s' if sale_qty_strips != 1 else ''}")
    if parts:
        return " + ".join(parts)
    # Legacy single-unit rows
    if sale_qty is not None:
        label = "strip" if sale_qty_unit == "strip" else "tab"
        return f"{sale_qty:g} {label}{'s' if sale_qty != 1 else ''}"
    return f"{quantity:g} tab{'s' if quantity != 1 else ''}"


def cost_pcs_from_mrp(mrp: float, strip_conversion_factor: int) -> float:
    """Cost per tab = MRP per strip ÷ tablets per strip."""
    factor = max(1, int(strip_conversion_factor or 1))
    val = float(mrp or 0)
    if val <= 0:
        return 0.0
    return round_money(val / factor)


def apply_cost_pcs_from_mrp(medicine: "Medicine") -> None:
    medicine.cost_pcs = cost_pcs_from_mrp(
        round_money(float(medicine.mrp or 0)),
        int(medicine.strip_conversion_factor or 1),
    )


def is_free_text_medicine(medicine: "Medicine") -> bool:
    """True for auto-created hidden stubs from inpatient free-text entry."""
    code = (medicine.medicine_code or "").upper()
    return bool(medicine.is_hidden) and code.startswith("TXT-")


def medicine_sale_rate(medicine: "Medicine") -> float:
    """Primary sale rate per tablet (for Rx / inpatient billing)."""
    return tab_sale_rate(medicine, tier="A")
