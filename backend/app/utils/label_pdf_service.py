"""Thermal / Avery label PDF + HTML generation (non-A4 page sizes)."""
from __future__ import annotations

import html
import io
from dataclasses import dataclass
from typing import Any, List, Optional
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.utils.barcode_draw import (
    barcode_svg_markup,
    draw_barcode_with_digits_below,
    draw_linear_barcode,
    resolve_label_symbology,
)
from app.utils.pdf_settings import apply_thermal_roll_layout

# Pharmacy label layout ratios (retail-style: header / barcode / footer).
PHARMACY_SIDE_MARGIN_RATIO = 0.01
PHARMACY_HEADER_RATIO = 0.10
PHARMACY_BARCODE_HEIGHT_RATIO = 0.45  # max barcode block height vs label
PHARMACY_DETAIL_ZONE_RATIO = 0.28
PHARMACY_ZONE_GAP = 0.5 * mm
PHARMACY_HEADER_MIN_MM = 4.0
PHARMACY_FOOTER_MIN_MM = 7.2
# Vertical clearance between text glyph boxes and barcode bars (points→mm via helpers).
TEXT_BARCODE_GAP = 0.8 * mm
# Known Code128 payload for calibration stickers (also a valid EAN-13 check digit).
TEST_LABEL_BARCODE = "2300000000108"


def _text_ascent_mm(size_pt: float) -> float:
    """Approximate Helvetica ascent height in mm for a font size in points."""
    return _pt_to_mm(size_pt * 0.72)


def _text_descent_mm(size_pt: float) -> float:
    return _pt_to_mm(size_pt * 0.28)



def _pharmacy_band_heights(ih: float) -> tuple[float, float]:
    """Header/footer heights with minimum mm so small thermal labels still fit text."""
    header_h = max(PHARMACY_HEADER_MIN_MM * mm, ih * PHARMACY_HEADER_RATIO)
    footer_h = max(PHARMACY_FOOTER_MIN_MM * mm, ih * PHARMACY_DETAIL_ZONE_RATIO)
    max_bands = max(1.0, ih * 0.90 - 2 * PHARMACY_ZONE_GAP)
    if header_h + footer_h > max_bands:
        scale = max_bands / (header_h + footer_h)
        header_h *= scale
        footer_h *= scale
    return header_h, footer_h


# Query / dialog keys that may override saved hospital label settings.
LABEL_LAYOUT_OVERRIDE_KEYS = frozenset({
    "width_mm",
    "height_mm",
    "labels_per_row",
    "labels_per_column",
    "margin_top_mm",
    "margin_left_mm",
    "gutter_mm",
    "sheet_mode",
    "sheet_width_mm",
    "sheet_height_mm",
})


@dataclass(frozen=True)
class LabelLayoutConfig:
    width_mm: float = 50.0
    height_mm: float = 30.0
    labels_per_row: int = 1
    labels_per_column: int = 1
    margin_top_mm: float = 2.0
    margin_left_mm: float = 2.0
    gutter_mm: float = 2.0
    sheet_mode: str = "thermal"  # thermal | avery
    sheet_width_mm: float = 210.0
    sheet_height_mm: float = 297.0
    show_lab_name: bool = True
    lab_name_override: Optional[str] = None
    show_pharmacy_name: bool = True
    pharmacy_name_override: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "LabelLayoutConfig":
        if not data:
            return cls()
        normalized = apply_thermal_roll_layout(dict(data))
        return cls(
            width_mm=float(normalized.get("width_mm", 50)),
            height_mm=float(normalized.get("height_mm", 30)),
            labels_per_row=max(1, int(normalized.get("labels_per_row", 1))),
            labels_per_column=max(1, int(normalized.get("labels_per_column", 1))),
            margin_top_mm=float(normalized.get("margin_top_mm", 2)),
            margin_left_mm=float(normalized.get("margin_left_mm", 2)),
            gutter_mm=float(normalized.get("gutter_mm", 2)),
            sheet_mode=str(normalized.get("sheet_mode", "thermal")),
            sheet_width_mm=float(normalized.get("sheet_width_mm", 210)),
            sheet_height_mm=float(normalized.get("sheet_height_mm", 297)),
            show_lab_name=bool(normalized.get("show_lab_name", True)),
            lab_name_override=normalized.get("lab_name_override") or None,
            show_pharmacy_name=bool(normalized.get("show_pharmacy_name", True)),
            pharmacy_name_override=normalized.get("pharmacy_name_override") or None,
        )


def layout_overrides_from_params(
    *,
    width_mm: Optional[float] = None,
    height_mm: Optional[float] = None,
    labels_per_row: Optional[int] = None,
    labels_per_column: Optional[int] = None,
    margin_top_mm: Optional[float] = None,
    margin_left_mm: Optional[float] = None,
    gutter_mm: Optional[float] = None,
    sheet_mode: Optional[str] = None,
    sheet_width_mm: Optional[float] = None,
    sheet_height_mm: Optional[float] = None,
) -> dict[str, Any]:
    """Collect non-None layout query params for merge_label_layout."""
    raw = {
        "width_mm": width_mm,
        "height_mm": height_mm,
        "labels_per_row": labels_per_row,
        "labels_per_column": labels_per_column,
        "margin_top_mm": margin_top_mm,
        "margin_left_mm": margin_left_mm,
        "gutter_mm": gutter_mm,
        "sheet_mode": sheet_mode,
        "sheet_width_mm": sheet_width_mm,
        "sheet_height_mm": sheet_height_mm,
    }
    return {k: v for k, v in raw.items() if v is not None}


def merge_label_layout(
    base: Optional[dict[str, Any]],
    overrides: Optional[dict[str, Any]] = None,
    *,
    single_label: bool = False,
) -> LabelLayoutConfig:
    """
    Merge hospital defaults with per-print overrides.

    When single_label=True and the caller did not pass labels_per_row, force
    thermal 1×1 so hospital 2/3-across presets do not widen a solitary reprint.
    An explicit labels_per_row from the print dialog is always honored.
    """
    data = dict(base or {})
    explicit_across = overrides is not None and "labels_per_row" in overrides
    if overrides:
        for key, value in overrides.items():
            if key in LABEL_LAYOUT_OVERRIDE_KEYS and value is not None:
                data[key] = value
    if single_label:
        mode = str(data.get("sheet_mode") or "thermal").lower()
        if mode != "avery":
            data["sheet_mode"] = "thermal"
            if not explicit_across:
                data["labels_per_row"] = 1
                data["labels_per_column"] = 1
            else:
                data["labels_per_column"] = 1
    return LabelLayoutConfig.from_dict(data)


def _truncate(text: str, max_len: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def _truncate_to_width(
    c: canvas.Canvas,
    text: str,
    font: str,
    size: float,
    max_width: float,
) -> str:
    t = (text or "").strip()
    if not t or max_width <= 0:
        return ""
    if c.stringWidth(t, font, size) <= max_width:
        return t
    ell = "…"
    while len(t) > 1 and c.stringWidth(t + ell, font, size) > max_width:
        t = t[:-1]
    return (t + ell) if t else ell


def _fit_font_size(
    c: canvas.Canvas,
    text: str,
    font: str,
    max_pt: float,
    min_pt: float,
    max_width: float,
) -> float:
    if not text or max_width <= 0:
        return min_pt
    for pt in range(int(max_pt), int(min_pt) - 1, -1):
        if c.stringWidth(text, font, float(pt)) <= max_width:
            return float(pt)
    return min_pt


def _wrap_lines_to_width(
    c: canvas.Canvas,
    text: str,
    font: str,
    size: float,
    max_width: float,
    max_lines: int = 4,
) -> List[str]:
    words = (text or "").strip().split()
    if not words or max_width <= 0:
        return []
    lines: List[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if c.stringWidth(trial, font, size) <= max_width:
            current = trial
            continue
        if current:
            lines.append(current)
            if len(lines) >= max_lines:
                current = ""
                break
        current = word
        if c.stringWidth(current, font, size) > max_width:
            current = _truncate_to_width(c, word, font, size, max_width)
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if len(lines) == max_lines and len(words) > 1:
        lines[-1] = _truncate_to_width(c, lines[-1], font, size, max_width)
    return lines


def _pt_to_mm(pt: float) -> float:
    return pt * (25.4 / 72.0)


def _font_ascent_pt(font: str, size: float) -> float:
    try:
        from reportlab.pdfbase.pdfmetrics import getAscent

        return getAscent(font) * size / 1000.0
    except Exception:
        return size * 0.72


def _content_rect(
    layout: LabelLayoutConfig,
    x0: float,
    y0: float,
) -> tuple[float, float, float, float]:
    """Drawable area inside a label slot (x, y, width, height). y is bottom edge."""
    w = layout.width_mm * mm
    h = layout.height_mm * mm
    if layout.sheet_mode == "thermal":
        inset_l = layout.margin_left_mm * mm
        inset_t = layout.margin_top_mm * mm
        inset_b = max(0.8 * mm, inset_t * 0.35)
        inset_r = max(0.5 * mm, inset_l * 0.35)
        cx = x0 + inset_l
        cy = y0 + inset_b
        cw = max(1.0, w - inset_l - inset_r)
        ch = max(1.0, h - inset_t - inset_b)
        return cx, cy, cw, ch
    pad = 1.0 * mm
    return x0 + pad, y0 + pad, w - 2 * pad, h - 2 * pad


def _draw_lab_label(
    c: canvas.Canvas,
    layout: LabelLayoutConfig,
    x0: float,
    y0: float,
    label: dict[str, Any],
    lab_display_name: str,
) -> None:
    """Lab tube sticker: header text / barcode / footer MRN in exclusive bands."""
    w = layout.width_mm * mm
    h = layout.height_mm * mm
    pad = max(1.0 * mm, min(1.8 * mm, h * 0.05, w * 0.03))

    patient_name = _truncate(label.get("patient_name") or "", 28)
    sample_id = label.get("sample_id") or ""
    mrn = label.get("mrn") or ""
    sample_ean = label.get("sample_ean13") or ""

    name_pt = 7.0
    meta_pt = 6.0
    line_gap = 2.4 * mm
    header_content = (
        _text_ascent_mm(name_pt)
        + line_gap
        + _text_ascent_mm(meta_pt)
        + _text_descent_mm(meta_pt)
    )
    footer_content = (
        (_text_ascent_mm(meta_pt) + _text_descent_mm(meta_pt)) if mrn else 0.0
    )
    header_h = max(header_content + 0.4 * mm, min(10.0 * mm, h * 0.28))
    footer_h = max(footer_content + 0.4 * mm, min(5.0 * mm, h * 0.14)) if mrn else 1.2 * mm

    usable_top = y0 + h - pad
    usable_bottom = y0 + pad
    header_bottom = usable_top - header_h
    footer_top = usable_bottom + footer_h
    bar_bottom = footer_top + TEXT_BARCODE_GAP
    bar_top = header_bottom - TEXT_BARCODE_GAP
    bar_h = max(0.0, bar_top - bar_bottom)
    bar_w = max(1.0, w - 2 * pad)

    # Header band (glyphs stay above header_bottom).
    name_baseline = usable_top - _text_ascent_mm(name_pt)
    sample_baseline = name_baseline - line_gap
    c.setFont("Helvetica-Bold", name_pt)
    c.drawString(x0 + pad, name_baseline, patient_name)
    c.setFont("Helvetica", meta_pt)
    c.drawString(x0 + pad, sample_baseline, f"Sample: {sample_id}")

    if layout.show_lab_name:
        c.setFont("Helvetica-Bold", meta_pt)
        lab_name = _truncate(
            layout.lab_name_override or lab_display_name or "Laboratory",
            18,
        )
        c.drawRightString(x0 + w - pad, name_baseline, lab_name)

    if sample_ean and bar_h >= 3.5 * mm:
        draw_linear_barcode(
            c,
            sample_ean,
            x0 + pad,
            bar_bottom,
            bar_w,
            bar_h,
            symbology=resolve_label_symbology(sample_ean, force="code128"),
            human_readable=False,
            align="center",
            area_width=bar_w,
        )

    if mrn:
        c.setFont("Helvetica", meta_pt)
        mrn_baseline = usable_bottom + _text_descent_mm(meta_pt)
        c.drawString(x0 + pad, mrn_baseline, f"MRN: {_truncate(mrn, 24)}")


def _draw_pharmacy_label(
    c: canvas.Canvas,
    layout: LabelLayoutConfig,
    x0: float,
    y0: float,
    label: dict[str, Any],
    pharmacy_display_name: str = "",
) -> None:
    w = layout.width_mm * mm
    h = layout.height_mm * mm
    side = max(w * 0.01, min(w * 0.03, w * PHARMACY_SIDE_MARGIN_RATIO))
    ix = x0 + side
    iy = y0 + side
    iw = max(1.0, w - 2 * side)
    ih = max(1.0, h - 2 * side)

    name = (label.get("name") or "").strip()
    batch = label.get("batch_number") or ""
    expiry = label.get("expiry_date") or ""
    if expiry:
        expiry = str(expiry).split("T")[0]
    barcode = label.get("batch_barcode") or label.get("barcode") or ""

    header_h, footer_h = _pharmacy_band_heights(ih)
    header_bottom = iy + ih - header_h
    footer_top = iy + footer_h
    # Keep an explicit gap so barcode digits never touch footer text.
    bar_zone_bottom = footer_top + max(PHARMACY_ZONE_GAP, TEXT_BARCODE_GAP)
    bar_zone_top = header_bottom - max(PHARMACY_ZONE_GAP, TEXT_BARCODE_GAP)
    bar_zone_h = max(0.0, bar_zone_top - bar_zone_bottom)

    ref_h = layout.height_mm * mm
    scale = footer_h / (ref_h * PHARMACY_DETAIL_ZONE_RATIO) if ref_h > 0 else 1.0
    name_pt = max(4.0, min(6.0, 5.0 * scale))
    detail_pt = max(3.8, min(5.5, 4.8 * scale))
    header_pt = max(3.5, min(6.0, (header_h / mm) * 1.55))
    line_gap = max(1.6 * mm, min(2.4 * mm, footer_h * 0.22))
    descent = _text_descent_mm(detail_pt)
    ascent_name = _text_ascent_mm(name_pt)

    expiry_y = iy + descent
    batch_y = expiry_y + line_gap
    item_y = batch_y + line_gap
    # If three lines would climb into the barcode gap, compress spacing.
    item_top = item_y + ascent_name
    max_item_top = footer_top - 0.2 * mm
    if item_top > max_item_top and item_y > expiry_y:
        overflow = item_top - max_item_top
        shrink = overflow / 2.0
        line_gap = max(1.2 * mm, line_gap - shrink)
        batch_y = expiry_y + line_gap
        item_y = batch_y + line_gap

    provider_fit = ""
    provider_pt = header_pt
    if layout.show_pharmacy_name:
        provider = (layout.pharmacy_name_override or pharmacy_display_name or "").strip()
        if provider:
            provider_pt = _fit_font_size(
                c, provider, "Helvetica-Bold", header_pt, 3.5, iw,
            )
            provider_fit = _truncate_to_width(
                c, provider, "Helvetica-Bold", provider_pt, iw,
            )

    if barcode and bar_zone_h >= 3.0 * mm:
        draw_barcode_with_digits_below(
            c,
            barcode,
            ix + iw / 2,
            bar_zone_bottom,
            iw,
            bar_zone_h,
            symbology=resolve_label_symbology(barcode),
        )

    if provider_fit:
        # Keep provider glyphs inside the header band.
        header_baseline = header_bottom + (header_h - _text_ascent_mm(provider_pt)) / 2
        header_baseline = min(
            iy + ih - _text_ascent_mm(provider_pt) - 0.2 * mm,
            max(header_bottom + _text_descent_mm(provider_pt), header_baseline),
        )
        c.setFont("Helvetica-Bold", provider_pt)
        c.drawCentredString(ix + iw / 2, header_baseline, provider_fit)

    c.setFont("Helvetica-Bold", name_pt)
    c.drawString(
        ix,
        item_y,
        _truncate_to_width(c, name, "Helvetica-Bold", name_pt, iw),
    )
    c.setFont("Helvetica", detail_pt)
    c.drawString(
        ix,
        batch_y,
        _truncate_to_width(c, f"Batch: {batch}", "Helvetica", detail_pt, iw),
    )
    c.drawString(
        ix,
        expiry_y,
        _truncate_to_width(c, f"Expiry: {expiry}", "Helvetica", detail_pt, iw),
    )


def _draw_patient_file_label(
    c: canvas.Canvas,
    layout: LabelLayoutConfig,
    x0: float,
    y0: float,
    label: dict[str, Any],
) -> None:
    """Patient file sticker: barcode band on top, demographics below — no overlap."""
    w = layout.width_mm * mm
    h = layout.height_mm * mm
    pad = max(0.8 * mm, min(1.8 * mm, h * 0.04, w * 0.03))

    mrn = (label.get("mrn") or "").strip()
    mrn_ean = (label.get("mrn_ean13") or "").strip()
    patient_name = (label.get("patient_name") or "").strip()
    pat_type = (label.get("pat_type") or "Self Paying").strip()
    age_gender = (label.get("age_gender") or "").strip()
    bill_date = (label.get("bill_date") or "").strip()
    order_no = (label.get("order_no") or "").strip()
    ref_name = (label.get("ref_name") or "").strip()

    usable_w = max(1.0, w - 2 * pad)
    label_pt = max(5.0, min(7.0, (h / mm) * 0.16))
    line = max(2.4 * mm, min(3.8 * mm, h * 0.085))
    body_lines = 4 + (1 if (order_no or ref_name) else 0)
    # Body needs ascent of first line + (n-1)*line + descent of last line.
    body_budget = (
        _text_ascent_mm(label_pt)
        + max(0, body_lines - 1) * line
        + _text_descent_mm(label_pt)
        + 0.4 * mm
    )

    digit_pt = max(4.5, min(6.0, (h / mm) * 0.14))
    side_by_side = w >= 55 * mm and bool(mrn)
    digit_reserve = 0.0 if side_by_side else (
        _text_ascent_mm(digit_pt) + _text_descent_mm(digit_pt) + 0.4 * mm
    )

    bar_h = max(5.0 * mm, min(11.0 * mm, h - body_budget - digit_reserve - 2 * pad - TEXT_BARCODE_GAP))
    if bar_h + body_budget + digit_reserve + 2 * pad + TEXT_BARCODE_GAP > h:
        bar_h = max(4.0 * mm, h * 0.26)

    bar_top = y0 + h - pad
    bar_bottom = bar_top - bar_h
    mrn_text_w = min(usable_w * 0.30, 26 * mm) if side_by_side else 0.0
    bar_max_w = usable_w - mrn_text_w - (1.5 * mm if side_by_side else 0.0)
    bars_h = max(3.0 * mm, bar_h - (0.0 if side_by_side else 0.2 * mm))

    if mrn_ean and bar_h >= 3.5 * mm:
        # Bars sit in the upper part of the barcode band; digits (if any) below bars.
        bars_bottom = bar_bottom + (0.0 if side_by_side else digit_reserve)
        draw_linear_barcode(
            c,
            mrn_ean,
            x0 + pad,
            bars_bottom,
            bar_max_w,
            max(2.5 * mm, bar_top - bars_bottom - 0.2 * mm),
            symbology=resolve_label_symbology(mrn_ean, force="code128"),
            human_readable=False,
            align="center" if not side_by_side else "left",
            area_width=bar_max_w,
        )
        if not side_by_side and mrn:
            c.setFont("Helvetica", digit_pt)
            digit_baseline = bar_bottom + _text_descent_mm(digit_pt)
            c.drawCentredString(x0 + w / 2, digit_baseline, _truncate(mrn, 22))

    if mrn and side_by_side:
        c.setFont("Helvetica-Bold", max(5.5, min(7.0, (h / mm) * 0.16)))
        # Vertically center in barcode band without leaving the band.
        side_pt = max(5.5, min(7.0, (h / mm) * 0.16))
        side_baseline = bar_bottom + (bar_h - _text_ascent_mm(side_pt)) / 2
        c.drawRightString(x0 + w - pad, side_baseline, _truncate(mrn, 18))

    # First body baseline: full ascent stays below barcode band + gap.
    y = bar_bottom - TEXT_BARCODE_GAP - _text_ascent_mm(label_pt)

    def draw_line(text: str, *, bold: bool = False) -> None:
        nonlocal y
        if y < y0 + pad:
            return
        font = "Helvetica-Bold" if bold else "Helvetica"
        c.setFont(font, label_pt)
        c.drawString(
            x0 + pad,
            y,
            _truncate_to_width(c, text, font, label_pt, usable_w),
        )
        y -= line

    def draw_split(left: str, right: str) -> None:
        nonlocal y
        if y < y0 + pad:
            return
        c.setFont("Helvetica", label_pt)
        half = usable_w * 0.52
        if left:
            c.drawString(
                x0 + pad,
                y,
                _truncate_to_width(c, left, "Helvetica", label_pt, half),
            )
        if right:
            c.drawRightString(
                x0 + w - pad,
                y,
                _truncate_to_width(c, right, "Helvetica", label_pt, usable_w - half - 1 * mm),
            )
        y -= line

    draw_line(f"Pat Type:  {pat_type}")
    draw_line(f"YHNO :  {mrn}" if mrn else "YHNO :  —")
    draw_line(f"Patient Name :  {patient_name}", bold=True)
    draw_split(
        f"Age: {age_gender}" if age_gender else "Age: —",
        f"Bill Date : {bill_date}" if bill_date else "",
    )
    if order_no or ref_name:
        draw_split(
            f"Order No : {order_no}" if order_no else "",
            f"Ref Name: {_truncate(ref_name, 28)}" if ref_name else "",
        )
    elif ref_name:
        draw_line(f"Ref Name: {_truncate(ref_name, 40)}")


def _draw_test_label(
    c: canvas.Canvas,
    layout: LabelLayoutConfig,
    x0: float,
    y0: float,
) -> None:
    """Calibration sticker: exclusive header / barcode / footer bands."""
    w = layout.width_mm * mm
    h = layout.height_mm * mm
    pad = 1.5 * mm
    title_pt = 7.0
    meta_pt = 5.5
    digit_pt = 6.0
    hint_pt = 5.0

    header_h = (
        _text_ascent_mm(title_pt)
        + 2.2 * mm
        + _text_ascent_mm(meta_pt)
        + _text_descent_mm(meta_pt)
        + 3.5 * mm  # ruler ticks + numbers
    )
    footer_h = (
        _text_ascent_mm(digit_pt)
        + 1.6 * mm
        + _text_ascent_mm(hint_pt)
        + _text_descent_mm(hint_pt)
    )
    usable_top = y0 + h - pad
    usable_bottom = y0 + pad
    header_bottom = usable_top - header_h
    footer_top = usable_bottom + footer_h
    bar_bottom = footer_top + TEXT_BARCODE_GAP
    bar_top = header_bottom - TEXT_BARCODE_GAP
    bar_h = max(4.0 * mm, bar_top - bar_bottom)

    title_baseline = usable_top - _text_ascent_mm(title_pt)
    meta_baseline = title_baseline - 2.2 * mm
    c.setFont("Helvetica-Bold", title_pt)
    c.drawString(x0 + pad, title_baseline, "KT HEALTH — TEST LABEL")
    c.setFont("Helvetica", meta_pt)
    c.drawString(
        x0 + pad,
        meta_baseline,
        f"Configured {layout.width_mm:.1f}×{layout.height_mm:.1f} mm — measure edge",
    )

    tick_y = meta_baseline - 1.2 * mm
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(0.4)
    c.line(x0 + pad, tick_y, x0 + w - pad, tick_y)
    n_ticks = max(1, int(layout.width_mm // 10))
    for i in range(n_ticks + 1):
        tx = x0 + pad + i * 10 * mm
        if tx > x0 + w - pad + 0.1:
            break
        c.line(tx, tick_y, tx, tick_y - 2.0 * mm)
        if i > 0:
            c.setFont("Helvetica", 4)
            c.drawCentredString(tx, tick_y - 3.6 * mm, f"{i * 10}")

    if bar_h >= 3.5 * mm:
        draw_linear_barcode(
            c,
            TEST_LABEL_BARCODE,
            x0 + pad,
            bar_bottom,
            max(1.0, w - 2 * pad),
            bar_h,
            symbology="code128",
            human_readable=False,
            align="center",
            area_width=max(1.0, w - 2 * pad),
        )

    c.setFont("Helvetica", digit_pt)
    digit_baseline = footer_top - TEXT_BARCODE_GAP / 2 - _text_ascent_mm(digit_pt)
    digit_baseline = max(usable_bottom + _text_descent_mm(hint_pt) + 1.6 * mm, digit_baseline)
    c.drawCentredString(x0 + w / 2, digit_baseline, TEST_LABEL_BARCODE)
    c.setFont("Helvetica", hint_pt)
    c.drawCentredString(
        x0 + w / 2,
        usable_bottom + _text_descent_mm(hint_pt),
        "Scan this Code128 — should read the digits above",
    )

def _page_size(layout: LabelLayoutConfig) -> tuple[float, float]:
    if layout.sheet_mode == "avery":
        return layout.sheet_width_mm * mm, layout.sheet_height_mm * mm
    lw = layout.width_mm * mm
    lh = layout.height_mm * mm
    gx = layout.gutter_mm * mm
    gy = layout.gutter_mm * mm
    page_w = layout.labels_per_row * lw + max(0, layout.labels_per_row - 1) * gx
    page_h = layout.labels_per_column * lh + max(0, layout.labels_per_column - 1) * gy
    return page_w, page_h


def page_size_mm(layout: LabelLayoutConfig) -> tuple[float, float]:
    """Page width/height in millimetres (thermal multi-up or Avery sheet)."""
    pw, ph = _page_size(layout)
    return pw / mm, ph / mm


def _label_positions(layout: LabelLayoutConfig) -> List[tuple[float, float]]:
    positions: List[tuple[float, float]] = []
    lw = layout.width_mm * mm
    lh = layout.height_mm * mm
    gx = layout.gutter_mm * mm
    gy = layout.gutter_mm * mm

    if layout.sheet_mode == "thermal":
        for row in range(layout.labels_per_column):
            for col in range(layout.labels_per_row):
                positions.append((col * (lw + gx), row * (lh + gy)))
        return positions

    top = layout.margin_top_mm * mm
    left = layout.margin_left_mm * mm
    page_h = layout.sheet_height_mm * mm

    for row in range(layout.labels_per_column):
        for col in range(layout.labels_per_row):
            x = left + col * (lw + gx)
            y = page_h - top - lh - row * (lh + gy)
            positions.append((x, y))
    return positions


def build_label_pdf(
    labels: List[dict[str, Any]],
    layout: LabelLayoutConfig,
    label_type: str,
    lab_display_name: str = "",
    pharmacy_display_name: str = "",
) -> bytes:
    """Build a PDF for one or more labels. Each label dict is type-specific."""
    if not labels and label_type != "test":
        raise ValueError("No labels to print")
    work = labels if labels else [{}]

    buf = io.BytesIO()
    page_w, page_h = _page_size(layout)
    slots = _label_positions(layout)
    slots_per_page = len(slots)
    lw = layout.width_mm * mm
    lh = layout.height_mm * mm

    c = canvas.Canvas(buf, pagesize=(page_w, page_h))

    for idx, label in enumerate(work):
        if idx > 0 and idx % slots_per_page == 0:
            c.showPage()
        slot_idx = idx % slots_per_page
        x0, y0 = slots[slot_idx]
        c.saveState()
        clip = c.beginPath()
        clip.rect(x0, y0, lw, lh)
        c.clipPath(clip, stroke=0)
        if label_type == "lab_sample":
            _draw_lab_label(c, layout, x0, y0, label, lab_display_name)
        elif label_type == "patient_file":
            _draw_patient_file_label(c, layout, x0, y0, label)
        elif label_type == "test":
            _draw_test_label(c, layout, x0, y0)
        else:
            _draw_pharmacy_label(c, layout, x0, y0, label, pharmacy_display_name)
        c.restoreState()

    c.save()
    return buf.getvalue()


def _svg_inner(svg: str) -> str:
    """Strip XML declaration / doctype so SVG can be inlined in HTML."""
    text = (svg or "").strip()
    if not text:
        return ""
    start = text.lower().find("<svg")
    if start < 0:
        return text
    return text[start:]


def _esc(text: Any) -> str:
    return html.escape(str(text or ""), quote=True)


def _html_barcode_block(
    value: str,
    *,
    max_width_mm: float,
    max_height_mm: float,
    force_code128: bool = False,
) -> str:
    sym = resolve_label_symbology(value, force="code128" if force_code128 else None)
    svg = barcode_svg_markup(
        value,
        max_width_mm=max_width_mm,
        max_height_mm=max_height_mm,
        symbology=sym,
        human_readable=False,
    )
    if not svg:
        return f'<div class="digits">{_esc(value)}</div>'
    return (
        f'<div class="barcode">{_svg_inner(svg)}'
        f'<div class="digits">{_esc(value)}</div></div>'
    )


def _html_lab_sticker(label: dict[str, Any], layout: LabelLayoutConfig, lab_name: str) -> str:
    sample = label.get("sample_ean13") or ""
    bar = ""
    if sample:
        bar = _html_barcode_block(
            sample,
            max_width_mm=max(10.0, layout.width_mm - 4),
            max_height_mm=max(6.0, layout.height_mm * 0.40),
            force_code128=True,
        )
    lab = layout.lab_name_override or lab_name or "Laboratory"
    return (
        f'<div class="sticker lab">'
        f'<div class="zone-header">'
        f'<div class="row"><strong>{_esc(_truncate(label.get("patient_name") or "", 28))}</strong>'
        f'<span class="right">{_esc(_truncate(lab, 18))}</span></div>'
        f'<div class="meta">Sample: {_esc(label.get("sample_id") or "")}</div>'
        f'</div>'
        f'{bar}'
        f'<div class="zone-footer"><div class="meta">MRN: {_esc(label.get("mrn") or "")}</div></div>'
        f'</div>'
    )


def _html_pharmacy_sticker(
    label: dict[str, Any],
    layout: LabelLayoutConfig,
    pharmacy_name: str,
) -> str:
    barcode = label.get("batch_barcode") or label.get("barcode") or ""
    expiry = label.get("expiry_date") or ""
    if expiry:
        expiry = str(expiry).split("T")[0]
    provider = layout.pharmacy_name_override or pharmacy_name or ""
    bar = ""
    if barcode:
        bar = _html_barcode_block(
            barcode,
            max_width_mm=max(10.0, layout.width_mm * 0.92),
            max_height_mm=max(5.0, layout.height_mm * 0.36),
        )
    return (
        f'<div class="sticker pharmacy">'
        f'<div class="zone-header"><div class="provider">{_esc(_truncate(provider, 28))}</div></div>'
        f'{bar}'
        f'<div class="zone-footer">'
        f'<div class="name">{_esc(_truncate(label.get("name") or "", 36))}</div>'
        f'<div class="meta">Batch: {_esc(label.get("batch_number") or "")}</div>'
        f'<div class="meta">Expiry: {_esc(expiry)}</div>'
        f'</div>'
        f'</div>'
    )


def _html_patient_sticker(label: dict[str, Any], layout: LabelLayoutConfig) -> str:
    mrn_ean = label.get("mrn_ean13") or ""
    bar = ""
    if mrn_ean:
        bar = _html_barcode_block(
            mrn_ean,
            max_width_mm=max(10.0, layout.width_mm - 4),
            max_height_mm=max(6.0, min(10.0, layout.height_mm * 0.26)),
            force_code128=True,
        )
    return (
        f'<div class="sticker patient">'
        f'{bar}'
        f'<div class="zone-footer">'
        f'<div class="meta">Pat Type: {_esc(label.get("pat_type") or "Self Paying")}</div>'
        f'<div class="meta">YHNO : {_esc(label.get("mrn") or "—")}</div>'
        f'<div class="name">{_esc(label.get("patient_name") or "")}</div>'
        f'<div class="meta">Age: {_esc(label.get("age_gender") or "—")} · '
        f'Bill Date: {_esc(label.get("bill_date") or "")}</div>'
        f'<div class="meta">Order: {_esc(label.get("order_no") or "")} · '
        f'Ref: {_esc(_truncate(label.get("ref_name") or "", 28))}</div>'
        f'</div>'
        f'</div>'
    )


def _html_test_sticker(layout: LabelLayoutConfig) -> str:
    bar = _html_barcode_block(
        TEST_LABEL_BARCODE,
        max_width_mm=max(10.0, layout.width_mm - 4),
        max_height_mm=max(7.0, layout.height_mm * 0.38),
        force_code128=True,
    )
    ticks = "".join(
        f'<span style="left:{i * 10}mm"></span>'
        for i in range(1, max(1, int(layout.width_mm // 10)) + 1)
    )
    return (
        f'<div class="sticker test">'
        f'<div class="zone-header">'
        f'<div class="ruler">{ticks}</div>'
        f'<div class="name">KT HEALTH — TEST LABEL</div>'
        f'<div class="meta">Configured {layout.width_mm:.1f}×{layout.height_mm:.1f} mm</div>'
        f'</div>'
        f'{bar}'
        f'<div class="zone-footer">'
        f'<div class="meta">Scan Code128 — should read {TEST_LABEL_BARCODE}</div>'
        f'</div>'
        f'</div>'
    )


def build_label_html(
    labels: List[dict[str, Any]],
    layout: LabelLayoutConfig,
    label_type: str,
    lab_display_name: str = "",
    pharmacy_display_name: str = "",
) -> str:
    """
    Browser thermal print sheet with exact @page size in millimetres.

    Prefer this path for thermal roll printing; use PDF for Avery / download.
    """
    if not labels and label_type != "test":
        raise ValueError("No labels to print")
    work = labels if labels else [{}]
    page_w_mm, page_h_mm = page_size_mm(layout)
    lw = layout.width_mm
    lh = layout.height_mm
    gutter = layout.gutter_mm if layout.sheet_mode == "thermal" else layout.gutter_mm
    cols = max(1, layout.labels_per_row)

    stickers: List[str] = []
    for label in work:
        if label_type == "lab_sample":
            stickers.append(_html_lab_sticker(label, layout, lab_display_name))
        elif label_type == "patient_file":
            stickers.append(_html_patient_sticker(label, layout))
        elif label_type == "test":
            stickers.append(_html_test_sticker(layout))
        else:
            stickers.append(_html_pharmacy_sticker(label, layout, pharmacy_display_name))

    cells = "\n".join(stickers)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Label print</title>
<style>
  @page {{
    size: {page_w_mm:.3f}mm {page_h_mm:.3f}mm;
    margin: 0;
  }}
  html, body {{
    margin: 0;
    padding: 0;
    width: {page_w_mm:.3f}mm;
    background: #fff;
    color: #000;
    font-family: Helvetica, Arial, sans-serif;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }}
  .sheet {{
    display: grid;
    grid-template-columns: repeat({cols}, {lw:.3f}mm);
    column-gap: {gutter:.3f}mm;
    row-gap: {gutter:.3f}mm;
    width: {page_w_mm:.3f}mm;
    box-sizing: border-box;
  }}
  .sticker {{
    width: {lw:.3f}mm;
    height: {lh:.3f}mm;
    box-sizing: border-box;
    padding: 1.2mm;
    overflow: hidden;
    page-break-inside: avoid;
    display: flex;
    flex-direction: column;
    gap: 0.8mm;
  }}
  .sticker .zone-header,
  .sticker .zone-footer {{
    flex: 0 0 auto;
    min-height: 0;
  }}
  .sticker .row {{ display: flex; justify-content: space-between; gap: 1mm; }}
  .sticker .right {{ font-size: 6pt; font-weight: 700; }}
  .sticker .name {{ font-size: 7pt; font-weight: 700; line-height: 1.1; }}
  .sticker .provider {{ font-size: 6pt; font-weight: 700; text-align: center; }}
  .sticker .meta {{ font-size: 5.5pt; line-height: 1.15; }}
  .barcode {{
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    flex: 1 1 auto;
    min-height: 0;
    overflow: hidden;
    gap: 0.35mm;
  }}
  .barcode svg {{ max-width: 100%; max-height: 100%; height: auto; display: block; }}
  .digits {{ font-size: 5.5pt; letter-spacing: 0.04em; text-align: center; margin: 0; line-height: 1; }}
  .ruler {{ position: relative; height: 2.5mm; border-top: 0.3mm solid #000; margin-bottom: 1mm; }}
  .ruler span {{
    position: absolute; top: 0; width: 0; height: 2.2mm;
    border-left: 0.25mm solid #000;
  }}
  @media print {{
    body {{ margin: 0; }}
  }}
</style>
</head>
<body>
<div class="sheet">
{cells}
</div>
<script>
  window.addEventListener('load', function () {{
    setTimeout(function () {{
      try {{ window.focus(); window.print(); }} catch (e) {{}}
    }}, 250);
  }});
</script>
</body>
</html>
"""
