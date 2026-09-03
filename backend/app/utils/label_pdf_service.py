"""Thermal / Avery label PDF generation (non-A4 page sizes)."""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any, List, Optional

from reportlab.graphics.barcode import eanbc
from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.services.barcode_service import validate_ean13
from app.utils.pdf_settings import apply_thermal_roll_layout

# Pharmacy label layout ratios (retail-style: header / barcode / footer).
PHARMACY_SIDE_MARGIN_RATIO = 0.01
PHARMACY_HEADER_RATIO = 0.10
PHARMACY_BARCODE_WIDTH_RATIO = 0.50
PHARMACY_BARCODE_HEIGHT_RATIO = 0.45  # max barcode block height vs label
PHARMACY_DETAIL_ZONE_RATIO = 0.28
PHARMACY_ZONE_GAP = 0.5 * mm
PHARMACY_HEADER_MIN_MM = 4.0
PHARMACY_FOOTER_MIN_MM = 7.2


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


def _ean13_size(
    code: str,
    max_width: float,
    height: float,
    *,
    bars_only: bool = False,
) -> tuple[float, float]:
    widget = eanbc.Ean13BarcodeWidget(code[:13])
    if bars_only:
        widget.humanReadable = 0
        widget.barHeight = max(1.0, height * 0.92)
    bounds = widget.getBounds()
    bw = max(bounds[2] - bounds[0], 1)
    bh = max(bounds[3] - bounds[1], 1)
    scale = min(max_width / bw, height / bh)
    return bw * scale, bh * scale


def _draw_pharmacy_ean13(
    c: canvas.Canvas,
    code: str,
    center_x: float,
    zone_bottom: float,
    zone_width: float,
    zone_height: float,
) -> None:
    """Draw scannable EAN-13 bars centered in a zone; digits sit below bars inside the zone."""
    if not code or not validate_ean13(code) or zone_height < 2.0 * mm:
        return
    digit_pt = max(3.2, min(4.5, (zone_height / mm) * 1.15))
    digit_band = _pt_to_mm(digit_pt) * 1.35 + 0.4 * mm
    bars_zone_h = max(1.0, zone_height - digit_band)
    max_bar_w = zone_width * PHARMACY_BARCODE_WIDTH_RATIO
    widget = eanbc.Ean13BarcodeWidget(code[:13])
    widget.humanReadable = 0
    widget.barHeight = bars_zone_h * 0.92
    bounds = widget.getBounds()
    bw = max(bounds[2] - bounds[0], 1)
    bh = max(bounds[3] - bounds[1], 1)
    scale = min(max_bar_w / bw, bars_zone_h / bh)
    widget.barHeight = widget.barHeight * scale
    bounds = widget.getBounds()
    dw = bounds[2] - bounds[0]
    dh = bounds[3] - bounds[1]
    bar_x = center_x - dw / 2
    bar_y = zone_bottom + digit_band + max(0.0, (bars_zone_h - dh) / 2)
    drawing = Drawing(dw, dh)
    drawing.add(widget)
    renderPDF.draw(drawing, c, bar_x, bar_y)
    c.setFont("Helvetica", digit_pt)
    c.drawCentredString(center_x, zone_bottom + 0.25 * mm, code[:13])


def _draw_ean13(
    c: canvas.Canvas,
    code: str,
    x: float,
    y: float,
    max_width: float,
    height: float,
    *,
    area_width: Optional[float] = None,
    align: str = "left",
) -> None:
    if not code or not validate_ean13(code):
        return
    dw, dh = _ean13_size(code, max_width, height)
    widget = eanbc.Ean13BarcodeWidget(code[:13])
    drawing = Drawing(dw, dh)
    drawing.add(widget)
    draw_x = x
    if align == "center" and area_width is not None:
        draw_x = x + max(0.0, (area_width - dw) / 2)
    renderPDF.draw(drawing, c, draw_x, y)


def _draw_lab_label(
    c: canvas.Canvas,
    layout: LabelLayoutConfig,
    x0: float,
    y0: float,
    label: dict[str, Any],
    lab_display_name: str,
) -> None:
    w = layout.width_mm * mm
    h = layout.height_mm * mm
    pad = 1.5 * mm
    left_w = w * 0.62
    right_w = w - left_w - pad

    patient_name = _truncate(label.get("patient_name") or "", 28)
    sample_id = label.get("sample_id") or ""
    mrn = label.get("mrn") or ""
    sample_ean = label.get("sample_ean13") or ""
    mrn_ean = label.get("mrn_ean13") or ""

    c.setFont("Helvetica-Bold", 7)
    c.drawString(x0 + pad, y0 + h - pad - 6, patient_name)

    c.setFont("Helvetica", 6)
    c.drawString(x0 + pad, y0 + h - pad - 14, f"Sample: {sample_id}")
    if mrn:
        c.drawString(x0 + pad, y0 + pad + 2, f"MRN: {mrn}")

    if layout.show_lab_name:
        c.setFont("Helvetica-Bold", 6)
        lab_name = _truncate(
            layout.lab_name_override or lab_display_name or "Laboratory",
            18,
        )
        c.drawRightString(x0 + w - pad, y0 + h - pad - 8, lab_name)

    bar_y = y0 + pad + 8
    bar_h = 8 * mm
    bar_w = (left_w - 2 * pad) / 2 - 1 * mm
    if sample_ean:
        _draw_ean13(c, sample_ean, x0 + pad, bar_y, bar_w, bar_h)
    if mrn_ean:
        _draw_ean13(c, mrn_ean, x0 + pad + bar_w + 2 * mm, bar_y, bar_w, bar_h)


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
    bar_zone_bottom = footer_top + PHARMACY_ZONE_GAP
    bar_zone_top = header_bottom - PHARMACY_ZONE_GAP
    bar_zone_h = max(0.0, bar_zone_top - bar_zone_bottom)

    ref_h = layout.height_mm * mm
    scale = footer_h / (ref_h * PHARMACY_DETAIL_ZONE_RATIO) if ref_h > 0 else 1.0
    name_pt = max(4.0, min(6.0, 5.0 * scale))
    detail_pt = max(3.8, min(5.5, 4.8 * scale))
    header_pt = max(3.5, min(6.0, (header_h / mm) * 1.55))
    line_gap = max(1.6 * mm, min(2.4 * mm, footer_h * 0.22))
    descender_mm = _pt_to_mm(detail_pt * 0.28)

    expiry_y = iy + descender_mm
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
        _draw_pharmacy_ean13(
            c,
            barcode,
            ix + iw / 2,
            bar_zone_bottom,
            iw,
            bar_zone_h,
        )

    if provider_fit:
        header_mid = iy + ih - header_h / 2
        header_baseline = header_mid - _pt_to_mm(provider_pt) * 0.32
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


def _label_positions(layout: LabelLayoutConfig) -> List[tuple[float, float]]:
    positions: List[tuple[float, float]] = []
    lw = layout.width_mm * mm
    lh = layout.height_mm * mm
    gx = layout.gutter_mm * mm
    gy = layout.gutter_mm * mm

    if layout.sheet_mode == "thermal":
        # Page size equals one label; margins are content inset (see _content_rect).
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
    if not labels:
        raise ValueError("No labels to print")

    buf = io.BytesIO()
    page_w, page_h = _page_size(layout)
    slots = _label_positions(layout)
    slots_per_page = len(slots)

    c = canvas.Canvas(buf, pagesize=(page_w, page_h))

    for idx, label in enumerate(labels):
        if idx > 0 and idx % slots_per_page == 0:
            c.showPage()
        slot_idx = idx % slots_per_page
        x0, y0 = slots[slot_idx]
        if label_type == "lab_sample":
            _draw_lab_label(c, layout, x0, y0, label, lab_display_name)
        else:
            _draw_pharmacy_label(c, layout, x0, y0, label, pharmacy_display_name)

    c.save()
    return buf.getvalue()
