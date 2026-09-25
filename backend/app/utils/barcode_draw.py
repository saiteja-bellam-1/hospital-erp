"""Shared linear barcode drawing for labels and document PDFs.

Internal hospital codes (prefixes 20–23) print as Code128 with the same digit
payload so scanners still wedge the stored EAN-13 string. Manufacturer retail
codes print as EAN-13. Symbols are uniformly scaled (never height-only) and
module widths are snapped toward 203 dpi dots.
"""
from __future__ import annotations

from typing import Literal, Optional, Tuple

from reportlab.graphics import renderPDF, renderSVG
from reportlab.graphics.barcode.eanbc import Ean13BarcodeWidget
from reportlab.graphics.barcode.widgets import BarcodeCode128
from reportlab.graphics.shapes import Drawing, Group
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.services.barcode_service import (
    PREFIX_LAB_SAMPLE,
    PREFIX_PATIENT,
    PREFIX_PHARMACY_BATCH,
    PREFIX_PHARMACY_ITEM,
    validate_ean13,
)

Symbology = Literal["code128", "ean13"]

INTERNAL_PREFIXES = (
    PREFIX_LAB_SAMPLE,
    PREFIX_PATIENT,
    PREFIX_PHARMACY_ITEM,
    PREFIX_PHARMACY_BATCH,
)

# 203 dpi thermal: one printer dot ≈ 0.125 mm.
DOT_PT = 0.125 * mm
MIN_MODULE_DOTS = 2
DEFAULT_BAR_WIDTH_PT = 0.33 * mm  # GS1 nominal X before fit/snap


def digits_only(value: str) -> str:
    return "".join(c for c in (value or "") if c.isdigit())


def is_internal_hospital_code(value: str) -> bool:
    digits = digits_only(value)
    return len(digits) == 13 and digits.startswith(INTERNAL_PREFIXES)


def resolve_label_symbology(
    value: str,
    *,
    force: Optional[Symbology] = None,
) -> Symbology:
    """Pick Code128 for internal IDs; EAN-13 only for manufacturer retail codes."""
    if force in ("code128", "ean13"):
        return force
    digits = digits_only(value)
    if is_internal_hospital_code(digits):
        return "code128"
    if validate_ean13(digits) and not digits.startswith(INTERNAL_PREFIXES):
        return "ean13"
    return "code128"


def barcode_payload(value: str, symbology: Symbology) -> Optional[str]:
    raw = (value or "").strip()
    if not raw:
        return None
    digits = digits_only(raw)
    if symbology == "ean13":
        if validate_ean13(digits):
            return digits[:13]
        return None
    # Code128: keep alphanumeric payloads (human MRN e.g. KTH-2026-00042).
    # Collapse to digits only when the value is already a pure digit barcode
    # (internal EAN-13 / sample / batch codes).
    if raw.isdigit():
        return raw
    if digits == raw and digits:
        return digits
    return raw


def _make_code128_drawing(
    payload: str,
    *,
    bar_width: float,
    bar_height: float,
    human_readable: bool,
) -> Drawing:
    """Code128 with GS1 quiet zones (10X), not ReportLab's oversized defaults."""
    widget = BarcodeCode128()
    widget.value = payload
    widget.barWidth = bar_width
    widget.barHeight = bar_height
    widget.humanReadable = 1 if human_readable else 0
    quiet = max(10.0 * bar_width, 1.5 * mm)
    widget.lquiet = quiet
    widget.rquiet = quiet
    bounds = widget.getBounds()
    dw = max(bounds[2] - bounds[0], 1.0)
    dh = max(bounds[3] - bounds[1], 1.0)
    drawing = Drawing(dw, dh)
    drawing.add(widget)
    return drawing


def _make_ean13_drawing(
    payload: str,
    *,
    bar_width: float,
    bar_height: float,
    human_readable: bool,
) -> Drawing:
    widget = Ean13BarcodeWidget(payload[:13])
    widget.barWidth = bar_width
    widget.barHeight = bar_height
    widget.humanReadable = 1 if human_readable else 0
    bounds = widget.getBounds()
    dw = max(bounds[2] - bounds[0], 1.0)
    dh = max(bounds[3] - bounds[1], 1.0)
    drawing = Drawing(dw, dh)
    drawing.add(widget)
    return drawing


def _raw_barcode_drawing(
    payload: str,
    sym: Symbology,
    *,
    bar_width: float,
    bar_height: float,
    human_readable: bool,
) -> Optional[Drawing]:
    try:
        if sym == "ean13":
            return _make_ean13_drawing(
                payload,
                bar_width=bar_width,
                bar_height=bar_height,
                human_readable=human_readable,
            )
        return _make_code128_drawing(
            payload,
            bar_width=bar_width,
            bar_height=bar_height,
            human_readable=human_readable,
        )
    except Exception:
        return None


def build_barcode_drawing(
    value: str,
    *,
    max_width: float,
    max_height: float,
    symbology: Optional[Symbology] = None,
    human_readable: bool = False,
    bar_width: float = DEFAULT_BAR_WIDTH_PT,
) -> Optional[Tuple[Drawing, Symbology, float]]:
    """
    Build a Drawing that fits inside max_width × max_height (points).

    Returns (drawing, symbology, effective_module_pt) or None.
    Quiet zones are part of the symbol bounds and are never cropped.
    Module (X) width is chosen as a whole number of 203 dpi dots when possible.
    """
    sym = symbology or resolve_label_symbology(value)
    payload = barcode_payload(value, sym)
    if not payload or max_width < 2 * mm or max_height < 1.5 * mm:
        return None

    bar_h = max(max_height * 0.92, 2 * mm)

    # Prefer the largest whole-dot module that still fits the box.
    chosen = None
    for dots in range(8, MIN_MODULE_DOTS - 1, -1):
        trial_w = dots * DOT_PT
        src = _raw_barcode_drawing(
            payload,
            sym,
            bar_width=trial_w,
            bar_height=bar_h,
            human_readable=human_readable,
        )
        if src is None:
            continue
        nat_w = float(getattr(src, "width", 0) or 0)
        nat_h = float(getattr(src, "height", 0) or 0)
        if nat_w <= 0 or nat_h <= 0:
            continue
        if nat_w <= max_width + 1e-6 and nat_h <= max_height + 1e-6:
            chosen = (src, trial_w, 1.0)
            break

    if chosen is None:
        src = _raw_barcode_drawing(
            payload,
            sym,
            bar_width=bar_width,
            bar_height=bar_h,
            human_readable=human_readable,
        )
        if src is None:
            return None
        nat_w = float(getattr(src, "width", 0) or 0)
        nat_h = float(getattr(src, "height", 0) or 0)
        if nat_w <= 0 or nat_h <= 0:
            return None
        scale, module_pt = _fit_scale(nat_w, nat_h, max_width, max_height, bar_width)
        if scale <= 0:
            return None
        chosen_src = src
        chosen_module = module_pt
        chosen_scale = scale
    else:
        chosen_src, chosen_module, chosen_scale = chosen[0], chosen[1], chosen[2]
        nat_w = float(chosen_src.width)
        nat_h = float(chosen_src.height)
        if nat_h > max_height + 1e-6 or nat_w > max_width + 1e-6:
            chosen_scale = min(max_width / nat_w, max_height / nat_h)
            chosen_module = chosen_module * chosen_scale

    out_w = float(chosen_src.width) * chosen_scale
    out_h = float(chosen_src.height) * chosen_scale
    if abs(chosen_scale - 1.0) < 1e-9:
        return chosen_src, sym, chosen_module
    group = Group(chosen_src)
    group.scale(chosen_scale, chosen_scale)
    out = Drawing(out_w, out_h)
    out.add(group)
    return out, sym, chosen_module


def _fit_scale(
    nat_w: float,
    nat_h: float,
    max_w: float,
    max_h: float,
    base_bar_width: float,
) -> Tuple[float, float]:
    """Best-effort uniform scale; snap module down to whole dots without upsizing."""
    if nat_w <= 0 or nat_h <= 0 or max_w <= 0 or max_h <= 0:
        return 0.0, 0.0
    scale = min(max_w / nat_w, max_h / nat_h)
    if scale <= 0:
        return 0.0, 0.0
    effective = base_bar_width * scale
    min_module = MIN_MODULE_DOTS * DOT_PT
    if effective + 1e-9 < min_module:
        return scale, effective
    dots = max(MIN_MODULE_DOTS, int(effective / DOT_PT))
    snapped = dots * DOT_PT
    scale_snapped = snapped / base_bar_width
    final = min(scale, scale_snapped)
    return final, base_bar_width * final


def barcode_module_ok(module_pt: float) -> bool:
    """True when the narrowest bar is at least ~2 dots at 203 dpi."""
    return module_pt + 1e-9 >= (MIN_MODULE_DOTS * DOT_PT)


def draw_linear_barcode(
    c: canvas.Canvas,
    value: str,
    x: float,
    y: float,
    max_width: float,
    max_height: float,
    *,
    symbology: Optional[Symbology] = None,
    human_readable: bool = False,
    align: Literal["left", "center", "right"] = "left",
    area_width: Optional[float] = None,
) -> Optional[Tuple[float, float, Symbology]]:
    """
    Draw a fitted linear barcode with bottom-left at (x, y).

    Returns (drawn_width, drawn_height, symbology) or None.
    """
    built = build_barcode_drawing(
        value,
        max_width=max_width,
        max_height=max_height,
        symbology=symbology,
        human_readable=human_readable,
    )
    if not built:
        return None
    drawing, sym, _module = built
    dw = float(drawing.width)
    dh = float(drawing.height)
    draw_x = x
    box_w = area_width if area_width is not None else max_width
    if align == "center":
        draw_x = x + max(0.0, (box_w - dw) / 2)
    elif align == "right":
        draw_x = x + max(0.0, (box_w - dw))
    renderPDF.draw(drawing, c, draw_x, y)
    return dw, dh, sym


def draw_barcode_with_digits_below(
    c: canvas.Canvas,
    value: str,
    center_x: float,
    zone_bottom: float,
    zone_width: float,
    zone_height: float,
    *,
    symbology: Optional[Symbology] = None,
) -> Optional[Symbology]:
    """Pharmacy-style: bars centered in zone, human-readable digits under bars.

    Digit glyph box and bars stay inside [zone_bottom, zone_bottom+zone_height].
    """
    if zone_height < 2.0 * mm or zone_width < 4.0 * mm:
        return None
    payload_preview = digits_only(value) or (value or "").strip()
    digit_pt = max(3.2, min(4.8, (zone_height / mm) * 1.15))
    ascent = digit_pt * 0.72 * (25.4 / 72.0)
    descent = digit_pt * 0.28 * (25.4 / 72.0)
    digit_gap = 0.35 * mm
    digit_band = ascent + descent + digit_gap
    if digit_band > zone_height * 0.45:
        digit_band = zone_height * 0.35
        digit_pt = max(3.0, min(digit_pt, (digit_band - digit_gap) / ((0.72 + 0.28) * (25.4 / 72.0))))
        ascent = digit_pt * 0.72 * (25.4 / 72.0)
        descent = digit_pt * 0.28 * (25.4 / 72.0)
    bars_h = max(1.0, zone_height - digit_band)
    max_bar_w = zone_width * 0.95
    built = build_barcode_drawing(
        value,
        max_width=max_bar_w,
        max_height=bars_h,
        symbology=symbology,
        human_readable=False,
    )
    if not built:
        return None
    drawing, sym, _module = built
    dw = float(drawing.width)
    dh = float(drawing.height)
    bar_x = center_x - dw / 2
    bars_bottom = zone_bottom + digit_band
    bar_y = bars_bottom + max(0.0, (bars_h - dh) / 2)
    # Never let bars climb past the zone top.
    if bar_y + dh > zone_bottom + zone_height:
        bar_y = max(bars_bottom, zone_bottom + zone_height - dh)
    renderPDF.draw(drawing, c, bar_x, bar_y)
    text = payload_preview[:32]
    if text:
        c.setFont("Helvetica", digit_pt)
        digit_baseline = zone_bottom + descent
        c.drawCentredString(center_x, digit_baseline, text)
    return sym


def barcode_svg_markup(
    value: str,
    *,
    max_width_mm: float,
    max_height_mm: float,
    symbology: Optional[Symbology] = None,
    human_readable: bool = False,
) -> Optional[str]:
    """SVG fragment for HTML thermal print (same fit rules as PDF)."""
    built = build_barcode_drawing(
        value,
        max_width=max_width_mm * mm,
        max_height=max_height_mm * mm,
        symbology=symbology,
        human_readable=human_readable,
    )
    if not built:
        return None
    drawing, _sym, _module = built
    try:
        return renderSVG.drawToString(drawing)
    except Exception:
        return None


def vertical_mrn_barcode_drawing(
    code: str,
    *,
    bar_length: float,
    bar_depth: float,
    min_length: float = 40.0,
) -> Optional[Drawing]:
    """Rotated Code128 strip for prescription / lab-report / bill demographics.

    Encodes the human-readable MRN string (e.g. KTH-2026-00042), not the
    internal patient EAN-13, so scanners wedge the same value staff type/search.
    """
    payload = (code or "").strip()
    if not payload:
        return None
    length = max(float(bar_length), float(min_length))
    depth = max(float(bar_depth), 14.0)
    # Build horizontal Code128 fitted to length × depth, then rotate -90°.
    built = build_barcode_drawing(
        payload,
        max_width=length,
        max_height=depth,
        symbology="code128",
        human_readable=False,
    )
    if not built:
        return None
    src, _sym, _module = built
    group = Group(src)
    group.rotate(-90)
    group.shift(0, src.width)
    out = Drawing(src.height, src.width)
    out.add(group)
    return out


def measure_fitted_size(
    value: str,
    max_width: float,
    max_height: float,
    *,
    symbology: Optional[Symbology] = None,
) -> Optional[Tuple[float, float, Symbology, float]]:
    """Test helper: (width, height, symbology, module_pt) after fit."""
    built = build_barcode_drawing(
        value,
        max_width=max_width,
        max_height=max_height,
        symbology=symbology,
        human_readable=False,
    )
    if not built:
        return None
    drawing, sym, module_pt = built
    return float(drawing.width), float(drawing.height), sym, module_pt
