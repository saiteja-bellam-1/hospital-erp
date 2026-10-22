"""Thermal / Avery label PDF + HTML generation (non-A4 page sizes)."""
from __future__ import annotations

import html
import io
import re
from dataclasses import dataclass
from typing import Any, List, Optional
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.utils.barcode_draw import (
    DEFAULT_LABEL_DPI,
    DIGIT_BAND_RATIO,
    barcode_svg_markup,
    draw_barcode_with_digits_below,
    draw_linear_barcode,
    normalize_label_dpi,
    resolve_label_symbology,
)
from app.utils.pdf_settings import apply_thermal_roll_layout

# Shares of the full sticker. The barcode band is whatever remains, so a
# 38×25 mm sticker and a 70×40 mm sticker keep the same arrangement.
PHARMACY_PAD_X = 0.025
PHARMACY_PAD_Y = 0.018
PHARMACY_GAP = 0.012
PHARMACY_HEADER = 0.12
PHARMACY_FOOTER = 0.50
LAB_PAD_X = 0.025
LAB_PAD_Y = 0.018
LAB_GAP = 0.014
LAB_HEADER = 0.34
LAB_FOOTER = 0.16
PATIENT_PAD_X = 0.028
PATIENT_PAD_Y = 0.018
PATIENT_GAP = 0.012
PATIENT_BARCODE = 0.34
# Floor so a short sticker still has a scannable bar after text takes its share.
MIN_BARCODE_SHARE = 0.20
# Kept for callers that still want a nominal text-to-bar clearance.
TEXT_BARCODE_GAP = 0.6 * mm
# Known Code128 payload for calibration stickers (also a valid EAN-13 check digit).
TEST_LABEL_BARCODE = "2300000000108"


def _text_ascent_mm(size_pt: float) -> float:
    """Approximate Helvetica ascent height in mm for a font size in points."""
    return _pt_to_mm(size_pt * 0.72)


def _text_descent_mm(size_pt: float) -> float:
    return _pt_to_mm(size_pt * 0.28)



@dataclass(frozen=True)
class StickerBands:
    """Horizontal bands in millimetres. They sum to the sticker height."""

    pad_x_mm: float
    pad_y_mm: float
    gap_mm: float
    header_mm: float
    barcode_mm: float
    footer_mm: float
    inner_w_mm: float
    width_mm: float
    height_mm: float
    gap_count: int


def font_pt_for_band(band_mm: float, fill: float = 0.82) -> float:
    """Point size whose em box fills `fill` of one text band."""
    if band_mm <= 0:
        return 1.0
    return band_mm * fill * 72.0 / 25.4


def sticker_bands(
    width_mm: float,
    height_mm: float,
    *,
    header: float,
    footer: float,
    pad_x: float,
    pad_y: float,
    gap: float,
    gap_count: int = 2,
) -> StickerBands:
    """Split a sticker into padding, header, barcode, and footer by percentage."""
    gaps = max(0, gap_count) * gap
    fixed = (2 * pad_y) + gaps
    room = max(0.0, 1.0 - fixed)
    header_r = max(0.0, header)
    footer_r = max(0.0, footer)
    if header_r + footer_r > room - MIN_BARCODE_SHARE and header_r + footer_r > 0:
        scale = max(0.0, (room - MIN_BARCODE_SHARE) / (header_r + footer_r))
        header_r *= scale
        footer_r *= scale
    barcode_r = max(0.0, 1.0 - fixed - header_r - footer_r)
    w = float(width_mm)
    h = float(height_mm)
    return StickerBands(
        pad_x_mm=w * pad_x,
        pad_y_mm=h * pad_y,
        gap_mm=h * gap,
        header_mm=h * header_r,
        barcode_mm=h * barcode_r,
        footer_mm=h * footer_r,
        inner_w_mm=w * (1.0 - 2 * pad_x),
        width_mm=w,
        height_mm=h,
        gap_count=max(0, gap_count),
    )


def pharmacy_sticker_bands(width_mm: float, height_mm: float, *, show_header: bool) -> StickerBands:
    return sticker_bands(
        width_mm,
        height_mm,
        header=PHARMACY_HEADER if show_header else 0.0,
        footer=PHARMACY_FOOTER,
        pad_x=PHARMACY_PAD_X,
        pad_y=PHARMACY_PAD_Y,
        gap=PHARMACY_GAP,
        gap_count=2 if show_header else 1,
    )


def lab_sticker_bands(width_mm: float, height_mm: float, *, show_footer: bool) -> StickerBands:
    return sticker_bands(
        width_mm,
        height_mm,
        header=LAB_HEADER,
        footer=LAB_FOOTER if show_footer else 0.0,
        pad_x=LAB_PAD_X,
        pad_y=LAB_PAD_Y,
        gap=LAB_GAP,
        gap_count=2 if show_footer else 1,
    )


def patient_sticker_bands(width_mm: float, height_mm: float) -> StickerBands:
    footer = 1.0 - (2 * PATIENT_PAD_Y) - PATIENT_GAP - PATIENT_BARCODE
    return sticker_bands(
        width_mm,
        height_mm,
        header=0.0,
        footer=footer,
        pad_x=PATIENT_PAD_X,
        pad_y=PATIENT_PAD_Y,
        gap=PATIENT_GAP,
        gap_count=1,
    )


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
    "dpi",
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
    dpi: int = DEFAULT_LABEL_DPI

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
            dpi=normalize_label_dpi(normalized.get("dpi", DEFAULT_LABEL_DPI)),
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
    dpi: Optional[int] = None,
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
        "dpi": dpi,
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
    if c.stringWidth(text, font, max_pt) <= max_width:
        return max_pt
    pt = min(max_pt, float(int(max_pt)))
    while pt >= min_pt:
        if c.stringWidth(text, font, pt) <= max_width:
            return pt
        pt -= 0.5
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


def _slot_baseline(slot_bottom: float, slot_h: float, pt: float) -> float:
    ascent = pt * 0.72
    descent = pt * 0.22
    extra = slot_h - ascent - descent
    return slot_bottom + descent + max(0.0, extra / 2.0)


def _draw_band_text(
    c: canvas.Canvas,
    text: str,
    font: str,
    max_pt: float,
    x: float,
    slot_bottom: float,
    slot_h: float,
    max_width: float,
    *,
    align: str = "left",
) -> None:
    shown_src = (text or "").strip()
    if slot_h <= 0 or max_width <= 0 or not shown_src:
        return
    min_pt = max(1.0, max_pt * 0.55)
    pt = _fit_font_size(c, shown_src, font, max_pt, min_pt, max_width)
    c.setFont(font, pt)
    shown = _truncate_to_width(c, shown_src, font, pt, max_width)
    baseline = _slot_baseline(slot_bottom, slot_h, pt)
    if align == "center":
        c.drawCentredString(x + max_width / 2.0, baseline, shown)
    elif align == "right":
        c.drawRightString(x + max_width, baseline, shown)
    else:
        c.drawString(x, baseline, shown)


def _draw_lab_label(
    c: canvas.Canvas,
    layout: LabelLayoutConfig,
    x0: float,
    y0: float,
    label: dict[str, Any],
    lab_display_name: str,
) -> None:
    """Lab tube sticker: header / barcode / MRN, each a share of the sticker."""
    mrn = (label.get("mrn") or "").strip()
    bands = lab_sticker_bands(layout.width_mm, layout.height_mm, show_footer=bool(mrn))
    pad_x = bands.pad_x_mm * mm
    pad_y = bands.pad_y_mm * mm
    gap = bands.gap_mm * mm
    header_h = bands.header_mm * mm
    footer_h = bands.footer_mm * mm
    bar_h = bands.barcode_mm * mm
    ix = x0 + pad_x
    iw = bands.inner_w_mm * mm
    footer_bottom = y0 + pad_y
    bar_bottom = footer_bottom + footer_h + (gap if footer_h else 0.0)
    header_bottom = y0 + layout.height_mm * mm - pad_y - header_h

    patient_name = label.get("patient_name") or ""
    sample_id = label.get("sample_id") or ""
    sample_ean = label.get("sample_ean13") or ""
    line_h = header_h / 2.0
    name_pt = font_pt_for_band(bands.header_mm / 2.0, 0.86)
    meta_pt = font_pt_for_band(bands.header_mm / 2.0, 0.80)
    name_w = iw * 0.62
    _draw_band_text(
        c, patient_name, "Helvetica-Bold", name_pt, ix,
        header_bottom + line_h, line_h, name_w,
    )
    if layout.show_lab_name:
        lab_name = layout.lab_name_override or lab_display_name or "Laboratory"
        _draw_band_text(
            c, lab_name, "Helvetica-Bold", meta_pt, ix + iw * 0.64,
            header_bottom + line_h, line_h, iw * 0.36, align="right",
        )
    _draw_band_text(
        c, f"Sample: {sample_id}", "Helvetica", meta_pt, ix,
        header_bottom, line_h, iw,
    )

    if sample_ean and bar_h >= 3.0 * mm:
        draw_linear_barcode(
            c,
            sample_ean,
            ix,
            bar_bottom,
            iw,
            bar_h,
            symbology=resolve_label_symbology(sample_ean, force="code128"),
            human_readable=False,
            align="center",
            area_width=iw,
            dpi=layout.dpi,
        )

    if mrn and footer_h > 0:
        footer_pt = font_pt_for_band(bands.footer_mm, 0.82)
        _draw_band_text(
            c, f"MRN: {mrn}", "Helvetica", footer_pt, ix,
            footer_bottom, footer_h, iw,
        )


def _draw_pharmacy_label(
    c: canvas.Canvas,
    layout: LabelLayoutConfig,
    x0: float,
    y0: float,
    label: dict[str, Any],
    pharmacy_display_name: str = "",
) -> None:
    """Medicine sticker: pharmacy name, full-width barcode, then name / batch / expiry."""
    name = (label.get("name") or "").strip()
    batch = label.get("batch_number") or ""
    expiry = str(label.get("expiry_date") or "").split("T")[0]
    barcode = label.get("batch_barcode") or label.get("barcode") or ""
    provider = ""
    if layout.show_pharmacy_name:
        provider = (layout.pharmacy_name_override or pharmacy_display_name or "").strip()

    bands = pharmacy_sticker_bands(
        layout.width_mm, layout.height_mm, show_header=bool(provider),
    )
    pad_x = bands.pad_x_mm * mm
    pad_y = bands.pad_y_mm * mm
    gap = bands.gap_mm * mm
    header_h = bands.header_mm * mm
    footer_h = bands.footer_mm * mm
    bar_h = bands.barcode_mm * mm
    ix = x0 + pad_x
    iw = bands.inner_w_mm * mm
    footer_bottom = y0 + pad_y
    bar_bottom = footer_bottom + footer_h + gap
    header_bottom = y0 + layout.height_mm * mm - pad_y - header_h

    if provider and header_h > 0:
        header_pt = font_pt_for_band(bands.header_mm, 0.82)
        _draw_band_text(
            c, provider, "Helvetica-Bold", header_pt, ix,
            header_bottom, header_h, iw, align="center",
        )

    if barcode and bar_h >= 3.0 * mm:
        draw_barcode_with_digits_below(
            c,
            barcode,
            ix + iw / 2.0,
            bar_bottom,
            iw,
            bar_h,
            symbology=resolve_label_symbology(barcode),
            dpi=layout.dpi,
        )

    line_h = footer_h / 3.0
    name_pt = font_pt_for_band(bands.footer_mm / 3.0, 0.88)
    detail_pt = font_pt_for_band(bands.footer_mm / 3.0, 0.80)
    _draw_band_text(
        c, name, "Helvetica-Bold", name_pt, ix,
        footer_bottom + 2 * line_h, line_h, iw,
    )
    _draw_band_text(
        c, f"Batch: {batch}", "Helvetica", detail_pt, ix,
        footer_bottom + line_h, line_h, iw,
    )
    _draw_band_text(
        c, f"Expiry: {expiry}", "Helvetica", detail_pt, ix,
        footer_bottom, line_h, iw,
    )


def patient_body_rows(label: dict[str, Any]) -> List[tuple]:
    """Stacked patient-file lines. A pair stays in two columns with a fixed gap share."""
    mrn = (label.get("mrn") or "").strip()
    patient_name = (label.get("patient_name") or "").strip()
    pat_type = (label.get("pat_type") or "Self Paying").strip()
    age_gender = (label.get("age_gender") or "").strip()
    bill_date = (label.get("bill_date") or "").strip()
    order_no = (label.get("order_no") or "").strip()
    ref_name = (label.get("ref_name") or "").strip()
    rows: List[tuple] = [
        ("meta", f"Pat Type:  {pat_type}", ""),
        ("meta", f"YHNO :  {mrn}" if mrn else "YHNO :  —", ""),
        ("name", f"Patient Name :  {patient_name}", ""),
        ("meta", f"Age: {age_gender}" if age_gender else "Age: —", ""),
    ]
    if bill_date:
        rows.append(("meta", f"Bill Date : {bill_date}", ""))
    if order_no:
        rows.append(("meta", f"Order No : {order_no}", ""))
    if ref_name:
        rows.append(("meta", f"Ref Name: {ref_name}", ""))
    return rows


def _draw_patient_file_label(
    c: canvas.Canvas,
    layout: LabelLayoutConfig,
    x0: float,
    y0: float,
    label: dict[str, Any],
) -> None:
    """Patient file sticker: full-width barcode, then lines that share the rest."""
    mrn = (label.get("mrn") or "").strip()
    barcode_value = mrn or (label.get("mrn_ean13") or "").strip()
    bands = patient_sticker_bands(layout.width_mm, layout.height_mm)
    pad_x = bands.pad_x_mm * mm
    pad_y = bands.pad_y_mm * mm
    gap = bands.gap_mm * mm
    footer_h = bands.footer_mm * mm
    bar_h = bands.barcode_mm * mm
    ix = x0 + pad_x
    iw = bands.inner_w_mm * mm
    footer_bottom = y0 + pad_y
    bar_bottom = footer_bottom + footer_h + gap

    if barcode_value and bar_h >= 3.0 * mm:
        draw_barcode_with_digits_below(
            c,
            barcode_value,
            ix + iw / 2.0,
            bar_bottom,
            iw,
            bar_h,
            symbology="code128",
            dpi=layout.dpi,
        )

    rows = patient_body_rows(label)
    if not rows or footer_h <= 0:
        return
    line_h = footer_h / len(rows)
    line_mm = bands.footer_mm / len(rows)
    name_pt = font_pt_for_band(line_mm, 0.88)
    meta_pt = font_pt_for_band(line_mm, 0.80)
    left_w = iw * 0.58
    right_x = ix + iw * 0.62
    right_w = iw * 0.38
    for index, (kind, left, right) in enumerate(reversed(rows)):
        slot_bottom = footer_bottom + index * line_h
        if kind == "pair":
            _draw_band_text(
                c, left, "Helvetica", meta_pt, ix, slot_bottom, line_h, left_w,
            )
            _draw_band_text(
                c, right, "Helvetica", meta_pt, right_x, slot_bottom, line_h, right_w,
                align="right",
            )
        else:
            font = "Helvetica-Bold" if kind == "name" else "Helvetica"
            pt = name_pt if kind == "name" else meta_pt
            _draw_band_text(c, left, font, pt, ix, slot_bottom, line_h, iw)


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
            dpi=layout.dpi,
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


def _svg_fill(svg: str, width_mm: float, height_mm: float) -> str:
    """Size the symbol in millimetres. A unitless SVG width is CSS pixels and stays small."""
    inner = _svg_inner(svg)
    inner = re.sub(
        r'\swidth="[^"]*"',
        f' width="{width_mm:.2f}mm"',
        inner,
        count=1,
    )
    inner = re.sub(
        r'\sheight="[^"]*"',
        f' height="{height_mm:.2f}mm"',
        inner,
        count=1,
    )
    return inner.replace("xMinYMin meet", "xMidYMid meet")


def _fit_html_line(text: str, pt: float, width_mm: float, *, bold: bool = False) -> tuple[float, str]:
    """Shrink type just enough to keep the line; ellipsis only when it still will not fit."""
    raw = (text or "").strip()
    if not raw or pt <= 0 or width_mm <= 0:
        return pt, raw
    factor = 0.50 if bold else 0.46
    em_mm = pt * 25.4 / 72.0
    need = len(raw) * em_mm * factor
    if need <= width_mm:
        return pt, raw
    fitted = pt * (width_mm / need)
    floor = pt * 0.70
    if fitted >= floor:
        return fitted, raw
    max_chars = max(4, int(width_mm / (floor * 25.4 / 72.0 * factor)))
    shown = raw if len(raw) <= max_chars else raw[: max_chars - 1] + "…"
    return floor, shown


def _html_sized(
    tag_class: str,
    text: str,
    pt: float,
    width_mm: float,
    *,
    bold: bool = False,
    tag: str = "div",
) -> str:
    fitted, shown = _fit_html_line(text, pt, width_mm, bold=bold)
    style = ""
    if abs(fitted - pt) > 0.3:
        style = f' style="font-size:{fitted:.2f}pt"'
    return f'<{tag} class="{tag_class}"{style}>{_esc(shown)}</{tag}>'


def _esc(text: Any) -> str:
    return html.escape(str(text or ""), quote=True)


def _html_fonts(kind: str, bands: StickerBands, body_lines: int) -> dict[str, float]:
    if kind == "pharmacy":
        line_mm = bands.footer_mm / 3.0
        header_pt = font_pt_for_band(bands.header_mm or line_mm, 0.82)
    elif kind == "patient":
        line_mm = bands.footer_mm / max(1, body_lines)
        header_pt = font_pt_for_band(line_mm, 0.80)
    else:
        line_mm = (bands.header_mm / 2.0) if bands.header_mm else bands.footer_mm
        header_pt = font_pt_for_band(line_mm, 0.82)
    return {
        "header_pt": header_pt,
        "name_pt": font_pt_for_band(line_mm, 0.88),
        "meta_pt": font_pt_for_band(line_mm if kind != "lab" else (bands.footer_mm or line_mm), 0.80),
        "digit_pt": font_pt_for_band(bands.barcode_mm * DIGIT_BAND_RATIO, 0.85),
    }


def _html_layout_for(
    layout: LabelLayoutConfig,
    label_type: str,
    labels: List[dict[str, Any]],
    pharmacy_display_name: str,
) -> tuple[str, StickerBands, int]:
    if label_type == "lab_sample":
        return "lab", lab_sticker_bands(layout.width_mm, layout.height_mm, show_footer=True), 2
    if label_type == "patient_file":
        counts = [len(patient_body_rows(label)) for label in labels] or [4]
        return "patient", patient_sticker_bands(layout.width_mm, layout.height_mm), max(counts)
    if label_type == "test":
        bands = sticker_bands(
            layout.width_mm,
            layout.height_mm,
            header=0.30,
            footer=0.18,
            pad_x=LAB_PAD_X,
            pad_y=LAB_PAD_Y,
            gap=LAB_GAP,
            gap_count=2,
        )
        return "test", bands, 2
    provider = ""
    if layout.show_pharmacy_name:
        provider = (layout.pharmacy_name_override or pharmacy_display_name or "").strip()
    return (
        "pharmacy",
        pharmacy_sticker_bands(layout.width_mm, layout.height_mm, show_header=bool(provider)),
        3,
    )


def _html_barcode_block(
    value: str,
    *,
    max_width_mm: float,
    max_height_mm: float,
    force_code128: bool = False,
    show_digits: bool = True,
    dpi: int = DEFAULT_LABEL_DPI,
) -> str:
    bars_h = max_height_mm * (1.0 - DIGIT_BAND_RATIO) if show_digits else max_height_mm
    bars_h = max(2.0, bars_h)
    digit_h = max(0.0, max_height_mm - bars_h) if show_digits else 0.0
    sym = resolve_label_symbology(value, force="code128" if force_code128 else None)
    svg = barcode_svg_markup(
        value,
        max_width_mm=max(4.0, max_width_mm),
        max_height_mm=bars_h,
        symbology=sym,
        human_readable=False,
        dpi=dpi,
    )
    digits = (
        f'<div class="digits" style="height:{digit_h:.2f}mm">{_esc(value)}</div>'
        if show_digits else ""
    )
    if not svg:
        return f'<div class="barcode" style="height:{max_height_mm:.2f}mm">{digits}</div>'
    return (
        f'<div class="barcode" style="height:{max_height_mm:.2f}mm">'
        f'<div class="bars" style="height:{bars_h:.2f}mm">{_svg_fill(svg, max_width_mm, bars_h)}</div>'
        f'{digits}</div>'
    )


def _html_lab_sticker(
    label: dict[str, Any],
    layout: LabelLayoutConfig,
    lab_name: str,
    bands: StickerBands,
    fonts: dict[str, float],
) -> str:
    sample = label.get("sample_ean13") or ""
    bar = ""
    if sample:
        bar = _html_barcode_block(
            sample,
            max_width_mm=bands.inner_w_mm,
            max_height_mm=bands.barcode_mm,
            force_code128=True,
            show_digits=False,
            dpi=layout.dpi,
        )
    lab = layout.lab_name_override or lab_name or "Laboratory"
    patient = _html_sized("l name", label.get("patient_name") or "", fonts["name_pt"], bands.inner_w_mm * 0.62, bold=True, tag="span")
    lab_fit = _html_sized("r meta", lab, fonts["meta_pt"], bands.inner_w_mm * 0.36, bold=True, tag="span")
    sample_line = _html_sized("meta", f"Sample: {label.get('sample_id') or ''}", fonts["meta_pt"], bands.inner_w_mm)
    mrn_line = _html_sized("meta", f"MRN: {label.get('mrn') or ''}", fonts["meta_pt"], bands.inner_w_mm)
    return (
        f'<div class="sticker lab">'
        f'<div class="zone-header">'
        f'<div class="row">{patient}{lab_fit}</div>'
        f'{sample_line}'
        f'</div>'
        f'{bar}'
        f'<div class="zone-footer">{mrn_line}</div>'
        f'</div>'
    )


def _html_pharmacy_sticker(
    label: dict[str, Any],
    layout: LabelLayoutConfig,
    pharmacy_name: str,
    bands: StickerBands,
    fonts: dict[str, float],
) -> str:
    barcode = label.get("batch_barcode") or label.get("barcode") or ""
    expiry = str(label.get("expiry_date") or "").split("T")[0]
    provider = ""
    if layout.show_pharmacy_name:
        provider = (layout.pharmacy_name_override or pharmacy_name or "").strip()
    bar = ""
    if barcode:
        bar = _html_barcode_block(
            barcode,
            max_width_mm=bands.inner_w_mm,
            max_height_mm=bands.barcode_mm,
            dpi=layout.dpi,
        )
    header = ""
    if provider and bands.header_mm > 0:
        header = (
            '<div class="zone-header">'
            + _html_sized("provider", provider, fonts["header_pt"], bands.inner_w_mm, bold=True)
            + "</div>"
        )
    name = _html_sized("name", label.get("name") or "", fonts["name_pt"], bands.inner_w_mm, bold=True)
    batch = _html_sized("meta", f"Batch: {label.get('batch_number') or ''}", fonts["meta_pt"], bands.inner_w_mm)
    expiry_line = _html_sized("meta", f"Expiry: {expiry}", fonts["meta_pt"], bands.inner_w_mm)
    return (
        f'<div class="sticker pharmacy">'
        f'{header}'
        f'{bar}'
        f'<div class="zone-footer">'
        f'{name}{batch}{expiry_line}'
        f'</div>'
        f'</div>'
    )


def _html_patient_sticker(
    label: dict[str, Any],
    bands: StickerBands,
    fonts: dict[str, float],
    dpi: int = DEFAULT_LABEL_DPI,
) -> str:
    mrn = (label.get("mrn") or "").strip()
    barcode_value = mrn or (label.get("mrn_ean13") or "").strip()
    bar = ""
    if barcode_value:
        bar = _html_barcode_block(
            barcode_value,
            max_width_mm=bands.inner_w_mm,
            max_height_mm=bands.barcode_mm,
            force_code128=True,
            dpi=dpi,
        )
    lines: List[str] = []
    for kind, left, _right in patient_body_rows(label):
        if kind == "name":
            lines.append(_html_sized("name", left, fonts["name_pt"], bands.inner_w_mm, bold=True))
        else:
            lines.append(_html_sized("meta", left, fonts["meta_pt"], bands.inner_w_mm))
    return (
        f'<div class="sticker patient">'
        f'{bar}'
        f'<div class="zone-footer">{"".join(lines)}</div>'
        f'</div>'
    )


def _html_test_sticker(layout: LabelLayoutConfig, bands: StickerBands) -> str:
    bar = _html_barcode_block(
        TEST_LABEL_BARCODE,
        max_width_mm=bands.inner_w_mm,
        max_height_mm=bands.barcode_mm,
        force_code128=True,
        dpi=layout.dpi,
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

    kind, bands, body_lines = _html_layout_for(
        layout, label_type, work, pharmacy_display_name,
    )
    fonts = _html_fonts(kind, bands, body_lines)
    stickers: List[str] = []
    for label in work:
        if label_type == "lab_sample":
            stickers.append(_html_lab_sticker(label, layout, lab_display_name, bands, fonts))
        elif label_type == "patient_file":
            stickers.append(_html_patient_sticker(label, bands, fonts, layout.dpi))
        elif label_type == "test":
            stickers.append(_html_test_sticker(layout, bands))
        else:
            stickers.append(_html_pharmacy_sticker(label, layout, pharmacy_display_name, bands, fonts))

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
    padding: {bands.pad_y_mm:.3f}mm {bands.pad_x_mm:.3f}mm;
    overflow: hidden;
    page-break-inside: avoid;
    display: flex;
    flex-direction: column;
    gap: {bands.gap_mm:.3f}mm;
  }}
  .zone-header {{
    height: {bands.header_mm:.3f}mm;
    display: flex;
    flex-direction: column;
    justify-content: center;
    min-height: 0;
  }}
  .zone-footer {{
    height: {bands.footer_mm:.3f}mm;
    display: flex;
    flex-direction: column;
    justify-content: space-evenly;
    min-height: 0;
  }}
  .row, .pair {{ display: flex; align-items: center; width: 100%; min-width: 0; }}
  .row .l, .pair .l {{ width: 60%; min-width: 0; }}
  .row .r, .pair .r {{ width: 36%; margin-left: 4%; text-align: right; min-width: 0; }}
  .name {{ font-size: {fonts["name_pt"]:.2f}pt; font-weight: 700; line-height: 1; white-space: nowrap; overflow: hidden; }}
  .provider {{ font-size: {fonts["header_pt"]:.2f}pt; font-weight: 700; text-align: center; line-height: 1; white-space: nowrap; overflow: hidden; }}
  .meta {{ font-size: {fonts["meta_pt"]:.2f}pt; line-height: 1; white-space: nowrap; overflow: hidden; }}
  .barcode {{
    display: flex;
    flex-direction: column;
    justify-content: center;
    min-height: 0;
    overflow: hidden;
  }}
  .barcode .bars {{ width: 100%; }}
  .barcode svg {{ width: 100%; height: 100%; display: block; shape-rendering: crispEdges; }}
  .digits {{
    font-size: {fonts["digit_pt"]:.2f}pt;
    letter-spacing: 0.02em;
    text-align: center;
    line-height: 1;
    white-space: nowrap;
    overflow: hidden;
  }}
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
