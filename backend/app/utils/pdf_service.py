from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, HRFlowable, XPreformatted
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from io import BytesIO
from datetime import datetime
from typing import Optional
import json
import os

from app.utils.patient_age import age_display_from_data

DEFAULT_LETTERHEAD_GAP_PT = 100.0


def _to_system_local(val):
    """Parse/normalize a datetime to naive system-local wall clock."""
    if val is None or val == "":
        return None
    if isinstance(val, str):
        val = datetime.fromisoformat(val.replace("Z", "+00:00"))
    if getattr(val, "tzinfo", None) is not None:
        val = val.astimezone().replace(tzinfo=None)
    return val


def _fmt_system_dt(val, fmt="%d/%m/%Y %I:%M %p", empty="-"):
    """Format a date/datetime for PDF display in system local time."""
    if not val:
        return empty
    try:
        return _to_system_local(val).strftime(fmt)
    except Exception:
        return str(val)


def _age_gender_str(data: dict, *, gender: str = "", age_key: str = "patient_age") -> str:
    """Build 'Age / Gender' display line for PDF headers."""
    age_display = age_display_from_data(data, age_key=age_key)
    gender = gender or data.get("patient_gender") or data.get("gender") or ""
    if gender:
        g = str(gender).upper() if len(str(gender)) <= 3 else str(gender).capitalize()
        if age_display:
            return f"{age_display} / {g}"
        return g
    return age_display


def _get_uploads_base():
    """Get the uploads directory path. Works in both dev and bundled (.exe) mode."""
    try:
        from app.utils.paths import get_uploads_dir
        return get_uploads_dir()
    except Exception:
        return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")


def _load_seller_info_safe():
    """Best-effort fetch of seller_info from the License table.

    Used as a fallback when callers don't pass seller_info via hospital_info.
    Failures are swallowed — the footer simply falls back to the generic line.
    """
    try:
        from app.config.database import SessionLocal
        from app.models.license import License
        db = SessionLocal()
        try:
            lic = db.query(License).order_by(License.id.desc()).first()
            return lic.seller_info if (lic and lic.seller_info) else None
        finally:
            db.close()
    except Exception:
        return None


def _draw_footer(canvas_obj, doc, seller_info=None):
    """Draws the standard footer line on every page.

    "Powered by KT HEALTH ERP — Sold by {vendor}" when a seller_info dict
    with a non-empty name is supplied; otherwise the generic
    "Developed by KT Health Soft" line.
    """
    try:
        if seller_info and seller_info.get('name'):
            text = f"Powered by KT HEALTH ERP — Sold by {seller_info['name']}"
        else:
            text = "Developed by KT Health Soft"
        canvas_obj.saveState()
        canvas_obj.setFont('Helvetica', 7)
        canvas_obj.setFillGray(0.4)
        page_width = doc.pagesize[0] if hasattr(doc, 'pagesize') else A4[0]
        canvas_obj.drawCentredString(page_width / 2, 12, text)
        canvas_obj.restoreState()
    except Exception:
        pass


def _draw_watermark(canvas_obj, doc, text):
    """Draws a large semi-transparent diagonal watermark across the page."""
    if not text:
        return
    try:
        canvas_obj.saveState()
        page_w = doc.pagesize[0] if hasattr(doc, 'pagesize') else A4[0]
        page_h = doc.pagesize[1] if hasattr(doc, 'pagesize') else A4[1]
        canvas_obj.translate(page_w / 2, page_h / 2)
        canvas_obj.rotate(35)
        canvas_obj.setFont('Helvetica-Bold', 90)
        try:
            canvas_obj.setFillAlpha(0.18)
        except Exception:
            canvas_obj.setFillGray(0.85)
        canvas_obj.setFillColorRGB(0.85, 0.15, 0.15)
        canvas_obj.drawCentredString(0, 0, text.upper())
        canvas_obj.restoreState()
    except Exception:
        pass


def _make_page_callback(seller_info, header_cb=None, watermark=None):
    """Returns a SimpleDocTemplate onPage callback chaining the optional
    header callback, watermark, then the footer."""
    def _cb(canvas_obj, doc):
        if watermark:
            _draw_watermark(canvas_obj, doc, watermark)
        if header_cb is not None:
            try:
                header_cb(canvas_obj, doc)
            except Exception:
                pass
        _draw_footer(canvas_obj, doc, seller_info)
    return _cb


def _patient_address_line(data):
    """Return a "village, district" string from a data dict, skipping empties.

    Used to populate a one-line address row in every patient-facing PDF's info
    box. Looks at the top level of the dict first and falls back to a nested
    "patient" sub-dict (the inpatient PDFs use that shape).
    """
    if not isinstance(data, dict):
        return ''
    village = (data.get('village') or '').strip()
    mandal = (data.get('mandal') or '').strip()
    district = (data.get('district') or '').strip()
    if not village and not mandal and not district:
        nested = data.get('patient')
        if isinstance(nested, dict):
            village = (nested.get('village') or '').strip()
            mandal = (nested.get('mandal') or '').strip()
            district = (nested.get('district') or '').strip()
    parts = [p for p in (village, mandal, district) if p]
    return ', '.join(parts)


def _append_address_row(info_data, style_list, data, lv):
    """Append a SPAN'd 'Address' row to a patient info table when the data
    dict carries village/district. Mutates info_data and style_list in place;
    no-op when no address info is present. Use after building the rest of
    the info_data list and the base style list, before constructing the Table.
    """
    addr = (data.get('address_line') or '').strip() or _patient_address_line(data)
    if not addr:
        return
    row_idx = len(info_data)
    info_data.append([lv('Address', addr), ''])
    style_list.append(('SPAN', (0, row_idx), (1, row_idx)))


def _discharge_type_label(dtype: str) -> str:
    labels = {
        'normal': 'Normal Discharge',
        'against_advice': 'Against Medical Advice',
        'transfer': 'Transfer',
        'death': 'Death',
    }
    return labels.get((dtype or '').lower(), (dtype or '').replace('_', ' ').title())


def _med_route_display(m: dict) -> str:
    return str(m.get('route') or 'Per Oral')


def _med_timings_display(m: dict) -> str:
    sched = str(m.get('frequency_schedule') or '').strip()
    if sched and '-' in sched:
        parts = sched.split('-')
        if len(parts) == 3:
            labels = []
            if parts[0] == '1':
                labels.append('Morning')
            if parts[1] == '1':
                labels.append('Afternoon')
            if parts[2] == '1':
                labels.append('Night')
            if labels:
                food = m.get('food_timing') or ''
                food_map = {
                    'before_food': 'before food',
                    'after_food': 'after food',
                    'with_food': 'with food',
                    'on_empty_stomach': 'empty stomach',
                    'anytime': 'anytime',
                }
                food_label = food_map.get(food, '')
                base = ', '.join(labels)
                return f"{base} ({food_label})" if food_label else base
    freq = str(m.get('frequency') or '').strip()
    return freq or '—'


def _discharge_running_header(canvas_obj, doc, patient_label: str):
    """Patient name + admission number on every page (top-right)."""
    if not patient_label:
        return
    try:
        canvas_obj.saveState()
        canvas_obj.setFont('Helvetica-Bold', 8)
        page_w = doc.pagesize[0] if hasattr(doc, 'pagesize') else A4[0]
        page_h = doc.pagesize[1] if hasattr(doc, 'pagesize') else A4[1]
        canvas_obj.drawRightString(page_w - 30, page_h - 18, patient_label)
        canvas_obj.restoreState()
    except Exception:
        pass


def _resolve_seller(hospital_info):
    """Extract seller_info from hospital_info dict (preferred) or fall back
    to a one-shot DB lookup."""
    if isinstance(hospital_info, dict):
        si = hospital_info.get('seller_info')
        if si:
            return si
    return _load_seller_info_safe()


def _finalize(doc, elements, hospital_info, header_cb=None, watermark=None):
    """Build the PDF with the footer (and optional header) wired in.

    Use this in place of `doc.build(elements)` so every generated PDF
    carries the consistent vendor footer. ``watermark`` (e.g. ``"CANCELLED"``,
    ``"INTERIM"``) renders a diagonal stamp behind the content.
    """
    seller_info = _resolve_seller(hospital_info)
    cb = _make_page_callback(seller_info, header_cb, watermark)
    doc.build(elements, onFirstPage=cb, onLaterPages=cb)


def _escape_pdf_inline(s):
    if not s:
        return ''
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _lab_results_show_notes_column(results_list):
    return any((r.get('notes') or '').strip() for r in (results_list or []))


def _lab_results_show_method_column(results_list):
    return any((r.get('method') or '').strip() for r in (results_list or []))


def _format_lab_result_with_unit(value, unit):
    raw = str(value or '').strip()
    unit_text = (unit or '').strip()
    if not raw:
        return '-'
    if unit_text:
        return f"{raw} {_escape_pdf_inline(unit_text)}"
    return raw


def _format_lab_parameter_cell(parameter_name, remarks=''):
    """Parameter name with optional technician remarks on the next line."""
    param_text = _escape_pdf_inline(parameter_name or '')
    if remarks:
        param_text = (
            f"{param_text}<br/><i><font size='7' color='grey'>"
            f"{_escape_pdf_inline(remarks)}</font></i>"
        )
    return param_text


def _build_lab_results_table(results_list, *, page_width, cell_label, cell_value, cell_abnormal, section_label_style, cell_ref_range=None):
    """Build a lab results table. Adds METHOD/NOTES columns when any parameter has them."""
    ref_cell_style = cell_ref_range or cell_value
    show_method = _lab_results_show_method_column(results_list)
    show_notes = _lab_results_show_notes_column(results_list)

    if show_method and show_notes:
        col_widths = [
            page_width * 0.24,
            page_width * 0.18,
            page_width * 0.28,
            page_width * 0.15,
            page_width * 0.15,
        ]
        header = [
            Paragraph('<b>PARAMETER</b>', cell_label),
            Paragraph('<b>RESULT</b>', cell_label),
            Paragraph('<b>BIO. REF. RANGE</b>', cell_label),
            Paragraph('<b>METHOD</b>', cell_label),
            Paragraph('<b>NOTES</b>', cell_label),
        ]
    elif show_method:
        col_widths = [
            page_width * 0.28,
            page_width * 0.22,
            page_width * 0.35,
            page_width * 0.15,
        ]
        header = [
            Paragraph('<b>PARAMETER</b>', cell_label),
            Paragraph('<b>RESULT</b>', cell_label),
            Paragraph('<b>BIO. REF. RANGE</b>', cell_label),
            Paragraph('<b>METHOD</b>', cell_label),
        ]
    elif show_notes:
        col_widths = [
            page_width * 0.30,
            page_width * 0.22,
            page_width * 0.28,
            page_width * 0.20,
        ]
        header = [
            Paragraph('<b>PARAMETER</b>', cell_label),
            Paragraph('<b>RESULT</b>', cell_label),
            Paragraph('<b>BIO. REF. RANGE</b>', cell_label),
            Paragraph('<b>NOTES</b>', cell_label),
        ]
    else:
        col_widths = [
            page_width * 0.32,
            page_width * 0.28,
            page_width * 0.40,
        ]
        header = [
            Paragraph('<b>PARAMETER</b>', cell_label),
            Paragraph('<b>RESULT</b>', cell_label),
            Paragraph('<b>BIO. REF. RANGE</b>', cell_label),
        ]

    results_data = [header]
    section_row_indices = []
    current_section = None
    empty_cell = Paragraph('', cell_value)

    for r in results_list or []:
        section = r.get('section', '')
        if section and section != current_section:
            current_section = section
            section_row_indices.append(len(results_data))
            row = [Paragraph(f'<b>{section}</b>', section_label_style)]
            row.extend([empty_cell] * (len(col_widths) - 1))
            results_data.append(row)
        elif not section and current_section is not None:
            current_section = None

        is_abnormal = r.get('is_abnormal', False)
        value_style = cell_abnormal if is_abnormal else cell_value

        ref_range = '-'
        ref_display = (r.get('reference_range_display') or '').strip()
        if ref_display:
            ref_range = ref_display
            ref_style = ref_cell_style if '<br/>' in ref_display else cell_value
        else:
            ref_style = cell_value
            ref_min = r.get('reference_min')
            ref_max = r.get('reference_max')
            normal_val = r.get('normal_value')
            if ref_min is not None and ref_max is not None:
                ref_range = f"{ref_min} - {ref_max}"
            elif ref_min is not None:
                ref_range = f"&gt; {ref_min}"
            elif ref_max is not None:
                ref_range = f"&lt; {ref_max}"
            elif normal_val:
                ref_range = normal_val

        param_text = _format_lab_parameter_cell(
            r.get('parameter_name', ''),
            r.get('remarks', ''),
        )
        result_text = _format_lab_result_with_unit(r.get('value', ''), r.get('unit', ''))
        row = [
            Paragraph(param_text, cell_value),
            Paragraph(result_text, value_style),
            Paragraph(ref_range, ref_style),
        ]
        if show_method:
            method_text = (r.get('method') or '').strip()
            row.append(Paragraph(_escape_pdf_inline(method_text) if method_text else '-', cell_value))
        if show_notes:
            notes_text = (r.get('notes') or '').strip()
            row.append(Paragraph(_escape_pdf_inline(notes_text) if notes_text else '-', cell_value))

        results_data.append(row)

    table_style_cmds = [
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
    ]
    for sec_row in section_row_indices:
        table_style_cmds.append(('SPAN', (0, sec_row), (-1, sec_row)))
        table_style_cmds.append(('FONTNAME', (0, sec_row), (-1, sec_row), 'Helvetica-Bold'))
        table_style_cmds.append(('TOPPADDING', (0, sec_row), (-1, sec_row), 5))
        table_style_cmds.append(('BOTTOMPADDING', (0, sec_row), (-1, sec_row), 5))

    results_table = Table(results_data, colWidths=col_widths)
    results_table.setStyle(TableStyle(table_style_cmds))
    return results_table


class PDFService:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.setup_custom_styles()
    
    def setup_custom_styles(self):
        """Setup custom paragraph styles"""
        self.styles.add(ParagraphStyle(
            'CustomTitle',
            parent=self.styles['Title'],
            fontSize=20,
            spaceAfter=20,
            alignment=1,  # Center alignment
            textColor=colors.darkblue
        ))
        
        self.styles.add(ParagraphStyle(
            'CustomHeading',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceAfter=10,
            textColor=colors.darkblue,
            borderWidth=1,
            borderColor=colors.darkblue,
            borderPadding=5,
            backColor=colors.lightblue
        ))
        
        self.styles.add(ParagraphStyle(
            'InfoText',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=6,
            textColor=colors.darkgrey
        ))

    def generate_inpatient_bill_pdf(self, bill_data, hospital_info, include_header=True, letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT, detailed_billing=True):
        """Inpatient bill — mirrors the OPD receipt layout so both bills feel
        consistent. Adds an Admission Details box for IP-specific fields, and
        the Payment Summary lists every deposit received before the balance.

        Expected `bill_data` keys:
          - bill_number, bill_date, status, bill_subtype
          - patient: {name, mrn, patient_id, age, gender, phone, address, referred_by}
          - admission: {admission_number, ward, room_number, bed_label,
                        admitted_at, discharged_at, length_of_stay, payer,
                        payer_status, scheme_member_id,
                        admitting_doctor, attending_doctor, referring_doctor}
          - items: [{description, code, qty, rate, amount}]
          - subtotal, discount, tax, total
          - deposits: [{date, method, reference, amount}]   (each receipt)
          - deposits_total, balance_due
          - prepared_by_name
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=20,
        )
        elements = []
        page_width = A4[0] - 60

        # --- Styles (black & white to match OPD bill) ---
        title_style = ParagraphStyle('BillTitle', parent=self.styles['Title'],
            fontSize=16, alignment=1, fontName='Helvetica-Bold',
            textColor=colors.black, spaceAfter=2)
        subtitle_style = ParagraphStyle('BillSubtitle', parent=self.styles['Normal'],
            fontSize=9, alignment=1, fontName='Helvetica',
            textColor=colors.black, spaceAfter=2)
        receipt_title_style = ParagraphStyle('ReceiptTitle', parent=self.styles['Normal'],
            fontSize=12, alignment=1, fontName='Helvetica-Bold',
            textColor=colors.black, spaceAfter=4)
        cell_label = ParagraphStyle('CellLabel', parent=self.styles['Normal'],
            fontSize=8, fontName='Helvetica-Bold', textColor=colors.black)
        cell_value = ParagraphStyle('CellValue', parent=self.styles['Normal'],
            fontSize=8, fontName='Helvetica', textColor=colors.black)
        cell_value_sm = ParagraphStyle('CellValueSm', parent=self.styles['Normal'],
            fontSize=7, fontName='Helvetica', textColor=colors.black)
        cell_value_right = ParagraphStyle('CellValueRight', parent=cell_value_sm, alignment=2)

        def lv(label, value):
            return Paragraph(f"<b>{label}</b> :  {value}",
                             ParagraphStyle('LV', parent=cell_value, leading=11))

        def lv_sm(label, value):
            return Paragraph(f"<b>{label}</b> :  {value}", cell_value_sm)

        # --- Parse dates ---
        try:
            bd = datetime.fromisoformat(bill_data.get('bill_date', ''))
            bill_date_str = bd.strftime('%d/%m/%Y')
        except Exception:
            bill_date_str = bill_data.get('bill_date') or datetime.now().strftime('%d/%m/%Y')

        # ============================================================
        # HEADER — identical pattern to OPD generate_bill_pdf
        # ============================================================
        if include_header:
            logo_path = hospital_info.get('logo_url', '')
            uploads_base = _get_uploads_base()
            has_logo = False
            full_logo_path = ''
            if logo_path:
                relative = logo_path.lstrip('/')
                if relative.startswith('uploads/'):
                    relative = relative[len('uploads/'):]
                full_logo_path = os.path.join(uploads_base, relative)
                has_logo = os.path.exists(full_logo_path)

            hospital_name = hospital_info.get('name', 'HOSPITAL').upper()
            hospital_subname = hospital_info.get('hospital_subname', '')
            address = hospital_info.get('address', '')
            contact_parts = []
            if hospital_info.get('email'):
                contact_parts.append(f"Email: {hospital_info['email']}")
            if hospital_info.get('phone'):
                contact_parts.append(f"Phone: {hospital_info['phone']}")

            header_text_elems = [Paragraph(hospital_name, title_style)]
            if hospital_subname:
                header_text_elems.append(Paragraph(hospital_subname, subtitle_style))
            if address:
                header_text_elems.append(Paragraph(address, subtitle_style))
            if contact_parts:
                header_text_elems.append(Paragraph("  |  ".join(contact_parts), subtitle_style))

            if has_logo:
                try:
                    logo_img = Image(full_logo_path, width=60, height=60)
                    logo_img.hAlign = 'CENTER'
                    header_table = Table(
                        [[logo_img, header_text_elems]],
                        colWidths=[75, page_width - 75],
                    )
                    header_table.setStyle(TableStyle([
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 0),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                        ('TOPPADDING', (0, 0), (-1, -1), 0),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                    ]))
                    elements.append(header_table)
                except Exception:
                    for el in header_text_elems:
                        elements.append(el)
            else:
                for el in header_text_elems:
                    elements.append(el)

            elements.append(Spacer(1, 6))
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        else:
            elements.append(Spacer(1, letterhead_gap_pt))

        elements.append(Spacer(1, 4))
        bill_subtype = (bill_data.get('bill_subtype') or 'final').upper()
        elements.append(Paragraph(f"INPATIENT BILL — {bill_subtype}", receipt_title_style))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        elements.append(Spacer(1, 6))

        # ============================================================
        # PATIENT INFO BOX (left) + BILL INFO (right) — bordered
        # ============================================================
        p = bill_data.get('patient') or {}
        a = bill_data.get('admission') or {}
        age_sex = _age_gender_str(p, gender=p.get('gender'))

        ref_value = (a.get('referring_doctor')
                     or p.get('referred_by')
                     or 'Self')
        payer_str = a.get('payer') or 'Cash'
        if a.get('payer_status') and a.get('payer_status') != 'none':
            payer_str = f"{payer_str} ({a['payer_status']})"

        col_w = page_width / 2
        info_data = [
            [lv('Name', p.get('name', '')),                 lv('Bill No',    bill_data.get('bill_number', ''))],
            [lv('Age / Gender', age_sex),                   lv('Bill Date',  bill_date_str)],
            [lv('Phone', p.get('phone', '')),               lv('Address', _patient_address_line(bill_data))],
            [lv('MRN',   p.get('mrn', '')),
             lv('Pay Mode',   payer_str)],
            [lv('Referred By', ref_value),                  Paragraph('', cell_value)],
        ]
        info_style = [
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ]
        info_table = Table(info_data, colWidths=[col_w, col_w])
        info_table.setStyle(TableStyle(info_style))
        elements.append(info_table)
        elements.append(Spacer(1, 6))

        # ============================================================
        # ADMISSION INFO BOX (inpatient-specific)
        # ============================================================
        ward_room_bed = ' / '.join(filter(None, [
            a.get('ward'), a.get('room_number'), a.get('bed_label')
        ])) or '—'
        doctors_line = ' / '.join(filter(None, [
            a.get('admitting_doctor'), a.get('attending_doctor')
        ])) or '—'

        adm_data = [
            [lv('Admission No', a.get('admission_number', '')),
             lv('Ward / Room / Bed', ward_room_bed)],
            [lv('Admitted', a.get('admitted_at') or '—'),
             lv('Discharged', a.get('discharged_at') or '—')],
            [lv('Length of Stay', f"{a.get('length_of_stay') or 0} day(s)"),
             lv('Admitting / Attending', doctors_line)],
        ]
        if a.get('payer') and a.get('scheme_member_id'):
            adm_data.append([
                lv('Scheme Member ID', a.get('scheme_member_id')),
                Paragraph('', cell_value),
            ])
        adm_table = Table(adm_data, colWidths=[col_w, col_w])
        adm_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(adm_table)
        elements.append(Spacer(1, 6))

        # ============================================================
        # ITEMS TABLE — Sno | Description | Qty | Rate | Amount
        # ============================================================
        sno_w = 0.4 * inch
        qty_w = 0.7 * inch
        rate_w = 1.0 * inch
        amt_w = 1.1 * inch
        desc_w = page_width - sno_w - qty_w - rate_w - amt_w

        items_header = [
            Paragraph('<b>Sno</b>', cell_label),
            Paragraph('<b>Description</b>', cell_label),
            Paragraph('<b>Qty</b>', ParagraphStyle('Qc', parent=cell_label, alignment=1)),
            Paragraph('<b>Rate</b>', ParagraphStyle('Rr', parent=cell_label, alignment=2)),
            Paragraph('<b>Amount</b>', ParagraphStyle('Ra', parent=cell_label, alignment=2)),
        ]
        items_data = [items_header]
        items = bill_data.get('items') or []
        for idx, it in enumerate(items, start=1):
            rate_val = it.get('rate')
            try:
                rate_str = f"{float(rate_val):,.2f}" if rate_val not in (None, "") else "—"
            except (TypeError, ValueError):
                rate_str = "—"
            items_data.append([
                Paragraph(str(idx), cell_value),
                Paragraph(it.get('description', ''), cell_value),
                Paragraph(str(it.get('qty', '')) or '—',
                    ParagraphStyle('Qc', parent=cell_value, alignment=1)),
                Paragraph(
                    rate_str,
                    ParagraphStyle('Rr', parent=cell_value, alignment=2),
                ),
                Paragraph(
                    f"{float(it.get('amount') or 0):,.2f}",
                    ParagraphStyle('Ra', parent=cell_value, alignment=2),
                ),
            ])
        if len(items_data) == 1:
            items_data.append([
                Paragraph('—', cell_value),
                Paragraph('No itemised charges', cell_value),
                Paragraph('—', cell_value),
                Paragraph('—',
                    ParagraphStyle('Rr', parent=cell_value, alignment=2)),
                Paragraph('0.00',
                    ParagraphStyle('Ra', parent=cell_value, alignment=2)),
            ])
        items_table = Table(items_data, colWidths=[sno_w, desc_w, qty_w, rate_w, amt_w])
        items_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
        ]))
        elements.append(items_table)
        elements.append(Spacer(1, 6))

        # ============================================================
        # DEPOSITS — itemised receipts before the payment summary
        # ============================================================
        deposits = bill_data.get('deposits') or []
        if deposits:
            elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
            elements.append(Spacer(1, 2))
            elements.append(Paragraph("<b>Deposits / Payments Received</b>", cell_label))
            elements.append(Spacer(1, 2))
            dep_header = [
                Paragraph('<b>Sno</b>', cell_label),
                Paragraph('<b>Receipt No</b>', cell_label),
                Paragraph('<b>Date</b>', cell_label),
                Paragraph('<b>Type</b>', cell_label),
                Paragraph('<b>Method</b>', cell_label),
                Paragraph('<b>Reference</b>', cell_label),
                Paragraph('<b>Amount</b>',
                    ParagraphStyle('R', parent=cell_label, alignment=2)),
            ]
            dep_rows = [dep_header]
            for idx, d in enumerate(deposits, start=1):
                amt = float(d.get('amount') or 0)
                is_refund = (d.get('deposit_type') == 'refund') or amt < 0
                amt_str = f"({abs(amt):,.2f})" if is_refund else f"{amt:,.2f}"
                dep_rows.append([
                    Paragraph(str(idx), cell_value),
                    Paragraph(d.get('deposit_number') or '—', cell_value),
                    Paragraph(d.get('date') or '—', cell_value),
                    Paragraph(str(d.get('deposit_type') or 'initial').replace('_', ' ').title(), cell_value),
                    Paragraph(str(d.get('method') or '—').title(), cell_value),
                    Paragraph(d.get('reference') or '—', cell_value),
                    Paragraph(amt_str,
                        ParagraphStyle('R', parent=cell_value, alignment=2)),
                ])
            ref_w = 0.8 * inch
            type_w = 0.65 * inch
            date_w = 1.1 * inch
            dep_table = Table(
                dep_rows,
                colWidths=[sno_w, 1.1 * inch, date_w, type_w,
                           0.75 * inch,
                           page_width - sno_w - 1.1 * inch - date_w - type_w - 0.75 * inch - rate_w,
                           rate_w],
            )
            dep_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.black),
            ]))
            elements.append(dep_table)
            elements.append(Spacer(1, 6))

        # ============================================================
        # PAYMENT SUMMARY — same column geometry as OPD
        # ============================================================
        subtotal = float(bill_data.get('subtotal') or 0)
        discount = float(bill_data.get('discount') or 0)
        tax = float(bill_data.get('tax') or 0)
        total = float(bill_data.get('total') or (subtotal - discount + tax))
        deposits_total = float(bill_data.get('deposits_total') or 0)
        balance = float(bill_data.get('balance_due')
                        if bill_data.get('balance_due') is not None
                        else (total - deposits_total))

        summary_label_w = page_width - qty_w - amt_w
        # When neither a discount nor a tax row is shown, the Sub Total + Total
        # rows are redundant — collapse them into a single "Bill Total" line.
        has_adjustments = discount > 0 or tax > 0
        payment_data = []
        if has_adjustments:
            payment_data.append([
                lv_sm('Paymode', payer_str),
                Paragraph('<b>Sub Total</b>', cell_value_sm),
                Paragraph(f"{subtotal:,.2f}", cell_value_right),
            ])
            if discount > 0:
                payment_data.append([
                    Paragraph('', cell_value_sm),
                    Paragraph('<b>Discount</b>', cell_value_sm),
                    Paragraph(f"- {discount:,.2f}", cell_value_right),
                ])
            if tax > 0:
                payment_data.append([
                    Paragraph('', cell_value_sm),
                    Paragraph('<b>Tax</b>', cell_value_sm),
                    Paragraph(f"+ {tax:,.2f}", cell_value_right),
                ])
            payment_data.append([
                Paragraph('', cell_value_sm),
                Paragraph('<b>Total Amt</b>', cell_value_sm),
                Paragraph(f"{total:,.2f}", cell_value_right),
            ])
        else:
            payment_data.append([
                lv_sm('Paymode', payer_str),
                Paragraph('<b>Bill Total</b>', cell_value_sm),
                Paragraph(f"{total:,.2f}", cell_value_right),
            ])
        if detailed_billing:
            payment_data.extend([
                [Paragraph('', cell_value_sm),
                 Paragraph('<b>Deposits</b>', cell_value_sm),
                 Paragraph(f"{deposits_total:,.2f}", cell_value_right)],
                [Paragraph('', cell_value_sm),
                 Paragraph('<b>Balance</b>'
                           if balance > 0 else
                           '<b>Refund Due</b>' if balance < -0.01 else
                           '<b>Balance</b>', cell_value_sm),
                 Paragraph(
                    f"{abs(balance):,.2f}" if abs(balance) > 0.01 else "0.00",
                    ParagraphStyle('Bal', parent=cell_value_right,
                        fontName='Helvetica-Bold'))],
            ])
        payment_table = Table(payment_data, colWidths=[summary_label_w, qty_w, amt_w])
        payment_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('LINEABOVE', (1, -1), (-1, -1), 1, colors.black),
        ]))
        elements.append(payment_table)
        elements.append(Spacer(1, 4))

        # ============================================================
        # Amount in words — uses the balance the patient sees
        # ============================================================
        def amount_to_words(amount):
            try:
                ones = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven',
                        'Eight', 'Nine', 'Ten', 'Eleven', 'Twelve', 'Thirteen',
                        'Fourteen', 'Fifteen', 'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen']
                tens = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty',
                        'Sixty', 'Seventy', 'Eighty', 'Ninety']
                num = int(amount)
                if num == 0:
                    return "Zero"
                def two_digits(n):
                    if n < 20: return ones[n]
                    return tens[n // 10] + (' ' + ones[n % 10] if n % 10 else '')
                def three_digits(n):
                    if n >= 100:
                        return ones[n // 100] + ' Hundred' + (
                            ' and ' + two_digits(n % 100) if n % 100 else '')
                    return two_digits(n)
                parts = []
                if num >= 10000000:
                    parts.append(two_digits(num // 10000000) + ' Crore')
                    num %= 10000000
                if num >= 100000:
                    parts.append(two_digits(num // 100000) + ' Lakh')
                    num %= 100000
                if num >= 1000:
                    parts.append(two_digits(num // 1000) + ' Thousand')
                    num %= 1000
                if num > 0:
                    parts.append(three_digits(num))
                return ' '.join(parts) + ' Only'
            except Exception:
                return str(amount)

        words_text = f"Rupees {amount_to_words(total)}"
        words_data = [[lv('In words', words_text)]]
        words_table = Table(words_data, colWidths=[page_width])
        words_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(words_table)
        elements.append(Spacer(1, 8))

        # ============================================================
        # FOOTER — prepared by / printed by (same as OPD)
        # ============================================================
        prepared_by = bill_data.get('prepared_by_name', '')
        footer_data = [[
            lv('Prepared by', prepared_by),
            lv('Printed by', prepared_by),
        ]]
        footer_table = Table(footer_data, colWidths=[page_width / 2, page_width / 2])
        footer_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(footer_table)

        # Watermark: CANCELLED bills always; INTERIM bills surface that they
        # are not the final settlement.
        wm = None
        if (bill_data.get('status') or '').lower() == 'cancelled':
            wm = 'CANCELLED'
        elif (bill_data.get('bill_subtype') or '').lower() == 'interim':
            wm = 'INTERIM'
        _finalize(doc, elements, hospital_info, watermark=wm)
        buffer.seek(0)
        return buffer


    def generate_bill_pdf(self, bill_data, hospital_info, include_header=True, letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT, detailed_billing=True, include_footer=True):
        """Generate PDF for bill/receipt in tabular format"""
        buffer = BytesIO()

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=30,
            leftMargin=30,
            topMargin=30,
            bottomMargin=20
        )

        elements = []
        page_width = A4[0] - 60  # total usable width

        # --- Styles (no colors, black & white only) ---
        title_style = ParagraphStyle('BillTitle', parent=self.styles['Title'],
            fontSize=16, alignment=1, fontName='Helvetica-Bold',
            textColor=colors.black, spaceAfter=2)

        subtitle_style = ParagraphStyle('BillSubtitle', parent=self.styles['Normal'],
            fontSize=9, alignment=1, fontName='Helvetica',
            textColor=colors.black, spaceAfter=2)

        receipt_title_style = ParagraphStyle('ReceiptTitle', parent=self.styles['Normal'],
            fontSize=12, alignment=1, fontName='Helvetica-Bold',
            textColor=colors.black, spaceAfter=4)

        cell_label = ParagraphStyle('CellLabel', parent=self.styles['Normal'],
            fontSize=8, fontName='Helvetica-Bold', textColor=colors.black)

        cell_value = ParagraphStyle('CellValue', parent=self.styles['Normal'],
            fontSize=8, fontName='Helvetica', textColor=colors.black)

        cell_label_sm = ParagraphStyle('CellLabelSm', parent=self.styles['Normal'],
            fontSize=7, fontName='Helvetica-Bold', textColor=colors.black)

        cell_value_sm = ParagraphStyle('CellValueSm', parent=self.styles['Normal'],
            fontSize=7, fontName='Helvetica', textColor=colors.black)

        # Helper to make label:value pairs
        def lv(label, value):
            return Paragraph(f"<b>{label}</b> :  {value}", cell_value)

        def lv_sm(label, value):
            return Paragraph(f"<b>{label}</b> :  {value}", cell_value_sm)

        # --- Parse dates ---
        bill_date_str = ""
        try:
            bd = datetime.fromisoformat(bill_data.get('bill_date', ''))
            bill_date_str = bd.strftime('%d/%m/%Y')
        except Exception:
            bill_date_str = datetime.now().strftime('%d/%m/%Y')

        # ============================================================
        # HEADER: Hospital Name + Address + Receipt Title
        # ============================================================
        if include_header:
            logo_path = hospital_info.get('logo_url', '')
            uploads_base = _get_uploads_base()
            has_logo = False
            full_logo_path = ''
            if logo_path:
                relative = logo_path.lstrip('/')
                if relative.startswith('uploads/'):
                    relative = relative[len('uploads/'):]
                full_logo_path = os.path.join(uploads_base, relative)
                has_logo = os.path.exists(full_logo_path)

            hospital_name = hospital_info.get('name', 'HOSPITAL').upper()
            hospital_subname = hospital_info.get('hospital_subname', '')
            address = hospital_info.get('address', '')
            contact_parts = []
            if hospital_info.get('email'):
                contact_parts.append(f"Email: {hospital_info['email']}")
            if hospital_info.get('phone'):
                contact_parts.append(f"Phone: {hospital_info['phone']}")

            header_text_elems = [Paragraph(hospital_name, title_style)]
            if hospital_subname:
                header_text_elems.append(Paragraph(hospital_subname, subtitle_style))
            if address:
                header_text_elems.append(Paragraph(address, subtitle_style))
            if contact_parts:
                header_text_elems.append(Paragraph("  |  ".join(contact_parts), subtitle_style))

            if has_logo:
                try:
                    logo_img = Image(full_logo_path, width=60, height=60)
                    logo_img.hAlign = 'CENTER'
                    header_table = Table([[logo_img, header_text_elems]], colWidths=[75, page_width - 75])
                    header_table.setStyle(TableStyle([
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 0),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                        ('TOPPADDING', (0, 0), (-1, -1), 0),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                    ]))
                    elements.append(header_table)
                except Exception:
                    for el in header_text_elems:
                        elements.append(el)
            else:
                for el in header_text_elems:
                    elements.append(el)

            elements.append(Spacer(1, 6))
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        else:
            # Leave blank space for pre-printed letterhead (~100pt ≈ 3.5cm)
            elements.append(Spacer(1, letterhead_gap_pt))

        elements.append(Spacer(1, 4))
        elements.append(Paragraph("RECEIPT CUM REQUISITION", receipt_title_style))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        elements.append(Spacer(1, 6))

        # ============================================================
        # PATIENT INFO + BILL INFO (bordered box, like lab report)
        # ============================================================
        patient_name = bill_data.get('patient_name', '')
        age_sex = _age_gender_str(bill_data, gender=bill_data.get('patient_gender', ''))

        phone = bill_data.get('patient_phone', '')
        patient_id = bill_data.get('mrn', '')
        doctor = bill_data.get('doctor_name', '')
        referred_by = bill_data.get('referred_by', '')
        pay_category = bill_data.get('payment_method', 'Cash')
        bill_no = bill_data.get('bill_number', '')

        # Determine referral label
        if doctor:
            ref_label = 'Doctor'
            ref_value = doctor
        elif referred_by:
            ref_label = 'Referred By'
            ref_value = referred_by
        else:
            ref_label = 'Referred By'
            ref_value = 'Self'

        col_w = page_width / 2

        token_num = bill_data.get('token_number')
        if token_num:
            token_style = ParagraphStyle('TokenCell', parent=self.styles['Normal'],
                fontSize=12, fontName='Helvetica-Bold', textColor=colors.black)
            token_cell = Paragraph(f"<b>TOKEN #</b> &nbsp; <font size='16'>{token_num}</font>", token_style)
        else:
            token_cell = Paragraph('', cell_value)

        patient_info_data = [
            [lv('Name', patient_name), token_cell],
            [lv('Age / Gender', age_sex), lv('Bill No', bill_no)],
            [lv('Phone', phone), lv('Bill Date', bill_date_str)],
            [lv('MRN', patient_id), lv('Address', _patient_address_line(bill_data))],
            [lv(ref_label, ref_value), lv('Pay Mode', pay_category)],
        ]

        info_style = [
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ]

        info_table = Table(patient_info_data, colWidths=[col_w, col_w])
        info_table.setStyle(TableStyle(info_style))
        elements.append(info_table)
        elements.append(Spacer(1, 6))

        # ============================================================
        # ITEMS TABLE: Sno | Description | Code | Rate
        # ============================================================
        sno_w = 0.4 * inch
        code_w = 1.0 * inch
        rate_w = 1.0 * inch
        desc_w = page_width - sno_w - code_w - rate_w

        items_header = [
            Paragraph('<b>Sno</b>', cell_label),
            Paragraph('<b>Description</b>', cell_label),
            Paragraph('<b>Code</b>', cell_label),
            Paragraph('<b>Rate</b>', cell_label),
        ]

        items_data = [items_header]
        for idx, item in enumerate(bill_data.get('items', []), 1):
            items_data.append([
                Paragraph(str(idx), cell_value),
                Paragraph(item.get('item_name', ''), cell_value),
                Paragraph(item.get('item_code', ''), cell_value),
                Paragraph(f"{item.get('total_price', 0):.2f}", cell_value),
            ])


        items_table = Table(items_data, colWidths=[sno_w, desc_w, code_w, rate_w])
        items_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
        ]))
        elements.append(items_table)
        elements.append(Spacer(1, 6))

        # ============================================================
        # PAYMENT SUMMARY TABLE
        # ============================================================
        total_amt = bill_data.get('subtotal', 0)
        discount = bill_data.get('discount_amount', 0)
        tax_amt = bill_data.get('tax_amount', 0)
        paid_amt = bill_data.get('amount_paid', 0)
        balance = bill_data.get('balance_due', 0)
        # Net (post-discount, post-tax) bill amount — used for the amount-in-words
        # line so an unpaid bill still reads the actual sum due, not "Zero".
        net_total = bill_data.get('total_amount')
        if net_total is None:
            net_total = round((total_amt or 0) + (tax_amt or 0) - (discount or 0), 2)
        # Some callers (e.g. procedure / unpaid receipts) don't want the
        # Paid/Balance lines on the printed bill at all.
        hide_payment_summary = bool(bill_data.get('hide_payment_summary'))

        # Convert amount to words
        def amount_to_words(amount):
            try:
                ones = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven',
                        'Eight', 'Nine', 'Ten', 'Eleven', 'Twelve', 'Thirteen',
                        'Fourteen', 'Fifteen', 'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen']
                tens = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty',
                        'Sixty', 'Seventy', 'Eighty', 'Ninety']

                num = int(amount)
                if num == 0:
                    return "Zero"

                def two_digits(n):
                    if n < 20:
                        return ones[n]
                    return tens[n // 10] + (' ' + ones[n % 10] if n % 10 else '')

                def three_digits(n):
                    if n >= 100:
                        return ones[n // 100] + ' Hundred' + (' and ' + two_digits(n % 100) if n % 100 else '')
                    return two_digits(n)

                parts = []
                if num >= 10000000:
                    parts.append(two_digits(num // 10000000) + ' Crore')
                    num %= 10000000
                if num >= 100000:
                    parts.append(two_digits(num // 100000) + ' Lakh')
                    num %= 100000
                if num >= 1000:
                    parts.append(two_digits(num // 1000) + ' Thousand')
                    num %= 1000
                if num > 0:
                    parts.append(three_digits(num))

                return ' '.join(parts) + ' Only'
            except Exception:
                return str(amount)

        # Summary right-aligned under Rate column
        summary_label_w = page_width - code_w - rate_w
        cell_value_right = ParagraphStyle('CellValueRight', parent=cell_value_sm, alignment=2)

        has_adjustments = (discount or 0) > 0 or (tax_amt or 0) > 0
        payment_data = []
        if detailed_billing:
            payment_data.append([
                lv_sm('Paymode', pay_category),
                Paragraph('<b>Total Amt</b>', cell_value_sm),
                Paragraph(f"{total_amt:.2f}", cell_value_right),
            ])
            payment_data.append([
                Paragraph('', cell_value_sm),
                Paragraph('<b>Discount</b>', cell_value_sm),
                Paragraph(f"{discount:.2f}", cell_value_right),
            ])
            if tax_amt:
                payment_data.append([
                    Paragraph('', cell_value_sm),
                    Paragraph('<b>Tax</b>', cell_value_sm),
                    Paragraph(f"{tax_amt:.2f}", cell_value_right),
                ])
            payment_data.append([
                Paragraph('', cell_value_sm),
                Paragraph('<b>Net Total</b>', cell_value_sm),
                Paragraph(f"{net_total:.2f}", cell_value_right),
            ])
            if not hide_payment_summary:
                payment_data.append([
                    Paragraph('', cell_value_sm),
                    Paragraph('<b>Paid Amt</b>', cell_value_sm),
                    Paragraph(f"{paid_amt:.2f}", cell_value_right),
                ])
                payment_data.append([
                    Paragraph('', cell_value_sm),
                    Paragraph('<b>Balance</b>', cell_value_sm),
                    Paragraph(f"{balance:.2f}", cell_value_right),
                ])
        elif has_adjustments:
            payment_data.append([
                lv_sm('Paymode', pay_category),
                Paragraph('<b>Sub Total</b>', cell_value_sm),
                Paragraph(f"{total_amt:.2f}", cell_value_right),
            ])
            if discount:
                payment_data.append([
                    Paragraph('', cell_value_sm),
                    Paragraph('<b>Discount</b>', cell_value_sm),
                    Paragraph(f"{discount:.2f}", cell_value_right),
                ])
            if tax_amt:
                payment_data.append([
                    Paragraph('', cell_value_sm),
                    Paragraph('<b>Tax</b>', cell_value_sm),
                    Paragraph(f"{tax_amt:.2f}", cell_value_right),
                ])
            payment_data.append([
                Paragraph('', cell_value_sm),
                Paragraph('<b>Total Amt</b>', cell_value_sm),
                Paragraph(f"{net_total:.2f}", cell_value_right),
            ])
        else:
            payment_data.append([
                lv_sm('Paymode', pay_category),
                Paragraph('<b>Total Amt</b>', cell_value_sm),
                Paragraph(f"{net_total:.2f}", cell_value_right),
            ])

        payment_table = Table(payment_data, colWidths=[summary_label_w, code_w, rate_w])
        payment_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(payment_table)
        elements.append(Spacer(1, 4))

        # Amount in words — use the net total so an unpaid bill still reads
        # the actual sum due (paid_amt would be 0 for a fresh procedure bill).
        words_text = f"Rupees {amount_to_words(net_total)}"
        words_data = [[lv('In words', words_text)]]
        words_table = Table(words_data, colWidths=[page_width])
        words_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(words_table)
        elements.append(Spacer(1, 4))

        # Notes (free-text on the bill — surfaced for procedure bills etc.)
        notes_text = (bill_data.get('notes') or '').strip()
        if notes_text:
            notes_table = Table([[lv('Notes', notes_text)]], colWidths=[page_width])
            notes_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(notes_table)
            elements.append(Spacer(1, 4))
        elements.append(Spacer(1, 4))

        # ============================================================
        # FOOTER: prepared by / printed by
        # ============================================================
        if include_footer:
            prepared_by = bill_data.get('prepared_by', '')
            footer_data = [
                [lv('Prepared by', prepared_by), lv('Printed by', prepared_by)],
            ]
            footer_table = Table(footer_data, colWidths=[page_width / 2, page_width / 2])
            footer_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(footer_table)

        # Build PDF
        _finalize(doc, elements, hospital_info)
        buffer.seek(0)
        return buffer

    def generate_prescription_pdf(self, prescription_data, hospital_info, include_header=True, letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT, blank_mode=False):
        """Generate PDF for prescription matching the reference layout:
        Header → Doctor+Patient info box → Diagnosis → Vitals (left) + Medicines (right) → Instructions

        When blank_mode=True, vitals show labeled empty rows for handwritten entry.
        """
        buffer = BytesIO()

        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            rightMargin=40, leftMargin=40, topMargin=30, bottomMargin=30
        )

        elements = []
        page_width = A4[0] - 80  # usable width

        # Colors — black & white only
        accent = colors.black
        border_color = colors.HexColor('#999999')
        text_dark = colors.black
        text_muted = colors.HexColor('#444444')

        # --- Styles ---
        title_style = ParagraphStyle('RxTitle', parent=self.styles['Title'],
            fontSize=18, alignment=1, fontName='Helvetica-Bold',
            textColor=text_dark, spaceAfter=2)

        subtitle_style = ParagraphStyle('RxSubtitle', parent=self.styles['Normal'],
            fontSize=9, alignment=1, fontName='Helvetica',
            textColor=text_muted, spaceAfter=2)

        section_hdr = ParagraphStyle('RxSectionHdr', parent=self.styles['Normal'],
            fontSize=11, fontName='Helvetica-Bold', textColor=accent,
            spaceBefore=0, spaceAfter=4)

        cell_lbl = ParagraphStyle('RxCellLbl', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica-Bold', textColor=text_dark)

        cell_val = ParagraphStyle('RxCellVal', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica', textColor=text_dark)

        cell_val_sm = ParagraphStyle('RxCellValSm', parent=self.styles['Normal'],
            fontSize=8, fontName='Helvetica', textColor=text_dark)

        blank_line_style = ParagraphStyle('RxBlankLine', parent=self.styles['Normal'],
            fontSize=10, fontName='Helvetica', textColor=text_dark, leading=18)

        footer_style = ParagraphStyle('RxFooter', parent=self.styles['Normal'],
            fontSize=7, alignment=1, fontName='Helvetica', textColor=colors.grey)

        def lbl(text):
            return Paragraph(f"<b>{text}</b>", cell_lbl)

        def val(text):
            return Paragraph(str(text) if text else '', cell_val)

        # --- Parse dates ---
        try:
            rx_date = datetime.fromisoformat(prescription_data.get('prescription_date', '')).strftime('%d/%m/%Y')
        except Exception:
            rx_date = datetime.now().strftime('%d/%m/%Y')

        # ============================================================
        # HEADER — Logo (left) + Hospital Name + Address (center)
        # ============================================================
        if include_header:
            hospital_name = hospital_info.get('name', 'HOSPITAL').upper()
            address = hospital_info.get('address', '')
            contact_parts = []
            if hospital_info.get('phone'):
                contact_parts.append(f"Tel: {hospital_info['phone']}")
            if hospital_info.get('email'):
                contact_parts.append(f"Email: {hospital_info['email']}")
            contact_line = " | ".join(contact_parts)

            # Try to load hospital logo
            logo_path = hospital_info.get('logo_url', '')
            uploads_base = _get_uploads_base()
            has_logo = False
            full_logo_path = ''
            if logo_path:
                relative = logo_path.lstrip('/')
                if relative.startswith('uploads/'):
                    relative = relative[len('uploads/'):]
                full_logo_path = os.path.join(uploads_base, relative)
                has_logo = os.path.exists(full_logo_path)

            header_text_elems = [Paragraph(hospital_name, title_style)]
            if address:
                header_text_elems.append(Paragraph(address, subtitle_style))
            if contact_line:
                header_text_elems.append(Paragraph(contact_line, subtitle_style))

            if has_logo:
                try:
                    logo_img = Image(full_logo_path, width=65, height=65)
                    logo_img.hAlign = 'CENTER'
                    header_table = Table(
                        [[logo_img, header_text_elems]],
                        colWidths=[80, page_width - 80]
                    )
                    header_table.setStyle(TableStyle([
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 0),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                        ('TOPPADDING', (0, 0), (-1, -1), 0),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                    ]))
                    elements.append(header_table)
                except Exception:
                    for el in header_text_elems:
                        elements.append(el)
            else:
                for el in header_text_elems:
                    elements.append(el)

            elements.append(Spacer(1, 10))
        else:
            # Leave blank space for pre-printed letterhead (~100pt ≈ 3.5cm)
            elements.append(Spacer(1, letterhead_gap_pt))

        # ============================================================
        # PATIENT + DOCTOR INFO — bordered box (like lab report)
        # ============================================================
        doctor_name = prescription_data.get('doctor_name', '')
        doctor_spec = prescription_data.get('doctor_specialization', '')
        doctor_reg = prescription_data.get('doctor_registration_number', '')
        prescription_number = prescription_data.get('prescription_number', '')
        patient_name = prescription_data.get('patient_name', '')
        patient_age = prescription_data.get('patient_age', '')
        patient_gender = prescription_data.get('patient_gender', '')
        patient_blood_group = prescription_data.get('patient_blood_group', '')
        patient_phone = prescription_data.get('patient_phone', '')
        patient_id = prescription_data.get('mrn', '')

        age_sex = _age_gender_str(prescription_data, gender=patient_gender)

        doctor_display = doctor_name
        if doctor_spec:
            doctor_display = f"{doctor_name} ({doctor_spec})"

        col_w = page_width / 2
        reg_or_rx_label = "Rx No." if blank_mode else "Reg. No."
        reg_or_rx_value = (prescription_number or '—') if blank_mode else (doctor_reg or '—')
        appointment_number = prescription_data.get('appointment_number', '')
        info_data = [
            [Paragraph(f"<b>Name</b> :  {patient_name}", cell_val), Paragraph(f"<b>Prescribed By</b> :  {doctor_display}", cell_val)],
            [Paragraph(f"<b>Age / Gender</b> :  {age_sex}", cell_val), Paragraph(f"<b>{reg_or_rx_label}</b> :  {reg_or_rx_value}", cell_val)],
            [Paragraph(f"<b>Phone</b> :  {patient_phone}", cell_val), Paragraph(f"<b>Date</b> :  {rx_date}", cell_val)],
            [Paragraph(f"<b>MRN</b> :  {patient_id}", cell_val), Paragraph(
                f"<b>Appointment</b> :  {appointment_number or '—'}" if blank_mode and appointment_number
                else f"<b>Blood Group</b> :  {patient_blood_group or '—'}",
                cell_val
            )],
        ]

        info_style = [
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ]
        _rx_addr = _patient_address_line(prescription_data)
        if _rx_addr:
            _addr_row_idx = len(info_data)
            info_data.append([Paragraph(f"<b>Address</b> :  {_rx_addr}", cell_val), ''])
            info_style.append(('SPAN', (0, _addr_row_idx), (1, _addr_row_idx)))

        referred_by = (prescription_data.get('referred_by') or '').strip()
        if referred_by:
            _ref_row_idx = len(info_data)
            info_data.append([Paragraph(f"<b>Referred By</b> :  {referred_by}", cell_val), ''])
            info_style.append(('SPAN', (0, _ref_row_idx), (1, _ref_row_idx)))

        info_table = Table(info_data, colWidths=[col_w, col_w])
        info_table.setStyle(TableStyle(info_style))
        elements.append(info_table)
        elements.append(Spacer(1, 10))

        # ============================================================
        # DIAGNOSIS — full-width section (filled prescriptions only)
        # ============================================================
        diagnosis_text = prescription_data.get('diagnosis', '')
        consultation = prescription_data.get('consultation')
        appointment_reason = prescription_data.get('appointment_reason', '')

        if not blank_mode:
            diag_content = []
            if appointment_reason:
                diag_content.append(Paragraph(f"Appointment Reason: {appointment_reason}", cell_val))
            if diagnosis_text:
                diag_content.append(Paragraph(diagnosis_text, cell_val))
            if consultation:
                if consultation.get('chief_complaint'):
                    diag_content.append(Paragraph(f"Chief Complaint: {consultation['chief_complaint']}", cell_val))
                if consultation.get('examination_findings'):
                    diag_content.append(Paragraph(f"Examination: {consultation['examination_findings']}", cell_val))

            if not diag_content:
                diag_content.append(Paragraph('', cell_val))

            diag_rows = [
                [Paragraph('<b>Diagnosis</b>', section_hdr)],
            ] + [[c] for c in diag_content]

            diag_table = Table(diag_rows, colWidths=[page_width])
            diag_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ]))
            elements.append(diag_table)
            elements.append(Spacer(1, 10))

        # ============================================================
        # VITALS (left) + MEDICINES / DIAGNOSIS (right) — side by side
        # ============================================================
        vitals = prescription_data.get('vitals')
        vitals_left_width = page_width * 0.25
        meds_right_width = page_width * 0.73
        gap = page_width * 0.02

        # --- Build vitals sub-table ---
        blank_vital_fields = (
            ('Height', 'cms'),
            ('Weight', 'Kg'),
            ('Blood\nPressure', ''),
            ('Pulse', '/min'),
            ('Temperature', '°F'),
            ('Resp. Rate', '/min'),
            ('SpO2', '%'),
        )
        vitals_rows = [[Paragraph('<b><u>Vitals</u></b>', cell_lbl), '']]
        if blank_mode:
            for label, unit_hint in blank_vital_fields:
                hint = f" <font size='7' color='#888888'>{unit_hint}</font>" if unit_hint else ''
                vitals_rows.append([
                    lbl(label),
                    Paragraph(hint or '&nbsp;', cell_val),
                ])
        elif vitals and vitals.get('vital_signs'):
            vs = vitals['vital_signs']
            if vs.get('height'):
                vitals_rows.append([lbl('Height'), val(f"{vs['height']} cms")])
            if vs.get('weight'):
                vitals_rows.append([lbl('Weight'), val(f"{vs['weight']} Kg")])
            if vs.get('blood_pressure'):
                vitals_rows.append([lbl('Blood\nPressure'), val(vs['blood_pressure'])])
            if vs.get('heart_rate'):
                vitals_rows.append([lbl('Pulse'), val(str(vs['heart_rate']))])
            if vs.get('temperature'):
                vitals_rows.append([lbl('Temperature'), val(f"{vs['temperature']} F")])
            if vs.get('respiratory_rate'):
                vitals_rows.append([lbl('Resp. Rate'), val(str(vs['respiratory_rate']))])
            if vs.get('spo2') or vs.get('oxygen_saturation'):
                vitals_rows.append([lbl('SpO2'), val(f"{vs.get('spo2') or vs.get('oxygen_saturation')}%")])
            if vs.get('bmi'):
                vitals_rows.append([lbl('BMI'), val(str(vs['bmi']))])
        else:
            vitals_rows.append([Paragraph('No vitals recorded', cell_val_sm), ''])

        vitals_table = Table(vitals_rows, colWidths=[vitals_left_width * 0.55, vitals_left_width * 0.45])
        vitals_style = [
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('SPAN', (0, 0), (1, 0)),  # header spans
        ]
        if blank_mode:
            vitals_style.extend([
                ('TOPPADDING', (0, 1), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 1), (-1, -1), 10),
                ('LINEBELOW', (1, 1), (1, -1), 0.5, border_color),
            ])
        vitals_table.setStyle(TableStyle(vitals_style))

        # --- Lab tests (left column) ---
        lab_tests = prescription_data.get('lab_tests', [])
        lab_rows = []
        if lab_tests:
            header = '<b><u>Tests Ordered</u></b>' if blank_mode else '<b><u>Tests Done</u></b>'
            lab_rows.append([Paragraph(header, cell_lbl), ''])
            for t in lab_tests:
                status_text = (t.get('status', '') or '').capitalize()
                lab_rows.append([
                    Paragraph(f"&bull; {t.get('test_name', '')}", cell_val_sm),
                    Paragraph(status_text, cell_val_sm),
                ])
        elif blank_mode:
            lab_rows.append([Paragraph('<b><u>Lab Tests</u></b>', cell_lbl), ''])

        lab_tests_table = None
        if lab_rows:
            lab_tests_table = Table(lab_rows, colWidths=[vitals_left_width * 0.65, vitals_left_width * 0.35])
            lab_tests_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                ('SPAN', (0, 0), (1, 0)),
            ]))

        # Combine vitals + lab tests into left column
        left_col_parts = [[vitals_table]]
        if lab_tests_table:
            left_col_parts.append([Spacer(1, 14 if blank_mode else 8)])
            left_col_parts.append([lab_tests_table])
        left_col_wrapper = Table(left_col_parts, colWidths=[vitals_left_width])
        left_col_wrapper.setStyle(TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))

        # --- Build medicines sub-table ---
        food_timing_map = {
            'before_food': 'Before food', 'after_food': 'After food',
            'with_food': 'With food', 'on_empty_stomach': 'Empty stomach', 'anytime': 'Anytime'
        }

        sno_w = meds_right_width * 0.07
        name_w = meds_right_width * 0.31
        dosage_w = meds_right_width * 0.22
        freq_w = meds_right_width * 0.22
        dur_w = meds_right_width * 0.18

        med_header = [
            Paragraph('<b>No</b>', cell_lbl),
            Paragraph('<b>Medicine Name</b>', cell_lbl),
            Paragraph('<b>Dosage</b>', cell_lbl),
            Paragraph('<b>Frequency</b>', cell_lbl),
            Paragraph('<b>Duration</b>', cell_lbl),
        ]

        med_data = [med_header]
        if blank_mode:
            pass
        else:
            for idx, item in enumerate(prescription_data.get('items', []), 1):
                freq = item.get('frequency_schedule', '1-0-0')
                food = food_timing_map.get(item.get('food_timing', 'after_food'), 'After food')
                freq_text = f"{freq}\n{food}"

                med_data.append([
                    Paragraph(str(idx), cell_val),
                    Paragraph(f"<b>{item.get('medicine_name', '')}</b>", cell_val),
                    Paragraph(item.get('dosage', 'As directed'), cell_val_sm),
                    Paragraph(freq_text, cell_val_sm),
                    Paragraph(item.get('duration', '—'), cell_val),
                ])

        # No empty padding rows — only show actual medicines (filled mode)

        meds_header_row = [[Paragraph('<b>Medicines</b>', section_hdr)]]
        meds_title_table = Table(meds_header_row, colWidths=[meds_right_width])
        meds_title_table.setStyle(TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))

        med_table = Table(med_data, colWidths=[sno_w, name_w, dosage_w, freq_w, dur_w])
        med_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F0F0F0')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('LINEBELOW', (0, 0), (-1, 0), 1, border_color),
        ]))

        # Combine medicines (+ blank diagnosis) into right column
        meds_combined = [[meds_title_table], [med_table]]
        if blank_mode:
            diag_right_rows = [[Paragraph('<b>Diagnosis</b>', section_hdr)]]
            diag_right_table = Table(diag_right_rows, colWidths=[meds_right_width])
            diag_right_table.setStyle(TableStyle([
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))
            meds_combined.append([Spacer(1, 8)])
            meds_combined.append([diag_right_table])

        meds_wrapper = Table(meds_combined, colWidths=[meds_right_width])
        meds_wrapper.setStyle(TableStyle([
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))

        # Side by side layout with vertical divider
        layout_table = Table(
            [[left_col_wrapper, meds_wrapper]],
            colWidths=[vitals_left_width, meds_right_width + gap]
        )
        layout_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('LINEAFTER', (0, 0), (0, -1), 0.5, colors.Color(0.7, 0.7, 0.7)),  # Vertical divider line
        ]))
        elements.append(layout_table)

        # ============================================================
        # INSTRUCTIONS — filled prescriptions only
        # ============================================================
        if not blank_mode:
            elements.append(Spacer(1, 10))
            notes = prescription_data.get('notes', '')
            follow_up = None
            if consultation and consultation.get('follow_up_date'):
                follow_up = consultation['follow_up_date']

            instr_content = []
            if notes:
                instr_content.append(Paragraph(notes, cell_val))
            if follow_up:
                instr_content.append(Paragraph(f"<b>Follow-up:</b> {follow_up}", cell_val))
            if not instr_content:
                instr_content.append(Paragraph('', cell_val))

            instr_rows = [
                [Paragraph('<b>Instructions</b>', section_hdr)],
            ] + [[c] for c in instr_content]

            instr_table = Table(instr_rows, colWidths=[page_width])
            instr_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ]))
            elements.append(instr_table)
        else:
            elements.append(Spacer(1, 10))

        # ============================================================
        # SIGNATURE
        # ============================================================
        elements.append(Spacer(1, 30))
        if blank_mode and prescription_number:
            sig_doctor_detail = (f"<b>{doctor_name}</b><br/>{doctor_spec}<br/>"
                                 f"Rx No: {prescription_number}")
        elif doctor_reg:
            sig_doctor_detail = (f"<b>{doctor_name}</b><br/>{doctor_spec}<br/>"
                                 f"Reg. No: {doctor_reg}")
        else:
            sig_doctor_detail = f"<b>{doctor_name}</b><br/>{doctor_spec}"
        sig_rows = [[
            Paragraph(f"Date: {rx_date}", cell_val),
            Paragraph(sig_doctor_detail,
                      ParagraphStyle('SigStyle', parent=cell_val_sm, alignment=2))
        ]]
        sig_table = Table(sig_rows, colWidths=[page_width * 0.50, page_width * 0.50])
        sig_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        elements.append(sig_table)

        # Footer
        elements.append(Spacer(1, 15))
        elements.append(Paragraph(f"Generated on {datetime.now().strftime('%d/%m/%Y at %H:%M:%S')}", footer_style))

        _finalize(doc, elements, hospital_info)
        buffer.seek(0)
        return buffer

    def generate_lab_report_pdf(self, report_data, hospital_info, lab_config=None, include_header=True, letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT, include_footer=True):
        """Generate PDF for lab report"""
        if lab_config is None:
            lab_config = {}

        buffer = BytesIO()

        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=20
        )

        elements = []
        page_width = A4[0] - 60

        # --- Styles ---
        title_style = ParagraphStyle('LabTitle', parent=self.styles['Title'],
            fontSize=16, alignment=1, fontName='Helvetica-Bold',
            textColor=colors.black, spaceAfter=2)

        subtitle_style = ParagraphStyle('LabSubtitle', parent=self.styles['Normal'],
            fontSize=9, alignment=1, fontName='Helvetica',
            textColor=colors.black, spaceAfter=2)

        reg_style = ParagraphStyle('LabReg', parent=self.styles['Normal'],
            fontSize=8, alignment=1, fontName='Helvetica',
            textColor=colors.grey, spaceAfter=1)

        report_title_style = ParagraphStyle('LabReportTitle', parent=self.styles['Normal'],
            fontSize=12, alignment=1, fontName='Helvetica-Bold',
            textColor=colors.black, spaceAfter=4)

        cell_label = ParagraphStyle('LabCellLabel', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica-Bold', textColor=colors.black)

        cell_value = ParagraphStyle('LabCellValue', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica', textColor=colors.black)

        cell_abnormal = ParagraphStyle('LabCellAbnormal', parent=self.styles['Normal'],
            fontSize=10, fontName='Helvetica-Bold', textColor=colors.black)

        cell_ref_range = ParagraphStyle('LabCellRefRange', parent=cell_value,
            fontSize=7, leading=9, textColor=colors.black)

        normal_text = ParagraphStyle('LabNormalText', parent=self.styles['Normal'],
            fontSize=10, spaceAfter=6, fontName='Helvetica', textColor=colors.black)

        footer_style = ParagraphStyle('LabFooter', parent=self.styles['Normal'],
            fontSize=8, alignment=1, fontName='Helvetica', textColor=colors.grey)

        def lv(label, value):
            return Paragraph(f"<b>{label}</b> :  {value}", cell_value)

        # Use lab config provider details if available, fall back to hospital info
        hospital_name = hospital_info.get('name', 'HOSPITAL')
        provider_name = lab_config.get('provider_name') or hospital_name
        # Show hospital name as secondary line if lab has its own name
        show_hospital_subline = lab_config.get('provider_name') and lab_config['provider_name'].strip().upper() != hospital_name.strip().upper()
        provider_address_parts = []
        if lab_config.get('provider_address'):
            provider_address_parts.append(lab_config['provider_address'])
        if lab_config.get('provider_city'):
            provider_address_parts.append(lab_config['provider_city'])
        if lab_config.get('provider_state'):
            provider_address_parts.append(lab_config['provider_state'])
        if lab_config.get('provider_pincode'):
            provider_address_parts.append(f"- {lab_config['provider_pincode']}")
        provider_address = ", ".join(provider_address_parts) if provider_address_parts else hospital_info.get('address', '')

        provider_phone = lab_config.get('provider_phone') or hospital_info.get('phone', '')
        provider_email = lab_config.get('provider_email') or hospital_info.get('email', '')

        # ============================================================
        # HEADER — Logo + Provider Name side by side
        # ============================================================
        if include_header:
            logo_path = lab_config.get('provider_logo', '') or hospital_info.get('logo_url', '')
            uploads_base = _get_uploads_base()

            has_logo = False
            full_logo_path = ''
            if logo_path:
                relative = logo_path.lstrip('/')
                if relative.startswith('uploads/'):
                    relative = relative[len('uploads/'):]
                full_logo_path = os.path.join(uploads_base, relative)
                has_logo = os.path.exists(full_logo_path)

            if has_logo:
                try:
                    logo_img = Image(full_logo_path, width=60, height=60)
                    logo_img.hAlign = 'CENTER'

                    header_text_parts = []
                    header_text_parts.append(Paragraph(provider_name.upper(), title_style))
                    if show_hospital_subline:
                        header_text_parts.append(Paragraph(hospital_name, subtitle_style))
                    if provider_address:
                        header_text_parts.append(Paragraph(provider_address, subtitle_style))
                    contact_parts = []
                    if provider_email:
                        contact_parts.append(f"Email: {provider_email}")
                    if provider_phone:
                        contact_parts.append(f"Phone: {provider_phone}")
                    if contact_parts:
                        header_text_parts.append(Paragraph("  |  ".join(contact_parts), subtitle_style))

                    from reportlab.platypus import KeepTogether
                    header_table = Table(
                        [[logo_img, header_text_parts]],
                        colWidths=[80, page_width - 80]
                    )
                    header_table.setStyle(TableStyle([
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 0),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                        ('TOPPADDING', (0, 0), (-1, -1), 0),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                    ]))
                    elements.append(header_table)
                except Exception:
                    elements.append(Paragraph(provider_name.upper(), title_style))
                    if provider_address:
                        elements.append(Paragraph(provider_address, subtitle_style))
            else:
                elements.append(Paragraph(provider_name.upper(), title_style))
                if show_hospital_subline:
                    elements.append(Paragraph(hospital_name, subtitle_style))
                if provider_address:
                    elements.append(Paragraph(provider_address, subtitle_style))
                contact_parts = []
                if provider_email:
                    contact_parts.append(f"Email: {provider_email}")
                if provider_phone:
                    contact_parts.append(f"Phone: {provider_phone}")
                if contact_parts:
                    elements.append(Paragraph("  |  ".join(contact_parts), subtitle_style))

            # Registration details line
            reg_parts = []
            if lab_config.get('registration_number'):
                reg_parts.append(f"Reg No: {lab_config['registration_number']}")
            if lab_config.get('nabl_number'):
                reg_parts.append(f"NABL: {lab_config['nabl_number']}")
            if lab_config.get('license_number'):
                reg_parts.append(f"Lic No: {lab_config['license_number']}")
            if reg_parts:
                elements.append(Paragraph("  |  ".join(reg_parts), reg_style))

            elements.append(Spacer(1, 6))
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        else:
            # Leave blank space for pre-printed letterhead (~100pt ≈ 3.5cm)
            elements.append(Spacer(1, letterhead_gap_pt))

        elements.append(Spacer(1, 4))
        elements.append(Paragraph("LABORATORY REPORT", report_title_style))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        elements.append(Spacer(1, 6))

        # ============================================================
        # PATIENT INFO — bordered box matching reference layout
        # ============================================================
        def _fmt_dt(val, fmt="%d/%m/%Y %I:%M %p"):
            """Format a date/datetime value for display (system local)."""
            return _fmt_system_dt(val, fmt=fmt)

        patient_name = report_data.get('patient_name', '')
        patient_gender = report_data.get('patient_gender', '')
        age_sex = _age_gender_str(report_data, gender=patient_gender)

        order_date_str = _fmt_dt(report_data.get('order_date'), fmt="%d/%m/%Y")
        collection_date_str = _fmt_dt(report_data.get('collection_date'), fmt="%d/%m/%Y")
        report_date_str = _fmt_dt(report_data.get('report_date'))

        referral_label = report_data.get('referral_label', 'Referred By')
        referral_name = report_data.get('referral_name', 'Self')
        patient_phone = report_data.get('patient_phone', '')

        col_w = page_width / 2
        info_data = [
            [lv('Name', patient_name), lv('Booked Date', order_date_str)],
            [lv('Age / Gender', age_sex), lv('Collection Date', collection_date_str)],
            [lv('Phone', patient_phone), lv('Report Date', report_date_str)],
            [lv(referral_label, referral_name), lv('Sample ID', report_data.get('sample_id', ''))],
            [lv('MRN', report_data.get('mrn', '')), lv('Report ID', report_data.get('order_number', ''))],
        ]

        info_style = [
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ]
        _append_address_row(info_data, info_style, report_data, lv)
        info_table = Table(info_data, colWidths=[col_w, col_w])
        info_table.setStyle(TableStyle(info_style))
        elements.append(info_table)
        elements.append(Spacer(1, 10))

        # ============================================================
        # TEST NAME — centered bold heading
        # ============================================================
        test_name_style = ParagraphStyle('LabTestName', parent=self.styles['Normal'],
            fontSize=11, alignment=1, fontName='Helvetica-Bold',
            textColor=colors.black, spaceAfter=2)

        test_name = report_data.get('test_name', '')
        test_code = report_data.get('test_code', '')
        test_display = test_name.upper()
        if test_code:
            test_display = f"{test_display} ({test_code})"

        elements.append(Paragraph(test_display, test_name_style))
        elements.append(Spacer(1, 6))

        # ============================================================
        # RESULTS TABLE
        # ============================================================
        results_list = report_data.get('results', [])
        results_table = _build_lab_results_table(
            results_list,
            page_width=page_width,
            cell_label=cell_label,
            cell_value=cell_value,
            cell_abnormal=cell_abnormal,
            cell_ref_range=cell_ref_range,
            section_label_style=ParagraphStyle('LabSectionLabel', parent=self.styles['Normal'],
                fontSize=9, fontName='Helvetica-Bold', textColor=colors.black),
        )
        elements.append(results_table)
        elements.append(Spacer(1, 10))

        # ============================================================
        # INTERPRETATION
        # ============================================================
        literal_style = ParagraphStyle('LabLiteral', parent=normal_text,
            fontName='Helvetica', fontSize=9, leading=12, spaceAfter=0)

        def _escape_literal(s):
            return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        interpretation = report_data.get('interpretation')
        if interpretation:
            elements.append(Paragraph("<b>Interpretation:</b>", cell_label))
            elements.append(Spacer(1, 4))
            elements.append(XPreformatted(_escape_literal(interpretation), literal_style))
            elements.append(Spacer(1, 10))

        # ============================================================
        # REFERENCE INFORMATION (from LabTest.description, strictly literal)
        # ============================================================
        test_description = report_data.get('test_description')
        if test_description and test_description.strip():
            elements.append(Paragraph("<b>Reference Information:</b>", cell_label))
            elements.append(Spacer(1, 4))
            elements.append(XPreformatted(_escape_literal(test_description), literal_style))
            elements.append(Spacer(1, 10))

        # ============================================================
        # SIGNATURES
        # ============================================================
        if include_footer:
            elements.append(Spacer(1, 30))
            tech_name = report_data.get('technician_name', '')

            # Build signatory column — use pathologist info from lab config
            pathologist_name = lab_config.get('pathologist_name', '')
            pathologist_qual = lab_config.get('pathologist_qualification', '')
            sig_image_path = lab_config.get('signature_image', '')

            # Left column: Lab Technician
            left_col = Paragraph(f"<b>Lab Technician:</b> {tech_name}", cell_value)

            # Right column: Authorized Signatory with optional signature image
            right_col_parts = []

            # Add signature image if available
            if sig_image_path:
                relative = sig_image_path.lstrip('/')
                if relative.startswith('uploads/'):
                    relative = relative[len('uploads/'):]
                full_sig_path = os.path.join(uploads_base, relative)
                if os.path.exists(full_sig_path):
                    try:
                        sig_img = Image(full_sig_path, width=80, height=35)
                        sig_img.hAlign = 'LEFT'
                        right_col_parts.append(sig_img)
                    except Exception:
                        pass

            if pathologist_name:
                right_col_parts.append(Paragraph(f"<b>{pathologist_name}</b>", cell_value))
            if pathologist_qual:
                qual_style = ParagraphStyle('LabQual', parent=self.styles['Normal'],
                    fontSize=8, fontName='Helvetica', textColor=colors.grey)
                right_col_parts.append(Paragraph(pathologist_qual, qual_style))
            if not pathologist_name:
                right_col_parts.append(Paragraph("<b>Authorized Signatory</b>", cell_value))

            sig_data = [
                [left_col, right_col_parts],
            ]
            sig_table = Table(sig_data, colWidths=[page_width / 2, page_width / 2])
            sig_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
            ]))
            elements.append(sig_table)

            # Footer timestamp
            elements.append(Spacer(1, 20))
            elements.append(Paragraph(f"Generated on {datetime.now().strftime('%d/%m/%Y at %H:%M:%S')}", footer_style))

        _finalize(doc, elements, hospital_info)
        buffer.seek(0)
        return buffer

    def generate_combined_lab_report_pdf(self, reports_list, hospital_info, lab_config=None, include_header=True, letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT, include_footer=True):
        """Generate a single continuous PDF with all tests flowing together.
        Header repeats on every page (or blank space for pre-printed letterhead).
        Patient info on first page only, tests flow continuously, signatures at the end."""
        if lab_config is None:
            lab_config = {}

        buffer = BytesIO()
        # Reserve top margin for the header drawn via onPage callback
        header_height = 100 if include_header else letterhead_gap_pt
        doc = SimpleDocTemplate(buffer, pagesize=A4,
            rightMargin=30, leftMargin=30, topMargin=30 + header_height, bottomMargin=20)

        elements = []
        page_width = A4[0] - 60

        first_report = reports_list[0]

        # --- Build header drawing info for onPage ---
        hospital_name_combined = hospital_info.get('name', 'HOSPITAL')
        provider_name = lab_config.get('provider_name') or hospital_name_combined
        show_hospital_subline = lab_config.get('provider_name') and lab_config['provider_name'].strip().upper() != hospital_name_combined.strip().upper()
        provider_address_parts = []
        if lab_config.get('provider_address'):
            provider_address_parts.append(lab_config['provider_address'])
        if lab_config.get('provider_city'):
            provider_address_parts.append(lab_config['provider_city'])
        if lab_config.get('provider_state'):
            provider_address_parts.append(lab_config['provider_state'])
        if lab_config.get('provider_pincode'):
            provider_address_parts.append(f"- {lab_config['provider_pincode']}")
        provider_address = ", ".join(provider_address_parts) if provider_address_parts else hospital_info.get('address', '')
        provider_phone = lab_config.get('provider_phone') or hospital_info.get('phone', '')
        provider_email = lab_config.get('provider_email') or hospital_info.get('email', '')

        logo_path = lab_config.get('provider_logo', '')
        uploads_base = _get_uploads_base()
        full_logo_path = ''
        has_logo = False
        if logo_path:
            relative = logo_path.lstrip('/')
            if relative.startswith('uploads/'):
                relative = relative[len('uploads/'):]
            full_logo_path = os.path.join(uploads_base, relative)
            has_logo = os.path.exists(full_logo_path)

        reg_parts = []
        if lab_config.get('registration_number'):
            reg_parts.append(f"Reg No: {lab_config['registration_number']}")
        if lab_config.get('nabl_number'):
            reg_parts.append(f"NABL: {lab_config['nabl_number']}")
        if lab_config.get('license_number'):
            reg_parts.append(f"Lic No: {lab_config['license_number']}")
        reg_line = "  |  ".join(reg_parts)

        contact_parts = []
        if provider_email:
            contact_parts.append(f"Email: {provider_email}")
        if provider_phone:
            contact_parts.append(f"Phone: {provider_phone}")
        contact_line = "  |  ".join(contact_parts)

        def _draw_header(c, doc_obj):
            """Draw hospital header or blank space on every page."""
            c.saveState()
            pg_w, pg_h = A4
            top_y = pg_h - 25  # start drawing from near top

            if include_header:
                # Draw logo if available
                text_x = 35
                if has_logo:
                    try:
                        c.drawImage(full_logo_path, 35, top_y - 55, width=55, height=55, preserveAspectRatio=True, mask='auto')
                        text_x = 100
                    except Exception:
                        pass

                # Lab / Hospital name
                c.setFont('Helvetica-Bold', 14)
                c.drawCentredString(pg_w / 2, top_y - 15, provider_name.upper())

                y_offset = 28
                # Hospital name subline (when lab has its own name)
                if show_hospital_subline:
                    c.setFont('Helvetica', 9)
                    c.drawCentredString(pg_w / 2, top_y - y_offset, hospital_name_combined)
                    y_offset += 12

                # Address
                if provider_address:
                    c.setFont('Helvetica', 8)
                    c.drawCentredString(pg_w / 2, top_y - y_offset, provider_address)
                    y_offset += 12

                # Contact
                if contact_line:
                    c.setFont('Helvetica', 7)
                    c.drawCentredString(pg_w / 2, top_y - y_offset, contact_line)
                    y_offset += 12

                # Registration
                if reg_line:
                    c.setFont('Helvetica', 6)
                    c.setFillColor(colors.grey)
                    c.drawCentredString(pg_w / 2, top_y - y_offset, reg_line)
                    c.setFillColor(colors.black)
                    y_offset += 10

                # Divider line
                line_y = top_y - y_offset - 2
                c.setStrokeColor(colors.black)
                c.setLineWidth(1)
                c.line(30, line_y, pg_w - 30, line_y)

            c.restoreState()

        # --- Styles ---
        report_title_style = ParagraphStyle('CLabReportTitle', parent=self.styles['Normal'],
            fontSize=12, alignment=1, fontName='Helvetica-Bold', textColor=colors.black, spaceAfter=4)
        test_name_style = ParagraphStyle('CLabTestName', parent=self.styles['Normal'],
            fontSize=11, alignment=1, fontName='Helvetica-Bold', textColor=colors.black, spaceAfter=2)
        cell_label = ParagraphStyle('CLabCellLabel', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica-Bold', textColor=colors.black)
        cell_value = ParagraphStyle('CLabCellValue', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica', textColor=colors.black)
        cell_abnormal = ParagraphStyle('CLabCellAbnormal', parent=self.styles['Normal'],
            fontSize=10, fontName='Helvetica-Bold', textColor=colors.black)
        cell_ref_range = ParagraphStyle('CLabCellRefRange', parent=cell_value,
            fontSize=7, leading=9, textColor=colors.black)
        normal_text = ParagraphStyle('CLabNormalText', parent=self.styles['Normal'],
            fontSize=10, spaceAfter=6, fontName='Helvetica', textColor=colors.black)
        footer_style = ParagraphStyle('CLabFooter', parent=self.styles['Normal'],
            fontSize=8, alignment=1, fontName='Helvetica', textColor=colors.grey)
        section_label_style = ParagraphStyle('CLabSectionLabel', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica-Bold', textColor=colors.black)

        def lv(label, value):
            return Paragraph(f"<b>{label}</b> :  {value}", cell_value)

        def _fmt_dt(val, fmt="%d/%m/%Y %I:%M %p"):
            return _fmt_system_dt(val, fmt=fmt)

        # ============================================================
        # REPORT TITLE (in flowable area, below header)
        # ============================================================
        elements.append(Paragraph("LABORATORY REPORT", report_title_style))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        elements.append(Spacer(1, 6))

        # ============================================================
        # PATIENT INFO (once, from first report)
        # ============================================================
        patient_name = first_report.get('patient_name', '')
        patient_gender = first_report.get('patient_gender', '')
        age_sex = _age_gender_str(first_report, gender=patient_gender)

        referral_label = first_report.get('referral_label', 'Referred By')
        referral_name = first_report.get('referral_name', 'Self')
        patient_phone = first_report.get('patient_phone', '')

        col_w = page_width / 2
        info_data = [
            [lv('Name', patient_name), lv('Booked Date', _fmt_dt(first_report.get('order_date'), fmt="%d/%m/%Y"))],
            [lv('Age / Gender', age_sex), lv('Collection Date', _fmt_dt(first_report.get('collection_date'), fmt="%d/%m/%Y"))],
            [lv('Phone', patient_phone), lv('Report Date', _fmt_dt(first_report.get('report_date')))],
            [lv(referral_label, referral_name), lv('Report Status', first_report.get('report_status', 'Final'))],
            [lv('MRN', first_report.get('mrn', '')), Paragraph('', cell_value)],
        ]

        info_style = [
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ]
        _append_address_row(info_data, info_style, first_report, lv)
        info_table = Table(info_data, colWidths=[col_w, col_w])
        info_table.setStyle(TableStyle(info_style))
        elements.append(info_table)
        elements.append(Spacer(1, 10))

        # ============================================================
        # LOOP THROUGH EACH TEST — continuous flow
        # ============================================================
        for idx, report_data in enumerate(reports_list):
            test_name = report_data.get('test_name', '')
            test_code = report_data.get('test_code', '')
            test_display = test_name.upper()
            if test_code:
                test_display = f"{test_display} ({test_code})"

            # Test name heading
            if idx > 0:
                elements.append(Spacer(1, 8))
            elements.append(Paragraph(test_display, test_name_style))
            elements.append(Spacer(1, 4))

            results_list_inner = report_data.get('results', [])
            results_table = _build_lab_results_table(
                results_list_inner,
                page_width=page_width,
                cell_label=cell_label,
                cell_value=cell_value,
                cell_abnormal=cell_abnormal,
                cell_ref_range=cell_ref_range,
                section_label_style=section_label_style,
            )
            elements.append(results_table)

            # Interpretation (per test, if any) — strictly literal (preserve whitespace + newlines)
            literal_style = ParagraphStyle('CLabLiteral', parent=normal_text,
                fontName='Helvetica', fontSize=9, leading=12, spaceAfter=0)

            def _escape_literal(s):
                return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

            interpretation = report_data.get('interpretation')
            if interpretation:
                elements.append(Spacer(1, 4))
                elements.append(Paragraph(f"<b>Interpretation ({test_name}):</b>", cell_label))
                elements.append(Spacer(1, 2))
                elements.append(XPreformatted(_escape_literal(interpretation), literal_style))

            # Reference Information (per test, from LabTest.description) — strictly literal
            test_description = report_data.get('test_description')
            if test_description and test_description.strip():
                elements.append(Spacer(1, 4))
                elements.append(Paragraph(f"<b>Reference Information ({test_name}):</b>", cell_label))
                elements.append(Spacer(1, 2))
                elements.append(XPreformatted(_escape_literal(test_description), literal_style))

        # ============================================================
        # SIGNATURES (once at the end)
        # ============================================================
        if include_footer:
            elements.append(Spacer(1, 30))
            uploads_base = _get_uploads_base()

            # Collect unique technician names from all reports
            tech_names = list(dict.fromkeys(r.get('technician_name', '') for r in reports_list if r.get('technician_name')))
            tech_text = ", ".join(tech_names) if tech_names else ""
            left_col = Paragraph(f"<b>Lab Technician:</b> {tech_text}", cell_value)

            pathologist_name = lab_config.get('pathologist_name', '')
            pathologist_qual = lab_config.get('pathologist_qualification', '')
            sig_image_path = lab_config.get('signature_image', '')

            right_col_parts = []
            if sig_image_path:
                relative = sig_image_path.lstrip('/')
                if relative.startswith('uploads/'):
                    relative = relative[len('uploads/'):]
                full_sig_path = os.path.join(uploads_base, relative)
                if os.path.exists(full_sig_path):
                    try:
                        sig_img = Image(full_sig_path, width=80, height=35)
                        sig_img.hAlign = 'LEFT'
                        right_col_parts.append(sig_img)
                    except Exception:
                        pass

            if pathologist_name:
                right_col_parts.append(Paragraph(f"<b>{pathologist_name}</b>", cell_value))
            if pathologist_qual:
                qual_style = ParagraphStyle('CLabQual', parent=self.styles['Normal'],
                    fontSize=8, fontName='Helvetica', textColor=colors.grey)
                right_col_parts.append(Paragraph(pathologist_qual, qual_style))
            if not pathologist_name:
                right_col_parts.append(Paragraph("<b>Authorized Signatory</b>", cell_value))

            sig_table = Table([[left_col, right_col_parts]], colWidths=[page_width / 2, page_width / 2])
            sig_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
            ]))
            elements.append(sig_table)

            elements.append(Spacer(1, 20))
            elements.append(Paragraph(f"Generated on {datetime.now().strftime('%d/%m/%Y at %H:%M:%S')}", footer_style))

        _finalize(doc, elements, hospital_info, header_cb=_draw_header)
        buffer.seek(0)
        return buffer

    def generate_discharge_summary_pdf(
        self,
        discharge_data,
        hospital_info,
        include_header=True,
        letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT,
        watermark=None,
        template=None,
    ):
        """Generate PDF for discharge summary from a hospital layout template."""
        from app.services.discharge_summary_template_service import (
            build_default_template,
            standard_section_content,
            validate_template,
        )

        if template is None:
            template = build_default_template()
        else:
            try:
                template = validate_template(template)
            except ValueError:
                template = build_default_template()

        buffer = BytesIO()

        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=30,
            leftMargin=30,
            topMargin=30,
            bottomMargin=20
        )

        elements = []
        page_width = A4[0] - 60  # total usable width

        # --- Styles (black & white, consistent with bill PDF) ---
        title_style = ParagraphStyle('DischTitle', parent=self.styles['Title'],
            fontSize=16, alignment=1, fontName='Helvetica-Bold',
            textColor=colors.black, spaceAfter=2)

        subtitle_style = ParagraphStyle('DischSubtitle', parent=self.styles['Normal'],
            fontSize=9, alignment=1, fontName='Helvetica',
            textColor=colors.black, spaceAfter=2)

        doc_title_style = ParagraphStyle('DischDocTitle', parent=self.styles['Normal'],
            fontSize=13, alignment=1, fontName='Helvetica-Bold',
            textColor=colors.black, spaceAfter=4)

        section_heading = ParagraphStyle('DischSection', parent=self.styles['Heading2'],
            fontSize=11, fontName='Helvetica-Bold', textColor=colors.black,
            spaceAfter=4, spaceBefore=8)

        cell_value = ParagraphStyle('DischCellValue', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica', textColor=colors.black, spaceAfter=2)

        footer_style = ParagraphStyle('DischFooter', parent=self.styles['Normal'],
            fontSize=7, fontName='Helvetica-Oblique', textColor=colors.grey,
            alignment=1)

        def lv(label, value):
            return Paragraph(
                f"<b>{_escape_pdf_inline(label)}:</b> {_escape_pdf_inline(value)}",
                cell_value,
            )

        def _append_section(title, content):
            if not content or not str(content).strip():
                return
            elements.append(Paragraph(_escape_pdf_inline(title), section_heading))
            for line in str(content).split('\n'):
                line = line.strip()
                if line:
                    elements.append(Paragraph(_escape_pdf_inline(line), cell_value))

        # ============================================================
        # HEADER: Hospital Name + Logo + Address
        # ============================================================
        if include_header:
            logo_path = hospital_info.get('logo_url', '')
            uploads_base = _get_uploads_base()
            has_logo = False
            full_logo_path = ''
            if logo_path:
                relative = logo_path.lstrip('/')
                if relative.startswith('uploads/'):
                    relative = relative[len('uploads/'):]
                full_logo_path = os.path.join(uploads_base, relative)
                has_logo = os.path.exists(full_logo_path)

            hospital_name = hospital_info.get('name', 'HOSPITAL').upper()
            hospital_subname = hospital_info.get('hospital_subname', '')
            address = hospital_info.get('address', '')
            contact_parts = []
            if hospital_info.get('email'):
                contact_parts.append(f"Email: {hospital_info['email']}")
            if hospital_info.get('phone'):
                contact_parts.append(f"Phone: {hospital_info['phone']}")

            header_text_elems = [Paragraph(_escape_pdf_inline(hospital_name), title_style)]
            if hospital_subname:
                header_text_elems.append(Paragraph(_escape_pdf_inline(hospital_subname), subtitle_style))
            if address:
                header_text_elems.append(Paragraph(_escape_pdf_inline(address), subtitle_style))
            if contact_parts:
                header_text_elems.append(Paragraph(
                    _escape_pdf_inline("  |  ".join(contact_parts)), subtitle_style))

            if has_logo:
                try:
                    logo_img = Image(full_logo_path, width=60, height=60)
                    logo_img.hAlign = 'CENTER'
                    header_table = Table([[logo_img, header_text_elems]], colWidths=[75, page_width - 75])
                    header_table.setStyle(TableStyle([
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 0),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                        ('TOPPADDING', (0, 0), (-1, -1), 0),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                    ]))
                    elements.append(header_table)
                except Exception:
                    for el in header_text_elems:
                        elements.append(el)
            else:
                for el in header_text_elems:
                    elements.append(el)

            elements.append(Spacer(1, 6))
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        else:
            elements.append(Spacer(1, letterhead_gap_pt))

        doc_title = (template.get("document_title") or "DISCHARGE SUMMARY").strip() or "DISCHARGE SUMMARY"
        elements.append(Spacer(1, 4))
        elements.append(Paragraph(_escape_pdf_inline(doc_title), doc_title_style))
        if template.get("show_department_line", True):
            dept_name = (discharge_data.get('department_name') or '').strip()
            if dept_name:
                dept_style = ParagraphStyle('DischDept', parent=subtitle_style,
                    fontSize=10, fontName='Helvetica-Bold', alignment=1, spaceAfter=2)
                elements.append(Paragraph(
                    f"DEPARTMENT OF {_escape_pdf_inline(dept_name.upper())}", dept_style))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        elements.append(Spacer(1, 6))

        col_w = page_width / 2
        custom_fields = discharge_data.get("custom_fields") or {}
        if isinstance(custom_fields, str):
            try:
                custom_fields = json.loads(custom_fields) if custom_fields.strip() else {}
            except (json.JSONDecodeError, TypeError):
                custom_fields = {}
        if not isinstance(custom_fields, dict):
            custom_fields = {}

        rendered_standard = False

        for block in template.get("blocks") or []:
            btype = block.get("type")

            if btype == "patient_info":
                age_gender = _age_gender_str(
                    discharge_data, gender=discharge_data.get('gender', ''), age_key='age')
                bed_room = discharge_data.get('bed_label', '')
                if bed_room and discharge_data.get('room_number'):
                    bed_room = f"{bed_room} / {discharge_data.get('room_number', '')}"
                elif discharge_data.get('room_number'):
                    bed_room = discharge_data.get('room_number', '')

                payer_label = discharge_data.get('payer_label') or 'Cash / Self Pay'
                discharge_type_label = _discharge_type_label(discharge_data.get('discharge_type', ''))

                patient_info_data = [
                    [lv('Patient Name', discharge_data.get('patient_name', '')),
                     lv('UHID', discharge_data.get('mrn', ''))],
                    [lv('Age / Sex', age_gender),
                     lv('Phone No.', discharge_data.get('patient_phone', ''))],
                    [lv('Admission No.', discharge_data.get('admission_number', '')),
                     lv('Admission Date', discharge_data.get('admission_date', ''))],
                    [lv('Bed / Room No.', bed_room),
                     lv('Ward Type', discharge_data.get('ward_type', ''))],
                    [lv('Discharge Date', discharge_data.get('discharge_date', '') or '—'),
                     lv('Date of Surgery', discharge_data.get('surgery_date', '') or '—')],
                    [lv('Payer / Scheme', payer_label),
                     lv('Discharge Type', discharge_type_label)],
                ]
                info_style = [
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING', (0, 0), (-1, -1), 3),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                    ('LEFTPADDING', (0, 0), (-1, -1), 8),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                    ('BOX', (0, 0), (-1, -1), 1, colors.black),
                ]
                _append_address_row(patient_info_data, info_style, discharge_data, lv)
                info_table = Table(patient_info_data, colWidths=[col_w, col_w])
                info_table.setStyle(TableStyle(info_style))
                elements.append(info_table)
                elements.append(Spacer(1, 8))

            elif btype == "consultants":
                consultants = discharge_data.get('consultants') or []
                if not consultants and discharge_data.get('doctor_name'):
                    consultants = [{
                        'display_line': discharge_data.get('doctor_name', ''),
                        'name': discharge_data.get('doctor_name', ''),
                    }]
                if consultants:
                    label = block.get("label") or "Chief Consultant(s)"
                    elements.append(Paragraph(_escape_pdf_inline(label), section_heading))
                    for c in consultants:
                        line = c.get('display_line') or c.get('name', '')
                        if line:
                            elements.append(Paragraph(_escape_pdf_inline(line), cell_value))
                    if discharge_data.get('secondary_doctor_name') and not any(
                        discharge_data.get('secondary_doctor_name') in (c.get('name') or '')
                        for c in consultants
                    ):
                        sdept = discharge_data.get('secondary_doctor_department', '')
                        sec = discharge_data.get('secondary_doctor_name', '')
                        if sdept:
                            sec = f"{sec} ({sdept})"
                        elements.append(Paragraph(_escape_pdf_inline(sec), cell_value))
                    elements.append(Spacer(1, 6))

            elif btype == "standard_section":
                content = standard_section_content(discharge_data, block.get("field_key") or "")
                if content and str(content).strip():
                    rendered_standard = True
                _append_section(block.get("label") or block.get("field_key") or "", content)

            elif btype == "custom_field":
                field_key = block.get("field_key") or ""
                content = custom_fields.get(field_key) or ""
                _append_section(block.get("label") or field_key, content)

            elif btype == "static_text":
                label = (block.get("label") or "").strip()
                content = block.get("content") or ""
                if label:
                    elements.append(Paragraph(_escape_pdf_inline(label), section_heading))
                for line in str(content).split('\n'):
                    line = line.strip()
                    if line:
                        elements.append(Paragraph(_escape_pdf_inline(line), cell_value))

            elif btype == "medications_table":
                med_label = block.get("label") or "Take-Home Medications"
                take_home = discharge_data.get("take_home_medications") or []
                if take_home:
                    elements.append(Paragraph(_escape_pdf_inline(med_label), section_heading))
                    header = ['S.No', 'Description', 'Dose', 'Route', 'Timings', 'Duration']
                    rows = [header]
                    for i, m in enumerate(take_home, start=1):
                        rows.append([
                            str(i),
                            str(m.get('medicine_name') or ''),
                            str(m.get('dosage') or '—'),
                            _med_route_display(m),
                            _med_timings_display(m),
                            str(m.get('duration') or '—'),
                        ])
                    med_table = Table(rows, colWidths=[28, 130, 62, 52, 118, 65])
                    med_table.setStyle(TableStyle([
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, -1), 8),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 3),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
                        ('TOPPADDING', (0, 0), (-1, -1), 3),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                    ]))
                    elements.append(med_table)
                    elements.append(Spacer(1, 4))
                else:
                    medications = discharge_data.get("medications", "")
                    if medications:
                        elements.append(Paragraph("Medications Prescribed", section_heading))
                        med_lines = [
                            m.strip()
                            for m in medications.replace(';', '\n').split('\n')
                            if m.strip()
                        ]
                        if len(med_lines) > 1:
                            for med in med_lines:
                                bullet = med if med.startswith(('•', '-', '*')) else f"• {med}"
                                elements.append(Paragraph(_escape_pdf_inline(bullet), cell_value))
                        else:
                            elements.append(Paragraph(_escape_pdf_inline(medications), cell_value))

            elif btype == "follow_up":
                follow_up = discharge_data.get("follow_up", "")
                follow_up_date = discharge_data.get("follow_up_date", "")
                emergency = discharge_data.get("emergency_instructions", "")
                diet = discharge_data.get("diet_instructions", "")
                activity = discharge_data.get("activity_restrictions", "")
                if follow_up or follow_up_date or emergency or diet or activity:
                    elements.append(Paragraph(
                        _escape_pdf_inline(block.get("label") or "Review / Follow-up"),
                        section_heading))
                    if follow_up:
                        elements.append(Paragraph(_escape_pdf_inline(follow_up), cell_value))
                    if follow_up_date:
                        elements.append(Paragraph(
                            f"<b>Follow-up Date:</b> {_escape_pdf_inline(follow_up_date)}",
                            cell_value))
                    if emergency:
                        elements.append(Paragraph(
                            f"<b>Emergency — seek care if:</b> {_escape_pdf_inline(emergency)}",
                            cell_value))
                    if diet:
                        elements.append(Paragraph(
                            f"<b>Diet:</b> {_escape_pdf_inline(diet)}", cell_value))
                    if activity:
                        elements.append(Paragraph(
                            f"<b>Activity Restrictions:</b> {_escape_pdf_inline(activity)}",
                            cell_value))

            elif btype == "condition_on_discharge":
                elements.append(Spacer(1, 16))
                condition_discharge = discharge_data.get("condition_on_discharge", "")
                if condition_discharge:
                    elements.append(Paragraph(
                        f"<b>Condition on Discharge:</b> {_escape_pdf_inline(condition_discharge)}",
                        cell_value))
                    elements.append(Spacer(1, 12))

            elif btype == "signatures":
                doctor_name = (
                    discharge_data.get("consultant_name") or discharge_data.get("doctor_name", "")
                )
                sig_label_style = ParagraphStyle(
                    'SigLabel', parent=self.styles['Normal'],
                    fontSize=8, fontName='Helvetica', textColor=colors.grey, alignment=1)
                sig_line_style = ParagraphStyle(
                    'SigLine', parent=self.styles['Normal'], fontSize=9, alignment=1)
                sig_name_style = ParagraphStyle(
                    'SigName', parent=self.styles['Normal'],
                    fontSize=9, fontName='Helvetica-Bold', alignment=1)
                sig_data = [
                    [Paragraph('_' * 28, sig_line_style), Paragraph('_' * 28, sig_line_style)],
                    [Paragraph("Resident", sig_label_style), Paragraph("Consultant", sig_label_style)],
                    [Paragraph('', cell_value),
                     Paragraph(
                         f"<b>{_escape_pdf_inline(doctor_name)}</b>" if doctor_name else '',
                         sig_name_style)],
                ]
                sig_table = Table(sig_data, colWidths=[page_width / 2, page_width / 2])
                sig_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
                    ('TOPPADDING', (0, 0), (-1, -1), 2),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ]))
                elements.append(sig_table)
                elements.append(Spacer(1, 14))

            elif btype == "acknowledgement":
                ack_style = ParagraphStyle('AckText', parent=cell_value, fontSize=8, leading=10)
                elements.append(Paragraph(
                    "I acknowledge that I have been explained in my understandable language about the "
                    "post-discharge care instructions, the medications, the diet to be taken at home "
                    "and when to obtain urgent care (if needed).",
                    ack_style,
                ))
                ack_rows = [
                    [lv('Name', '_' * 40), lv('Signature', '_' * 40)],
                    [lv('If by attendant, relationship', '_' * 40), ''],
                ]
                ack_table = Table(ack_rows, colWidths=[col_w, col_w])
                ack_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ]))
                elements.append(ack_table)
                elements.append(Spacer(1, 10))
                elements.append(Paragraph("Discharge Summary Explained by", section_heading))
                explained_rows = [
                    [lv('Clinical Pharmacist', '_' * 35), lv('DMO / Incharge Sister', '_' * 35)],
                ]
                explained_table = Table(explained_rows, colWidths=[col_w, col_w])
                explained_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ]))
                elements.append(explained_table)

        # Legacy free-text fallback when no structured section content was rendered
        if not rendered_standard and not any(
            (custom_fields.get(b.get("field_key")) or "")
            for b in (template.get("blocks") or [])
            if b.get("type") == "custom_field"
        ):
            for title, key in (
                ("Diagnosis", "diagnosis"),
                ("Treatment Given", "treatment"),
                ("Discharge Summary", "discharge_summary"),
            ):
                _append_section(title, discharge_data.get(key, ""))

        elements.append(Spacer(1, 20))
        elements.append(Paragraph(
            f"Generated on {datetime.now().strftime('%d/%m/%Y at %H:%M:%S')}",
            footer_style
        ))

        patient_hdr = f"{discharge_data.get('patient_name', '')} / {discharge_data.get('admission_number', '')}".strip(' /')
        def _page_cb(canvas_obj, doc):
            _discharge_running_header(canvas_obj, doc, patient_hdr)

        _finalize(doc, elements, hospital_info, header_cb=_page_cb, watermark=watermark)
        buffer.seek(0)
        return buffer

    def generate_admission_detail_pdf(self, payload, hospital_info, include_header=True, letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT):
        """Detailed Admission Summary — auto-aggregated clinical dossier for a stay."""
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=30,
            leftMargin=30,
            topMargin=30,
            bottomMargin=20,
        )
        elements = []
        page_width = A4[0] - 60
        meta = payload.get("admission_meta") or {}

        title_style = ParagraphStyle('AdmDetTitle', parent=self.styles['Title'],
            fontSize=16, alignment=1, fontName='Helvetica-Bold',
            textColor=colors.black, spaceAfter=2)
        subtitle_style = ParagraphStyle('AdmDetSubtitle', parent=self.styles['Normal'],
            fontSize=9, alignment=1, fontName='Helvetica',
            textColor=colors.black, spaceAfter=2)
        doc_title_style = ParagraphStyle('AdmDetDocTitle', parent=self.styles['Normal'],
            fontSize=13, alignment=1, fontName='Helvetica-Bold',
            textColor=colors.black, spaceAfter=4)
        section_heading = ParagraphStyle('AdmDetSection', parent=self.styles['Heading2'],
            fontSize=11, fontName='Helvetica-Bold', textColor=colors.black,
            spaceAfter=4, spaceBefore=8)
        cell_value = ParagraphStyle('AdmDetCell', parent=self.styles['Normal'],
            fontSize=8, fontName='Helvetica', textColor=colors.black, spaceAfter=1, leading=10)
        cell_bold = ParagraphStyle('AdmDetCellBold', parent=cell_value, fontName='Helvetica-Bold')
        footer_style = ParagraphStyle('AdmDetFooter', parent=self.styles['Normal'],
            fontSize=7, fontName='Helvetica-Oblique', textColor=colors.grey, alignment=1)

        def lv(label, value):
            return Paragraph(f"<b>{label}:</b> {value}", cell_value)

        def _str(v):
            if v is None or v == "":
                return "—"
            return str(v)

        def _add_table(headers, rows, col_widths=None):
            if not rows:
                return
            data = [headers] + rows
            if not col_widths:
                n = len(headers)
                col_widths = [page_width / n] * n
            tbl = Table(data, colWidths=col_widths, repeatRows=1)
            tbl.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 7),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 3),
                ('RIGHTPADDING', (0, 0), (-1, -1), 3),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ]))
            elements.append(tbl)
            elements.append(Spacer(1, 4))

        if include_header:
            logo_path = hospital_info.get('logo_url', '')
            uploads_base = _get_uploads_base()
            has_logo = False
            full_logo_path = ''
            if logo_path:
                relative = logo_path.lstrip('/')
                if relative.startswith('uploads/'):
                    relative = relative[len('uploads/'):]
                full_logo_path = os.path.join(uploads_base, relative)
                has_logo = os.path.exists(full_logo_path)

            hospital_name = hospital_info.get('name', 'HOSPITAL').upper()
            header_text_elems = [Paragraph(hospital_name, title_style)]
            if hospital_info.get('hospital_subname'):
                header_text_elems.append(Paragraph(hospital_info['hospital_subname'], subtitle_style))
            if hospital_info.get('address'):
                header_text_elems.append(Paragraph(hospital_info['address'], subtitle_style))
            contact_parts = []
            if hospital_info.get('email'):
                contact_parts.append(f"Email: {hospital_info['email']}")
            if hospital_info.get('phone'):
                contact_parts.append(f"Phone: {hospital_info['phone']}")
            if contact_parts:
                header_text_elems.append(Paragraph("  |  ".join(contact_parts), subtitle_style))

            if has_logo:
                try:
                    logo_img = Image(full_logo_path, width=60, height=60)
                    logo_img.hAlign = 'CENTER'
                    header_table = Table([[logo_img, header_text_elems]], colWidths=[75, page_width - 75])
                    header_table.setStyle(TableStyle([
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 0),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                    ]))
                    elements.append(header_table)
                except Exception:
                    for el in header_text_elems:
                        elements.append(el)
            else:
                for el in header_text_elems:
                    elements.append(el)
            elements.append(Spacer(1, 6))
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        else:
            elements.append(Spacer(1, letterhead_gap_pt))

        elements.append(Spacer(1, 4))
        elements.append(Paragraph("DETAILED ADMISSION SUMMARY", doc_title_style))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        elements.append(Spacer(1, 6))

        age_gender = _age_gender_str(meta, gender=meta.get('gender', ''), age_key='age')
        col_w = page_width / 2
        patient_info_data = [
            [lv('Patient', meta.get('patient_name', '')),
             lv('MRN', meta.get('mrn', ''))],
            [lv('Age / Gender', age_gender),
             lv('Doctor', meta.get('doctor_name', ''))],
            [lv('Admission No', meta.get('admission_number', '')),
             lv('Stay', f"{meta.get('stay_days', 0)} days")],
            [lv('Admitted', meta.get('admission_date', '')),
             lv('Discharged', meta.get('discharge_date', '') or '— (in progress)')],
            [lv('Room / Bed', f"{meta.get('room_number', '')} / {meta.get('bed_label', '')}"),
             lv('Status', meta.get('status', ''))],
        ]
        info_style = [
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ]
        _append_address_row(patient_info_data, info_style, meta, lv)
        info_table = Table(patient_info_data, colWidths=[col_w, col_w])
        info_table.setStyle(TableStyle(info_style))
        elements.append(info_table)
        elements.append(Spacer(1, 8))

        visits = payload.get('visits') or []
        if visits:
            elements.append(Paragraph("Doctor Visits &amp; Rounds", section_heading))
            for v in visits:
                elements.append(Paragraph(
                    f"<b>{v.get('visit_datetime', '')}</b> — {v.get('visitor_name', '')} "
                    f"({v.get('visit_type', '').replace('_', ' ')})",
                    cell_bold,
                ))
                if v.get('plan_for_today'):
                    elements.append(Paragraph(f"Plan: {v['plan_for_today']}", cell_value))
                if v.get('notes'):
                    elements.append(Paragraph(v['notes'], cell_value))
                elements.append(Spacer(1, 3))

        vitals = payload.get('vitals') or []
        if vitals:
            elements.append(Paragraph("Vitals Record", section_heading))
            v_headers = ['Date/Time', 'BP', 'HR', 'RR', 'Temp', 'SpO2', 'Glucose', 'Pain', 'GCS', 'Flags']
            v_rows = []
            for v in vitals:
                v_rows.append([
                    _str(v.get('recorded_at')),
                    _str(v.get('bp')),
                    _str(v.get('heart_rate')),
                    _str(v.get('respiratory_rate')),
                    _str(v.get('temperature_c')),
                    _str(v.get('spo2')),
                    _str(v.get('blood_glucose')),
                    _str(v.get('pain_score')),
                    _str(v.get('gcs_score')),
                    _str(v.get('abnormal_flags') or ('Abnormal' if v.get('is_abnormal') else '')),
                ])
            _add_table(v_headers, v_rows, [62, 38, 28, 28, 32, 28, 38, 28, 28, 50])

        meds = payload.get('inpatient_medications') or []
        if meds:
            elements.append(Paragraph("Medications Prescribed (Inpatient)", section_heading))
            m_headers = ['Date', 'Medicine', 'Dosage', 'Frequency', 'Route', 'Duration', 'PRN', 'Prescriber']
            m_rows = []
            for m in meds:
                m_rows.append([
                    _str(m.get('prescription_date')),
                    _str(m.get('medicine_name')),
                    _str(m.get('dosage')),
                    _str(m.get('frequency')),
                    _str(m.get('route')),
                    _str(m.get('duration')),
                    'Yes' if m.get('is_prn') else 'No',
                    _str(m.get('prescriber')),
                ])
            _add_table(m_headers, m_rows, [52, 85, 45, 55, 35, 45, 25, 70])

        if payload.get('mar_included', True):
            mar = payload.get('mar') or []
            if mar:
                elements.append(Paragraph("Medication Administration Record", section_heading))
                mar_headers = ['Scheduled', 'Medicine', 'Dosage', 'Status', 'Given At', 'Dose', 'Route', 'By', 'Notes']
                mar_rows = []
                for m in mar:
                    note_parts = [m.get('reason_if_not_given', ''), m.get('notes', '')]
                    note_txt = '; '.join(p for p in note_parts if p)
                    mar_rows.append([
                        _str(m.get('scheduled_time')),
                        _str(m.get('medicine_name')),
                        _str(m.get('dosage')),
                        _str(m.get('status')),
                        _str(m.get('administered_at')),
                        _str(m.get('dose_given')),
                        _str(m.get('route')),
                        _str(m.get('administered_by_name')),
                        _str(note_txt),
                    ])
                _add_table(mar_headers, mar_rows, [48, 72, 40, 38, 48, 32, 32, 52, 60])
        else:
            elements.append(Paragraph("Medication Administration Record", section_heading))
            elements.append(Paragraph(
                "MAR not included — insufficient permission to view medication administration records.",
                cell_value,
            ))

        ot_list = payload.get('ot_procedures') or []
        anc_list = payload.get('ancillary_procedures') or []
        if ot_list or anc_list:
            elements.append(Paragraph("Procedures &amp; Surgery", section_heading))
            if ot_list:
                ot_headers = ['Date', 'Procedure', 'Surgeon', 'Room', 'Status', 'Notes']
                ot_rows = []
                for p in ot_list:
                    notes = ' '.join(x for x in [p.get('pre_op_notes', ''), p.get('post_op_notes', '')] if x)
                    ot_rows.append([
                        _str(p.get('scheduled_date')),
                        _str(p.get('procedure_name')),
                        _str(p.get('surgeon_name')),
                        _str(p.get('ot_room')),
                        _str(p.get('status')),
                        _str(notes),
                    ])
                _add_table(ot_headers, ot_rows, [48, 90, 65, 35, 45, 90])
            if anc_list:
                elements.append(Paragraph("Ancillary Services", cell_bold))
                a_headers = ['Date', 'Service', 'Category', 'Qty', 'Performed By', 'Notes']
                a_rows = []
                for p in anc_list:
                    a_rows.append([
                        _str(p.get('charged_at')),
                        _str(p.get('procedure_name')),
                        _str(p.get('category')),
                        _str(p.get('quantity')),
                        _str(p.get('performed_by_name')),
                        _str(p.get('notes')),
                    ])
                _add_table(a_headers, a_rows, [48, 90, 55, 28, 65, 90])

        investigations = payload.get('investigations') or []
        if investigations:
            elements.append(Paragraph("Investigations", section_heading))
            for inv in investigations:
                elements.append(Paragraph(
                    f"<b>{inv.get('test_name', '')}</b> — {inv.get('order_number', '')} "
                    f"({inv.get('status', '')}) · Ordered {inv.get('order_date', '')}",
                    cell_bold,
                ))
                results = inv.get('results') or []
                if results:
                    r_headers = ['Parameter', 'Value', 'Unit', 'Flag']
                    r_rows = []
                    for r in results:
                        r_rows.append([
                            _str(r.get('parameter_name')),
                            _str(r.get('value')),
                            _str(r.get('unit')),
                            'Abnormal' if r.get('is_abnormal') else '',
                        ])
                    _add_table(r_headers, r_rows, [120, 80, 50, 50])
                else:
                    elements.append(Paragraph("No verified results on file.", cell_value))
                elements.append(Spacer(1, 4))

        notes = payload.get('nursing_notes') or []
        if notes:
            elements.append(Paragraph("Nursing Notes", section_heading))
            for n in notes:
                elements.append(Paragraph(
                    f"<b>{n.get('created_at', '')}</b> — {n.get('nurse_name', '')} "
                    f"({n.get('shift', '')} / {n.get('note_type', '')})",
                    cell_bold,
                ))
                if n.get('content'):
                    for line in str(n['content']).split('\n'):
                        line = line.strip()
                        if line:
                            elements.append(Paragraph(line, cell_value))
                elements.append(Spacer(1, 3))

        elements.append(Spacer(1, 16))
        elements.append(Paragraph(
            f"Generated on {datetime.now().strftime('%d/%m/%Y at %H:%M:%S')}",
            footer_style,
        ))
        _finalize(doc, elements, hospital_info)
        buffer.seek(0)
        return buffer

    def generate_deposit_receipt_pdf(self, deposit_data, hospital_info, include_header=True, letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT):
        """Advance deposit / refund receipt — mirrors the OPD bill layout
        (logo+hospital header, bordered patient/receipt info box, single-line
        item table, payment summary, amount-in-words, prepared-by footer)."""
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=20,
        )
        elements = []
        page_width = A4[0] - 60

        title_style = ParagraphStyle('DRTitle', parent=self.styles['Title'],
            fontSize=16, alignment=1, fontName='Helvetica-Bold',
            textColor=colors.black, spaceAfter=2)
        subtitle_style = ParagraphStyle('DRSubtitle', parent=self.styles['Normal'],
            fontSize=9, alignment=1, fontName='Helvetica',
            textColor=colors.black, spaceAfter=2)
        receipt_title_style = ParagraphStyle('DRReceiptTitle', parent=self.styles['Normal'],
            fontSize=12, alignment=1, fontName='Helvetica-Bold',
            textColor=colors.black, spaceAfter=4)
        cell_label = ParagraphStyle('DRCellLabel', parent=self.styles['Normal'],
            fontSize=8, fontName='Helvetica-Bold', textColor=colors.black)
        cell_value = ParagraphStyle('DRCellValue', parent=self.styles['Normal'],
            fontSize=8, fontName='Helvetica', textColor=colors.black)
        cell_value_sm = ParagraphStyle('DRCellValueSm', parent=self.styles['Normal'],
            fontSize=7, fontName='Helvetica', textColor=colors.black)
        cell_value_right = ParagraphStyle('DRCellValueRight', parent=cell_value_sm, alignment=2)

        def lv(label, value):
            return Paragraph(f"<b>{label}</b> :  {value}", cell_value)

        def lv_sm(label, value):
            return Paragraph(f"<b>{label}</b> :  {value}", cell_value_sm)

        is_refund = deposit_data.get('deposit_type') == 'refund'
        amount = float(deposit_data.get('amount', 0))
        receipt_no = deposit_data.get('deposit_number', '')
        receipt_date = deposit_data.get('received_at', '') or datetime.now().strftime('%d/%m/%Y %H:%M')

        # ============================================================
        # HEADER — identical to generate_bill_pdf
        # ============================================================
        if include_header:
            logo_path = hospital_info.get('logo_url', '')
            uploads_base = _get_uploads_base()
            has_logo = False
            full_logo_path = ''
            if logo_path:
                relative = logo_path.lstrip('/')
                if relative.startswith('uploads/'):
                    relative = relative[len('uploads/'):]
                full_logo_path = os.path.join(uploads_base, relative)
                has_logo = os.path.exists(full_logo_path)

            hospital_name = hospital_info.get('name', 'HOSPITAL').upper()
            hospital_subname = hospital_info.get('hospital_subname', '')
            address = hospital_info.get('address', '')
            contact_parts = []
            if hospital_info.get('email'):
                contact_parts.append(f"Email: {hospital_info['email']}")
            if hospital_info.get('phone'):
                contact_parts.append(f"Phone: {hospital_info['phone']}")

            header_text_elems = [Paragraph(hospital_name, title_style)]
            if hospital_subname:
                header_text_elems.append(Paragraph(hospital_subname, subtitle_style))
            if address:
                header_text_elems.append(Paragraph(address, subtitle_style))
            if contact_parts:
                header_text_elems.append(Paragraph("  |  ".join(contact_parts), subtitle_style))

            if has_logo:
                try:
                    logo_img = Image(full_logo_path, width=60, height=60)
                    logo_img.hAlign = 'CENTER'
                    header_table = Table([[logo_img, header_text_elems]], colWidths=[75, page_width - 75])
                    header_table.setStyle(TableStyle([
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 0),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                        ('TOPPADDING', (0, 0), (-1, -1), 0),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                    ]))
                    elements.append(header_table)
                except Exception:
                    for el in header_text_elems:
                        elements.append(el)
            else:
                for el in header_text_elems:
                    elements.append(el)

            elements.append(Spacer(1, 6))
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        else:
            elements.append(Spacer(1, letterhead_gap_pt))

        elements.append(Spacer(1, 4))
        elements.append(Paragraph(
            "REFUND RECEIPT" if is_refund else "ADVANCE DEPOSIT RECEIPT",
            receipt_title_style,
        ))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        elements.append(Spacer(1, 6))

        # ============================================================
        # PATIENT + RECEIPT INFO — bordered box, two-column
        # ============================================================
        deposit_type_label = str(deposit_data.get('deposit_type', '')).title() or '-'
        pay_method = str(deposit_data.get('payment_method', '')).title() or 'Cash'
        col_w = page_width / 2
        info_data = [
            [lv('Name', deposit_data.get('patient_name', '')),
             lv('Receipt No', receipt_no)],
            [lv('Phone', deposit_data.get('patient_phone', '')),
             lv('Date', receipt_date)],
            [lv('MRN', deposit_data.get('mrn', '')),
             lv('Address', _patient_address_line(deposit_data))],
            [lv('Admission No', deposit_data.get('admission_number', '')),
             lv('Pay Mode', pay_method)],
            [lv('Type', deposit_type_label),
             lv('Reference', deposit_data.get('reference_number') or '-')],
        ]
        info_style = [
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ]
        info_table = Table(info_data, colWidths=[col_w, col_w])
        info_table.setStyle(TableStyle(info_style))
        elements.append(info_table)
        elements.append(Spacer(1, 6))

        # ============================================================
        # ITEMS — single row describing the deposit
        # ============================================================
        sno_w = 0.4 * inch
        code_w = 1.0 * inch
        rate_w = 1.0 * inch
        desc_w = page_width - sno_w - code_w - rate_w

        item_description = (
            "Refund of advance deposit" if is_refund
            else f"Advance deposit — {deposit_type_label} ({pay_method})"
        )
        items_data = [
            [Paragraph('<b>Sno</b>', cell_label),
             Paragraph('<b>Description</b>', cell_label),
             Paragraph('<b>Code</b>', cell_label),
             Paragraph('<b>Amount</b>', cell_label)],
            [Paragraph('1', cell_value),
             Paragraph(item_description, cell_value),
             Paragraph(receipt_no, cell_value),
             Paragraph(f"{abs(amount):.2f}", cell_value)],
        ]
        items_table = Table(items_data, colWidths=[sno_w, desc_w, code_w, rate_w])
        items_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
        ]))
        elements.append(items_table)
        elements.append(Spacer(1, 6))

        # ============================================================
        # PAYMENT SUMMARY — right aligned, mirrors bill layout
        # ============================================================
        paid_label = 'Refunded Amt' if is_refund else 'Received Amt'
        summary_label_w = page_width - code_w - rate_w
        payment_data = [
            [lv_sm('Paymode', pay_method),
             Paragraph('<b>Total Amt</b>', cell_value_sm),
             Paragraph(f"{abs(amount):.2f}", cell_value_right)],
            [Paragraph('', cell_value_sm),
             Paragraph(f"<b>{paid_label}</b>", cell_value_sm),
             Paragraph(f"{abs(amount):.2f}", cell_value_right)],
            [Paragraph('', cell_value_sm),
             Paragraph('<b>Balance</b>', cell_value_sm),
             Paragraph("0.00", cell_value_right)],
        ]
        payment_table = Table(payment_data, colWidths=[summary_label_w, code_w, rate_w])
        payment_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(payment_table)
        elements.append(Spacer(1, 4))

        # ----- Amount in words (same inline routine as generate_bill_pdf) -----
        def _amount_to_words(num):
            try:
                ones = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven',
                        'Eight', 'Nine', 'Ten', 'Eleven', 'Twelve', 'Thirteen',
                        'Fourteen', 'Fifteen', 'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen']
                tens = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty',
                        'Sixty', 'Seventy', 'Eighty', 'Ninety']
                num = int(num)
                if num == 0:
                    return "Zero"
                def two(n):
                    return ones[n] if n < 20 else tens[n // 10] + ((' ' + ones[n % 10]) if n % 10 else '')
                def three(n):
                    if n >= 100:
                        return ones[n // 100] + ' Hundred' + (' and ' + two(n % 100) if n % 100 else '')
                    return two(n)
                parts = []
                if num >= 10000000:
                    parts.append(two(num // 10000000) + ' Crore'); num %= 10000000
                if num >= 100000:
                    parts.append(two(num // 100000) + ' Lakh'); num %= 100000
                if num >= 1000:
                    parts.append(two(num // 1000) + ' Thousand'); num %= 1000
                if num > 0:
                    parts.append(three(num))
                return ' '.join(parts) + ' Only'
            except Exception:
                return str(num)

        words_text = f"Rupees {_amount_to_words(abs(amount))}"
        words_data = [[lv('In words', words_text)]]
        words_table = Table(words_data, colWidths=[page_width])
        words_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(words_table)
        elements.append(Spacer(1, 8))

        # Notes (optional)
        if deposit_data.get('notes'):
            elements.append(Paragraph(f"<b>Notes:</b> {deposit_data['notes']}", cell_value))
            elements.append(Spacer(1, 8))

        # ============================================================
        # FOOTER — prepared by / printed by (matches bill PDF)
        # ============================================================
        received_by_name = deposit_data.get('received_by_name', '-') or '-'
        footer_data = [[
            lv('Prepared by', received_by_name),
            lv('Printed by', received_by_name),
        ]]
        footer_table = Table(footer_data, colWidths=[page_width / 2, page_width / 2])
        footer_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(footer_table)
        elements.append(Spacer(1, 4))
        elements.append(Paragraph(
            f"Generated on {datetime.now().strftime('%d/%m/%Y at %H:%M:%S')}",
            ParagraphStyle('DRFootMeta', parent=self.styles['Normal'],
                fontSize=7, fontName='Helvetica-Oblique', alignment=1, textColor=colors.grey),
        ))

        _finalize(doc, elements, hospital_info)
        buffer.seek(0)
        return buffer

    def generate_refund_receipt_pdf(self, refund_data, hospital_info, include_header=True, letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT):
        """Refund receipt for a reversed bill payment (Payment row with negative amount)."""
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            rightMargin=40, leftMargin=40, topMargin=30, bottomMargin=30,
        )
        elements = []
        page_width = A4[0] - 80

        title_style = ParagraphStyle('Title', parent=self.styles['Title'],
            fontSize=15, alignment=1, fontName='Helvetica-Bold', textColor=colors.black, spaceAfter=4)
        sub_style = ParagraphStyle('Sub', parent=self.styles['Normal'],
            fontSize=9, alignment=1, fontName='Helvetica', textColor=colors.black, spaceAfter=2)
        receipt_title_style = ParagraphStyle('RT', parent=self.styles['Normal'],
            fontSize=12, alignment=1, fontName='Helvetica-Bold', textColor=colors.red, spaceAfter=6)
        label_style = ParagraphStyle('Label', parent=self.styles['Normal'],
            fontSize=10, fontName='Helvetica-Bold', textColor=colors.black)
        value_style = ParagraphStyle('Value', parent=self.styles['Normal'],
            fontSize=10, fontName='Helvetica', textColor=colors.black)
        amount_style = ParagraphStyle('Amount', parent=self.styles['Normal'],
            fontSize=14, fontName='Helvetica-Bold', alignment=1, textColor=colors.red, spaceAfter=4)
        footer_style = ParagraphStyle('Footer', parent=self.styles['Normal'],
            fontSize=8, alignment=1, fontName='Helvetica', textColor=colors.black)

        if include_header:
            elements.append(Paragraph(hospital_info.get('name', 'HOSPITAL').upper(), title_style))
            if hospital_info.get('address'):
                elements.append(Paragraph(hospital_info['address'], sub_style))
            contact = []
            if hospital_info.get('phone'): contact.append(f"Phone: {hospital_info['phone']}")
            if hospital_info.get('email'): contact.append(f"Email: {hospital_info['email']}")
            if contact:
                elements.append(Paragraph("  |  ".join(contact), sub_style))
            elements.append(Spacer(1, 6))
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        else:
            elements.append(Spacer(1, letterhead_gap_pt))

        elements.append(Spacer(1, 8))
        elements.append(Paragraph("REFUND RECEIPT", receipt_title_style))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.black))
        elements.append(Spacer(1, 10))

        rows = [
            [Paragraph("Refund No:", label_style), Paragraph(str(refund_data.get('refund_number', '')), value_style),
             Paragraph("Date:", label_style), Paragraph(str(refund_data.get('refund_date', '')), value_style)],
            [Paragraph("Patient:", label_style), Paragraph(str(refund_data.get('patient_name', '')), value_style),
             Paragraph("Phone:", label_style), Paragraph(str(refund_data.get('patient_phone', '')), value_style)],
            [Paragraph("Bill No:", label_style), Paragraph(str(refund_data.get('bill_number', '')), value_style),
             Paragraph("Method:", label_style), Paragraph(str(refund_data.get('payment_method', '')).title(), value_style)],
            [Paragraph("Original Payment:", label_style), Paragraph(str(refund_data.get('original_payment_number', '')), value_style),
             Paragraph("Original Amt:", label_style), Paragraph(f"Rs. {float(refund_data.get('original_amount', 0)):,.2f}", value_style)],
        ]
        _refund_style = [('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]
        _refund_addr = _patient_address_line(refund_data)
        if _refund_addr:
            _row_idx = len(rows)
            rows.append([Paragraph("Address:", label_style), Paragraph(_refund_addr, value_style), '', ''])
            _refund_style.append(('SPAN', (1, _row_idx), (3, _row_idx)))
        meta_table = Table(rows, colWidths=[page_width * 0.20, page_width * 0.30, page_width * 0.18, page_width * 0.32])
        meta_table.setStyle(TableStyle(_refund_style))
        elements.append(meta_table)
        elements.append(Spacer(1, 14))

        elements.append(Paragraph("AMOUNT REFUNDED", label_style))
        elements.append(Spacer(1, 4))
        elements.append(Paragraph(f"Rs. {float(refund_data.get('amount', 0)):,.2f}", amount_style))
        elements.append(Spacer(1, 10))

        if refund_data.get('reason'):
            elements.append(Paragraph("<b>Reason:</b>", label_style))
            elements.append(Paragraph(str(refund_data['reason']), value_style))
            elements.append(Spacer(1, 10))

        sig_table = Table(
            [[Paragraph("____________________<br/>Refunded By", value_style),
              Paragraph("____________________<br/>Patient / Attendant", value_style)]],
            colWidths=[page_width / 2, page_width / 2],
        )
        sig_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 30),
        ]))
        elements.append(sig_table)
        elements.append(Spacer(1, 16))
        elements.append(Paragraph(
            f"Generated on {datetime.now().strftime('%d/%m/%Y at %H:%M:%S')}",
            footer_style,
        ))

        _finalize(doc, elements, hospital_info)
        buffer.seek(0)
        return buffer

    def generate_credit_note_pdf(self, cn_data, hospital_info, include_header=True, letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT):
        """Credit note PDF — reduces patient liability against a parent bill."""
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            rightMargin=40, leftMargin=40, topMargin=30, bottomMargin=30,
        )
        elements = []
        page_width = A4[0] - 80

        title_style = ParagraphStyle('Title', parent=self.styles['Title'],
            fontSize=15, alignment=1, fontName='Helvetica-Bold', textColor=colors.black, spaceAfter=4)
        sub_style = ParagraphStyle('Sub', parent=self.styles['Normal'],
            fontSize=9, alignment=1, fontName='Helvetica', textColor=colors.black, spaceAfter=2)
        cn_title_style = ParagraphStyle('CT', parent=self.styles['Normal'],
            fontSize=13, alignment=1, fontName='Helvetica-Bold', textColor=colors.HexColor('#b91c1c'), spaceAfter=6)
        label_style = ParagraphStyle('Label', parent=self.styles['Normal'],
            fontSize=10, fontName='Helvetica-Bold', textColor=colors.black)
        value_style = ParagraphStyle('Value', parent=self.styles['Normal'],
            fontSize=10, fontName='Helvetica', textColor=colors.black)
        amount_style = ParagraphStyle('Amount', parent=self.styles['Normal'],
            fontSize=14, fontName='Helvetica-Bold', alignment=1, textColor=colors.HexColor('#b91c1c'), spaceAfter=4)
        footer_style = ParagraphStyle('Footer', parent=self.styles['Normal'],
            fontSize=8, alignment=1, fontName='Helvetica', textColor=colors.black)

        if include_header:
            elements.append(Paragraph(hospital_info.get('name', 'HOSPITAL').upper(), title_style))
            if hospital_info.get('address'):
                elements.append(Paragraph(hospital_info['address'], sub_style))
            contact = []
            if hospital_info.get('phone'): contact.append(f"Phone: {hospital_info['phone']}")
            if hospital_info.get('email'): contact.append(f"Email: {hospital_info['email']}")
            if contact:
                elements.append(Paragraph("  |  ".join(contact), sub_style))
            elements.append(Spacer(1, 6))
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        else:
            elements.append(Spacer(1, letterhead_gap_pt))

        elements.append(Spacer(1, 8))
        elements.append(Paragraph("CREDIT NOTE", cn_title_style))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.black))
        elements.append(Spacer(1, 10))

        rows = [
            [Paragraph("Credit Note No:", label_style), Paragraph(str(cn_data.get('credit_note_number', '')), value_style),
             Paragraph("Date:", label_style), Paragraph(str(cn_data.get('credit_note_date', '')), value_style)],
            [Paragraph("Patient:", label_style), Paragraph(str(cn_data.get('patient_name', '')), value_style),
             Paragraph("Phone:", label_style), Paragraph(str(cn_data.get('patient_phone', '')), value_style)],
            [Paragraph("Original Bill:", label_style), Paragraph(str(cn_data.get('parent_bill_number', '')), value_style),
             Paragraph("Bill Total:", label_style), Paragraph(f"Rs. {float(cn_data.get('parent_bill_total', 0)):,.2f}", value_style)],
        ]
        _cn_style = [('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]
        _cn_addr = _patient_address_line(cn_data)
        if _cn_addr:
            _row_idx = len(rows)
            rows.append([Paragraph("Address:", label_style), Paragraph(_cn_addr, value_style), '', ''])
            _cn_style.append(('SPAN', (1, _row_idx), (3, _row_idx)))
        meta = Table(rows, colWidths=[page_width * 0.20, page_width * 0.30, page_width * 0.18, page_width * 0.32])
        meta.setStyle(TableStyle(_cn_style))
        elements.append(meta)
        elements.append(Spacer(1, 10))

        # Line items
        items = cn_data.get('items') or []
        if items:
            head = [Paragraph("<b>Item</b>", value_style), Paragraph("<b>Qty</b>", value_style),
                    Paragraph("<b>Unit (Rs.)</b>", value_style), Paragraph("<b>Total (Rs.)</b>", value_style)]
            body = [head]
            for it in items:
                body.append([
                    Paragraph(str(it.get('name', '')), value_style),
                    Paragraph(str(it.get('qty', '')), value_style),
                    Paragraph(f"{float(it.get('unit_price', 0)):,.2f}", value_style),
                    Paragraph(f"{float(it.get('total', 0)):,.2f}", value_style),
                ])
            t = Table(body, colWidths=[page_width * 0.55, page_width * 0.10, page_width * 0.17, page_width * 0.18])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#fee2e2')),
                ('GRID', (0, 0), (-1, -1), 0.4, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]))
            elements.append(t)
            elements.append(Spacer(1, 12))

        elements.append(Paragraph("TOTAL CREDITED", label_style))
        elements.append(Spacer(1, 4))
        elements.append(Paragraph(f"Rs. {float(cn_data.get('amount', 0)):,.2f}", amount_style))
        elements.append(Spacer(1, 10))

        if cn_data.get('reason'):
            elements.append(Paragraph("<b>Reason:</b>", label_style))
            elements.append(Paragraph(str(cn_data['reason']), value_style))
            elements.append(Spacer(1, 10))

        sig = Table(
            [[Paragraph("____________________<br/>Issued By", value_style),
              Paragraph("____________________<br/>Patient / Attendant", value_style)]],
            colWidths=[page_width / 2, page_width / 2],
        )
        sig.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 30),
        ]))
        elements.append(sig)
        elements.append(Spacer(1, 16))
        elements.append(Paragraph(
            f"Generated on {datetime.now().strftime('%d/%m/%Y at %H:%M:%S')}",
            footer_style,
        ))

        _finalize(doc, elements, hospital_info)
        buffer.seek(0)
        return buffer

    def generate_consent_pdf(self, consent_data, hospital_info, include_header=True, letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT):
        """Signed consent form PDF."""
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=30, bottomMargin=30)
        elements = []
        page_width = A4[0] - 80

        title_style = ParagraphStyle('Title', parent=self.styles['Title'],
            fontSize=14, alignment=1, fontName='Helvetica-Bold', textColor=colors.black, spaceAfter=4)
        sub_style = ParagraphStyle('Sub', parent=self.styles['Normal'],
            fontSize=9, alignment=1, fontName='Helvetica', textColor=colors.black, spaceAfter=2)
        heading = ParagraphStyle('Heading', parent=self.styles['Normal'],
            fontSize=11, fontName='Helvetica-Bold', textColor=colors.black, spaceAfter=4)
        body = ParagraphStyle('Body', parent=self.styles['Normal'],
            fontSize=10, fontName='Helvetica', textColor=colors.black, spaceAfter=4)
        label_small = ParagraphStyle('Label', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica-Bold', textColor=colors.black)
        footer_style = ParagraphStyle('Footer', parent=self.styles['Normal'],
            fontSize=8, alignment=1, fontName='Helvetica', textColor=colors.black)

        doc_number = consent_data.get('doc_number') or ''

        if include_header:
            # Header: hospital logo (left) + name/subname/address/contact (centre)
            # + doc number (right) — mirrors the OPD/bill header layout.
            logo_path = hospital_info.get('logo_url', '')
            uploads_base = _get_uploads_base()
            has_logo = False
            full_logo_path = ''
            if logo_path:
                relative = logo_path.lstrip('/')
                if relative.startswith('uploads/'):
                    relative = relative[len('uploads/'):]
                full_logo_path = os.path.join(uploads_base, relative)
                has_logo = os.path.exists(full_logo_path)

            centre_elems = [Paragraph(hospital_info.get('name', 'HOSPITAL').upper(), title_style)]
            if hospital_info.get('hospital_subname'):
                centre_elems.append(Paragraph(hospital_info['hospital_subname'], sub_style))
            if hospital_info.get('address'):
                centre_elems.append(Paragraph(hospital_info['address'], sub_style))
            contact_parts = []
            if hospital_info.get('email'):
                contact_parts.append(f"Email: {hospital_info['email']}")
            if hospital_info.get('phone'):
                contact_parts.append(f"Phone: {hospital_info['phone']}")
            if contact_parts:
                centre_elems.append(Paragraph("  |  ".join(contact_parts), sub_style))

            doc_num_para = Paragraph(
                f'<b>Doc No:</b><br/>{doc_number}' if doc_number else '',
                ParagraphStyle('DocNum', parent=self.styles['Normal'],
                    fontSize=9, fontName='Helvetica-Bold', alignment=2, textColor=colors.black)
            )

            if has_logo:
                try:
                    logo_img = Image(full_logo_path, width=60, height=60)
                    logo_img.hAlign = 'CENTER'
                    header_table = Table(
                        [[logo_img, centre_elems, doc_num_para]],
                        colWidths=[70, page_width - 70 - 90, 90],
                    )
                except Exception:
                    header_table = Table(
                        [[centre_elems, doc_num_para]],
                        colWidths=[page_width - 90, 90],
                    )
            else:
                header_table = Table(
                    [[centre_elems, doc_num_para]],
                    colWidths=[page_width - 90, 90],
                )
            header_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ]))
            elements.append(header_table)
            elements.append(Spacer(1, 6))
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        else:
            elements.append(Spacer(1, letterhead_gap_pt))
            if doc_number:
                elements.append(Paragraph(
                    f'<b>Doc No: {doc_number}</b>',
                    ParagraphStyle('DocNumNoH', parent=self.styles['Normal'],
                        fontSize=9, fontName='Helvetica-Bold', alignment=2, textColor=colors.black)
                ))

        elements.append(Spacer(1, 8))
        ctype = consent_data.get('consent_type', '').replace('_', ' ').upper()
        elements.append(Paragraph(f"{ctype} CONSENT FORM", ParagraphStyle('CT', parent=self.styles['Normal'],
            fontSize=13, alignment=1, fontName='Helvetica-Bold', textColor=colors.black, spaceAfter=6)))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.black))
        elements.append(Spacer(1, 8))

        # Patient/admission meta — always shown for all consent types
        mrn = consent_data.get('mrn', '')
        admission_number = consent_data.get('admission_number') or ''
        # In wizard preview mode the admission row doesn't exist yet, but the
        # form is being filled today — fall back to today's date so the
        # printed form has a meaningful "Date" on it.
        admission_date = consent_data.get('admission_date') or datetime.now().strftime("%d/%m/%Y")
        date_label = "Admitted on:" if admission_number else "Date:"
        meta_rows = [
            [Paragraph("Patient:", label_small), Paragraph(str(consent_data.get('patient_name', '')), body),
             Paragraph("MRN:", label_small), Paragraph(str(mrn), body)],
            [Paragraph("Admission #:", label_small), Paragraph(admission_number or '—', body),
             Paragraph("Doctor:", label_small), Paragraph(str(consent_data.get('doctor_name', '')), body)],
            [Paragraph(date_label, label_small), Paragraph(admission_date, body),
             Paragraph("Room:", label_small), Paragraph(str(consent_data.get('room_name', '')), body)],
            [Paragraph("Age / Gender:", label_small),
             Paragraph(f"{consent_data.get('age', '')} / {consent_data.get('gender', '')}", body),
             Paragraph("Phone:", label_small), Paragraph(str(consent_data.get('primary_phone', '')), body)],
        ]
        if consent_data.get('emergency_contact_name'):
            meta_rows.append([
                Paragraph("Emergency Contact:", label_small),
                Paragraph(
                    f"{consent_data['emergency_contact_name']}"
                    f"{' (' + consent_data['emergency_contact_relation'] + ')' if consent_data.get('emergency_contact_relation') else ''}"
                    f"{' — ' + consent_data['emergency_contact_phone'] if consent_data.get('emergency_contact_phone') else ''}",
                    body
                ),
                Paragraph("", label_small), Paragraph("", body),
            ])
        if consent_data.get('procedure_name'):
            meta_rows.append([Paragraph("Procedure:", label_small), Paragraph(str(consent_data['procedure_name']), body),
                              Paragraph("Language:", label_small), Paragraph(str(consent_data.get('language', 'english')).title(), body)])
        _consent_style = [
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]
        _consent_addr = _patient_address_line(consent_data)
        if _consent_addr:
            _row_idx = len(meta_rows)
            meta_rows.append([Paragraph("Address:", label_small), Paragraph(_consent_addr, body), '', ''])
            _consent_style.append(('SPAN', (1, _row_idx), (3, _row_idx)))
        meta_table = Table(meta_rows, colWidths=[page_width * 0.15, page_width * 0.35, page_width * 0.15, page_width * 0.35])
        meta_table.setStyle(TableStyle(_consent_style))
        elements.append(meta_table)
        elements.append(Spacer(1, 10))

        # Template content
        content = consent_data.get('template_content') or 'No template content.'
        elements.append(Paragraph("CONSENT STATEMENT", heading))
        for para in content.split("\n"):
            if para.strip():
                elements.append(Paragraph(para.strip(), body))
        elements.append(Spacer(1, 6))

        if consent_data.get('risks_explained'):
            elements.append(Paragraph("RISKS EXPLAINED", heading))
            elements.append(Paragraph(consent_data['risks_explained'], body))
            elements.append(Spacer(1, 6))

        # Signatures
        elements.append(Paragraph("SIGNATURES", heading))
        signed_by = consent_data.get('signed_by', 'patient')
        sig_label = "Patient" if signed_by == "patient" else f"{signed_by.title()} on behalf of patient"
        sig_lines = [[
            Paragraph(f"<b>{sig_label} Signature:</b><br/><br/>{consent_data.get('patient_signature', '') if consent_data.get('patient_signature_type') == 'typed' else '[drawn signature on file]'}<br/><br/>____________________", body),
            Paragraph(f"<b>Witness:</b><br/><br/>{consent_data.get('witness_name', '') or '—'}<br/><br/>____________________", body),
        ]]
        if signed_by != "patient":
            elements.append(Paragraph(f"<b>Signed by:</b> {signed_by} — {consent_data.get('guardian_name', '')} ({consent_data.get('guardian_relationship', '')})", body))
        sig_table = Table(sig_lines, colWidths=[page_width / 2, page_width / 2])
        sig_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
        ]))
        elements.append(sig_table)
        elements.append(Spacer(1, 6))
        elements.append(Paragraph(f"Signed at: {consent_data.get('signed_at', '')}", body))

        if consent_data.get('withdrawn_at'):
            elements.append(Spacer(1, 10))
            elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.black))
            elements.append(Paragraph("<b>CONSENT WITHDRAWN</b>", heading))
            elements.append(Paragraph(f"Withdrawn at: {consent_data['withdrawn_at']}", body))
            elements.append(Paragraph(f"Reason: {consent_data.get('withdrawal_reason', '')}", body))

        elements.append(Spacer(1, 18))
        elements.append(Paragraph(f"Generated on {datetime.now().strftime('%d/%m/%Y at %H:%M:%S')}", footer_style))
        _finalize(doc, elements, hospital_info)
        buffer.seek(0)
        return buffer

    def generate_death_certificate_pdf(self, cert_data, hospital_info, include_header=True, letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT):
        """Death certificate / mortality record."""
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=30, bottomMargin=30)
        elements = []
        page_width = A4[0] - 80

        title_style = ParagraphStyle('Title', parent=self.styles['Title'],
            fontSize=14, alignment=1, fontName='Helvetica-Bold', textColor=colors.black, spaceAfter=4)
        sub_style = ParagraphStyle('Sub', parent=self.styles['Normal'],
            fontSize=9, alignment=1, fontName='Helvetica', textColor=colors.black, spaceAfter=2)
        heading = ParagraphStyle('Heading', parent=self.styles['Normal'],
            fontSize=12, fontName='Helvetica-Bold', textColor=colors.black, spaceAfter=4)
        label = ParagraphStyle('Label', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica-Bold', textColor=colors.black)
        value = ParagraphStyle('Value', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica', textColor=colors.black)
        footer_style = ParagraphStyle('Footer', parent=self.styles['Normal'],
            fontSize=8, alignment=1, fontName='Helvetica', textColor=colors.black)

        if include_header:
            elements.append(Paragraph(hospital_info.get('name', 'HOSPITAL').upper(), title_style))
            if hospital_info.get('address'):
                elements.append(Paragraph(hospital_info['address'], sub_style))
            elements.append(Spacer(1, 6))
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        else:
            elements.append(Spacer(1, letterhead_gap_pt))

        elements.append(Spacer(1, 8))
        elements.append(Paragraph("DEATH CERTIFICATE", ParagraphStyle('DC', parent=self.styles['Normal'],
            fontSize=14, alignment=1, fontName='Helvetica-Bold', textColor=colors.black, spaceAfter=6)))
        if cert_data.get('death_certificate_number'):
            elements.append(Paragraph(f"Certificate No: {cert_data['death_certificate_number']}",
                ParagraphStyle('CN', parent=self.styles['Normal'], fontSize=10, alignment=1, textColor=colors.black)))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.black))
        elements.append(Spacer(1, 10))

        rows = [
            [Paragraph("Name of Deceased:", label), Paragraph(str(cert_data.get('patient_name', '')), value)],
            [Paragraph("Age / Gender:", label), Paragraph(_age_gender_str(cert_data, gender=cert_data.get('gender', ''), age_key='age') or str(cert_data.get('gender', '')), value)],
            [Paragraph("MRN:", label), Paragraph(str(cert_data.get('mrn', '')), value)],
            [Paragraph("Admission No:", label), Paragraph(str(cert_data.get('admission_number', '')), value)],
            [Paragraph("Admitted On:", label), Paragraph(str(cert_data.get('admission_date', '')), value)],
            [Paragraph("Date of Death:", label), Paragraph(str(cert_data.get('discharge_date', '')), value)],
            [Paragraph("Time of Death:", label), Paragraph(str(cert_data.get('time_of_death', '')), value)],
            [Paragraph("Cause of Death:", label), Paragraph(str(cert_data.get('cause_of_death', '')), value)],
            [Paragraph("Treating Doctor:", label), Paragraph(str(cert_data.get('treating_doctor', '')), value)],
            [Paragraph("MLC Required:", label), Paragraph("Yes" if cert_data.get('mlc_required') else "No", value)],
        ]
        if cert_data.get('mlc_required') and cert_data.get('mlc_number'):
            rows.append([Paragraph("MLC No:", label), Paragraph(str(cert_data['mlc_number']), value)])
        rows.append([Paragraph("Autopsy Done:", label), Paragraph("Yes" if cert_data.get('autopsy_done') else "No", value)])

        _cert_addr = _patient_address_line(cert_data)
        if _cert_addr:
            rows.append([Paragraph("Address:", label), Paragraph(_cert_addr, value)])

        meta_table = Table(rows, colWidths=[page_width * 0.3, page_width * 0.7])
        meta_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(meta_table)

        if cert_data.get('body_handed_over_to'):
            elements.append(Spacer(1, 10))
            elements.append(Paragraph("BODY HANDOVER", heading))
            handover_rows = [
                [Paragraph("Handed over to:", label), Paragraph(str(cert_data.get('body_handed_over_to', '')), value)],
                [Paragraph("Relationship:", label), Paragraph(str(cert_data.get('body_handover_relationship', '')), value)],
                [Paragraph("Date/Time:", label), Paragraph(str(cert_data.get('body_handover_time', '')), value)],
                [Paragraph("ID Proof:", label), Paragraph(str(cert_data.get('body_handover_id_proof', '')), value)],
            ]
            h_table = Table(handover_rows, colWidths=[page_width * 0.3, page_width * 0.7])
            h_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            elements.append(h_table)

        # Signatures
        elements.append(Spacer(1, 20))
        sig_table = Table([[
            Paragraph("____________________<br/>Medical Officer / Treating Doctor", value),
            Paragraph("____________________<br/>Medical Superintendent", value),
        ]], colWidths=[page_width / 2, page_width / 2])
        sig_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 30),
        ]))
        elements.append(sig_table)
        elements.append(Spacer(1, 14))
        elements.append(Paragraph(f"Generated on {datetime.now().strftime('%d/%m/%Y at %H:%M:%S')}", footer_style))
        _finalize(doc, elements, hospital_info)
        buffer.seek(0)
        return buffer

    def generate_dama_pdf(self, dama_data, hospital_info, include_header=True, letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT):
        """Discharge Against Medical Advice — signed liability form.
        Indian context: invokes Section 88/92 IPC ('act done in good faith for
        the benefit of a person, with consent') in the absolves clause."""
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=30, bottomMargin=30)
        elements = []
        page_width = A4[0] - 80

        title_style = ParagraphStyle('Title', parent=self.styles['Title'],
            fontSize=14, alignment=1, fontName='Helvetica-Bold', textColor=colors.black, spaceAfter=4)
        sub_style = ParagraphStyle('Sub', parent=self.styles['Normal'],
            fontSize=9, alignment=1, fontName='Helvetica', textColor=colors.black, spaceAfter=2)
        heading = ParagraphStyle('Heading', parent=self.styles['Normal'],
            fontSize=11, fontName='Helvetica-Bold', textColor=colors.black, spaceAfter=4, spaceBefore=8)
        label = ParagraphStyle('Label', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica-Bold', textColor=colors.black)
        value = ParagraphStyle('Value', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica', textColor=colors.black)
        body = ParagraphStyle('Body', parent=self.styles['Normal'],
            fontSize=10, fontName='Helvetica', textColor=colors.black, spaceAfter=4, leading=14)
        footer_style = ParagraphStyle('Footer', parent=self.styles['Normal'],
            fontSize=8, alignment=1, fontName='Helvetica', textColor=colors.black)

        if include_header:
            elements.append(Paragraph(hospital_info.get('name', 'HOSPITAL').upper(), title_style))
            if hospital_info.get('address'):
                elements.append(Paragraph(hospital_info['address'], sub_style))
            elements.append(Spacer(1, 6))
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        else:
            elements.append(Spacer(1, letterhead_gap_pt))

        elements.append(Spacer(1, 8))
        elements.append(Paragraph("DISCHARGE AGAINST MEDICAL ADVICE (DAMA)",
            ParagraphStyle('DA', parent=self.styles['Normal'],
                fontSize=14, alignment=1, fontName='Helvetica-Bold', textColor=colors.black, spaceAfter=6)))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.black))
        elements.append(Spacer(1, 10))

        meta_rows = [
            [Paragraph("Patient Name:", label), Paragraph(str(dama_data.get('patient_name', '')), value)],
            [Paragraph("MRN:", label), Paragraph(str(dama_data.get('mrn', '')), value)],
            [Paragraph("Age / Gender:", label),
             Paragraph(f"{dama_data.get('age', '')} / {dama_data.get('gender', '')}", value)],
            [Paragraph("Admission No:", label), Paragraph(str(dama_data.get('admission_number', '')), value)],
            [Paragraph("Attending Doctor:", label), Paragraph(str(dama_data.get('doctor_name', '')), value)],
            [Paragraph("Admission Date:", label), Paragraph(str(dama_data.get('admission_date', '')), value)],
            [Paragraph("Discharge Date/Time:", label), Paragraph(str(dama_data.get('discharge_date', '')), value)],
            [Paragraph("Language Used:", label), Paragraph(str(dama_data.get('language_used', '')).title(), value)],
        ]
        _dama_addr = _patient_address_line(dama_data)
        if _dama_addr:
            meta_rows.append([Paragraph("Address:", label), Paragraph(_dama_addr, value)])
        meta_table = Table(meta_rows, colWidths=[page_width * 0.3, page_width * 0.7])
        meta_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(meta_table)

        elements.append(Paragraph("MEDICAL ADVICE GIVEN", heading))
        elements.append(Paragraph((dama_data.get('medical_advice_given') or '').replace('\n', '<br/>'), body))

        elements.append(Paragraph("RISKS EXPLAINED", heading))
        elements.append(Paragraph((dama_data.get('risks_explained') or '').replace('\n', '<br/>'), body))

        elements.append(Paragraph("DECLARATION", heading))
        decl = (
            "I, the undersigned, hereby declare that I have been clearly explained the medical advice and "
            "the risks of leaving the hospital against this advice in a language I understand. I am leaving "
            "the hospital of my own free will and accord, against the advice of the treating doctor. I "
            "absolve the hospital, its doctors, nurses and staff of any responsibility for any consequences, "
            "including deterioration of health or death, that may arise as a result of this decision. "
            "(Reference: Sections 88 and 92, Indian Penal Code.)"
        )
        elements.append(Paragraph(decl, body))

        # Signatures
        elements.append(Spacer(1, 14))
        signed_label = "Patient Signature" if dama_data.get('signed_by') == 'patient' else "Guardian Signature"
        primary_sig_text = dama_data.get('primary_signature') or ''
        if dama_data.get('primary_signature_type') == 'typed':
            sig_para = Paragraph(f"<i>{primary_sig_text}</i>", value)
        else:
            sig_para = Paragraph("(signed)", value)

        guardian_block = ""
        if dama_data.get('signed_by') == 'guardian':
            guardian_block = (
                f"<br/>Guardian: {dama_data.get('guardian_name', '')}"
                f"<br/>Relationship: {dama_data.get('guardian_relationship', '')}"
            )

        sig_table = Table([
            [
                Paragraph(f"____________________<br/><b>{signed_label}</b>{guardian_block}<br/>{sig_para.text if hasattr(sig_para, 'text') else primary_sig_text}", value),
                Paragraph(
                    f"____________________<br/><b>Witness</b><br/>"
                    f"{dama_data.get('witness_name', '')}"
                    f"{(' (' + dama_data['witness_designation'] + ')') if dama_data.get('witness_designation') else ''}",
                    value),
            ]
        ], colWidths=[page_width / 2, page_width / 2])
        sig_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 30),
        ]))
        elements.append(sig_table)

        if dama_data.get('notes'):
            elements.append(Spacer(1, 10))
            elements.append(Paragraph("ADDITIONAL NOTES", heading))
            elements.append(Paragraph(dama_data['notes'].replace('\n', '<br/>'), body))

        elements.append(Spacer(1, 14))
        elements.append(Paragraph(
            f"Form signed on {dama_data.get('signed_at', '')} | Generated {datetime.now().strftime('%d/%m/%Y at %H:%M')}",
            footer_style))
        _finalize(doc, elements, hospital_info)
        buffer.seek(0)
        return buffer


    def generate_gate_pass_pdf(self, payload, hospital_info, include_header=True, letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT):
        """Printable gate pass — shown to security at exit. One half-page slip.
        Header matches the bill / lab report layout (logo + hospital name +
        subname + address + contact). Footer matches with Issued-by / Printed-by
        line plus a 'Generated on' timestamp."""
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
            rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=20)
        elements = []
        page_width = A4[0] - 60

        title_style = ParagraphStyle('GPTitle', parent=self.styles['Title'],
            fontSize=16, alignment=1, fontName='Helvetica-Bold',
            textColor=colors.black, spaceAfter=2)
        subtitle_style = ParagraphStyle('GPSubtitle', parent=self.styles['Normal'],
            fontSize=9, alignment=1, fontName='Helvetica',
            textColor=colors.black, spaceAfter=2)
        receipt_title_style = ParagraphStyle('GPReceiptTitle', parent=self.styles['Normal'],
            fontSize=12, alignment=1, fontName='Helvetica-Bold',
            textColor=colors.black, spaceAfter=4)
        label = ParagraphStyle('GPLbl', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica-Bold', textColor=colors.black)
        value = ParagraphStyle('GPVal', parent=self.styles['Normal'],
            fontSize=10, fontName='Helvetica', textColor=colors.black)
        small = ParagraphStyle('GPSm', parent=self.styles['Normal'],
            fontSize=8, fontName='Helvetica', textColor=colors.black)
        warn = ParagraphStyle('GPWarn', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica-Bold', textColor=colors.red)
        footer_meta = ParagraphStyle('GPFootMeta', parent=self.styles['Normal'],
            fontSize=7, fontName='Helvetica-Oblique', alignment=1, textColor=colors.grey)

        def lv(lbl, val):
            return Paragraph(f"<b>{lbl}</b> :  {val}",
                             ParagraphStyle('GPLV', parent=value, leading=11))

        # ============================================================
        # HEADER — same layout as generate_bill_pdf / inpatient bill
        # ============================================================
        if include_header:
            logo_path = hospital_info.get('logo_url', '')
            uploads_base = _get_uploads_base()
            has_logo = False
            full_logo_path = ''
            if logo_path:
                relative = logo_path.lstrip('/')
                if relative.startswith('uploads/'):
                    relative = relative[len('uploads/'):]
                full_logo_path = os.path.join(uploads_base, relative)
                has_logo = os.path.exists(full_logo_path)

            hospital_name = hospital_info.get('name', 'HOSPITAL').upper()
            hospital_subname = hospital_info.get('hospital_subname', '')
            address = hospital_info.get('address', '')
            contact_parts = []
            if hospital_info.get('email'):
                contact_parts.append(f"Email: {hospital_info['email']}")
            if hospital_info.get('phone'):
                contact_parts.append(f"Phone: {hospital_info['phone']}")

            header_text_elems = [Paragraph(hospital_name, title_style)]
            if hospital_subname:
                header_text_elems.append(Paragraph(hospital_subname, subtitle_style))
            if address:
                header_text_elems.append(Paragraph(address, subtitle_style))
            if contact_parts:
                header_text_elems.append(Paragraph("  |  ".join(contact_parts), subtitle_style))

            if has_logo:
                try:
                    logo_img = Image(full_logo_path, width=60, height=60)
                    logo_img.hAlign = 'CENTER'
                    header_table = Table(
                        [[logo_img, header_text_elems]],
                        colWidths=[75, page_width - 75],
                    )
                    header_table.setStyle(TableStyle([
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 0),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                        ('TOPPADDING', (0, 0), (-1, -1), 0),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                    ]))
                    elements.append(header_table)
                except Exception:
                    for el in header_text_elems:
                        elements.append(el)
            else:
                for el in header_text_elems:
                    elements.append(el)

            elements.append(Spacer(1, 6))
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        else:
            elements.append(Spacer(1, letterhead_gap_pt))

        elements.append(Spacer(1, 6))
        elements.append(Paragraph("GATE PASS / DISCHARGE EXIT SLIP", receipt_title_style))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        elements.append(Spacer(1, 8))

        # Detail table
        rows = [
            [Paragraph("Pass Number", label), Paragraph(payload.get('pass_number', '-'), value),
             Paragraph("Issued at", label), Paragraph(payload.get('issued_at', '-'), value)],
            [Paragraph("Admission No", label), Paragraph(payload.get('admission_number', '-'), value),
             Paragraph("MRN", label), Paragraph(payload.get('mrn', '-'), value)],
            [Paragraph("Patient Name", label), Paragraph(payload.get('patient_name', '-'), value),
             Paragraph("Attendant", label), Paragraph(payload.get('attendant_name', '-'), value)],
            [Paragraph("Vehicle No.", label), Paragraph(payload.get('vehicle_no', '-'), value),
             Paragraph("Relationship", label), Paragraph(payload.get('attendant_relationship', '-'), value)],
        ]
        t = Table(rows, colWidths=[page_width * 0.18, page_width * 0.32,
                                   page_width * 0.18, page_width * 0.32])
        t.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.4, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 12))

        # Outstanding-balance line (use Rs. — the ₹ glyph is missing from the
        # default Helvetica font and renders as a tofu square).
        if payload.get('override_balance'):
            elements.append(Paragraph(
                f"OVERRIDE issued with Rs. {float(payload.get('outstanding_at_issue') or 0):,.2f} outstanding",
                warn))
            if payload.get('override_reason'):
                elements.append(Paragraph(f"Reason: {payload['override_reason']}", value))
            elements.append(Spacer(1, 10))
        else:
            elements.append(Paragraph("Bill cleared — outstanding balance Rs. 0.00", value))
            elements.append(Spacer(1, 10))

        if payload.get('notes'):
            elements.append(Paragraph(f"<b>Notes:</b> {payload['notes']}", value))
            elements.append(Spacer(1, 10))

        elements.append(Paragraph(f"QR Token: {payload.get('qr_token', '-')}",
            ParagraphStyle('GPQR', parent=self.styles['Normal'],
                fontSize=7, fontName='Courier', textColor=colors.grey, alignment=1)))

        elements.append(Spacer(1, 36))
        sig_rows = [[
            Paragraph("Security Signature", label),
            Paragraph("Attendant Signature", label),
        ]]
        sig = Table(sig_rows, colWidths=[page_width * 0.5, page_width * 0.5])
        sig.setStyle(TableStyle([
            ('LINEABOVE', (0, 0), (-1, 0), 0.5, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(sig)

        # ============================================================
        # FOOTER — Issued by / Printed by + generation timestamp,
        # matches the bill PDFs' bottom block.
        # ============================================================
        elements.append(Spacer(1, 14))
        elements.append(HRFlowable(width="100%", thickness=0.4, color=colors.grey))
        elements.append(Spacer(1, 4))
        issued_by = payload.get('issued_by_name', '-') or '-'
        footer_data = [[
            lv('Issued by', issued_by),
            lv('Printed by', issued_by),
        ]]
        footer_table = Table(footer_data, colWidths=[page_width / 2, page_width / 2])
        footer_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(footer_table)
        elements.append(Spacer(1, 4))
        elements.append(Paragraph(
            f"Generated on {datetime.now().strftime('%d/%m/%Y at %H:%M:%S')}",
            footer_meta,
        ))

        _finalize(doc, elements, hospital_info)
        buffer.seek(0)
        return buffer


    def generate_doctor_productivity_pdf(self, payload, hospital_info, include_header=True, letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT):
        """Per-doctor productivity table for revenue-share / performance review."""
        buffer = BytesIO()
        # Landscape — many columns
        from reportlab.lib.pagesizes import landscape
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
            rightMargin=20, leftMargin=20, topMargin=24, bottomMargin=24)
        elements = []
        page_width = landscape(A4)[0] - 40

        title_style = ParagraphStyle('Title', parent=self.styles['Title'],
            fontSize=13, alignment=1, fontName='Helvetica-Bold', textColor=colors.black, spaceAfter=4)
        sub_style = ParagraphStyle('Sub', parent=self.styles['Normal'],
            fontSize=8, alignment=1, fontName='Helvetica', textColor=colors.black, spaceAfter=2)
        cell = ParagraphStyle('Cell', parent=self.styles['Normal'],
            fontSize=8, fontName='Helvetica', textColor=colors.black, leading=10)
        cell_b = ParagraphStyle('CellB', parent=self.styles['Normal'],
            fontSize=8, fontName='Helvetica-Bold', textColor=colors.black, leading=10)

        if include_header:
            elements.append(Paragraph(hospital_info.get('name', 'HOSPITAL').upper(), title_style))
            if hospital_info.get('address'):
                elements.append(Paragraph(hospital_info['address'], sub_style))
            elements.append(Spacer(1, 4))
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        else:
            elements.append(Spacer(1, 50))

        elements.append(Spacer(1, 6))
        elements.append(Paragraph(
            f"DOCTOR PRODUCTIVITY — {payload.get('date_from', '')} to {payload.get('date_to', '')}",
            ParagraphStyle('H', parent=self.styles['Normal'], fontSize=12, alignment=1,
                fontName='Helvetica-Bold', textColor=colors.black, spaceAfter=2)))
        elements.append(Paragraph(f"{payload.get('doctor_count', 0)} doctor(s)", sub_style))
        elements.append(Spacer(1, 6))

        rows = payload.get("rows", [])
        if not rows:
            elements.append(Paragraph("No activity in this date range.",
                ParagraphStyle('N', parent=self.styles['Normal'], fontSize=10, alignment=1)))
        else:
            header = ["Doctor", "Adm", "Dis", "Death", "Re-30d",
                      "OT-Sur", "OT-An", "Visits", "Avg LOS",
                      "Visit (Rs.)", "OT Surgeon (Rs.)", "OT Anaes (Rs.)", "Total (Rs.)"]
            data_rows = [[Paragraph(h, cell_b) for h in header]]
            for r in rows:
                data_rows.append([
                    Paragraph(r["doctor_name"], cell),
                    Paragraph(str(r["admissions"]), cell),
                    Paragraph(str(r["discharges"]), cell),
                    Paragraph(str(r["deaths"]), cell),
                    Paragraph(str(r["readmissions_30d"]), cell),
                    Paragraph(str(r["ot_as_surgeon"]), cell),
                    Paragraph(str(r["ot_as_anaesthetist"]), cell),
                    Paragraph(str(r["visits"]), cell),
                    Paragraph(str(r["average_los_days"]) if r["average_los_days"] is not None else "—", cell),
                    Paragraph(f'{r["visit_fees_billed"]:,.0f}', cell),
                    Paragraph(f'{r["ot_surgeon_fees"]:,.0f}', cell),
                    Paragraph(f'{r["ot_anaesthetist_fees"]:,.0f}', cell),
                    Paragraph(f'{r["total_billed_attributable"]:,.0f}', cell_b),
                ])
            # Column widths sized so the doctor name has room and money cols don't wrap
            col_widths = [
                page_width * 0.18,  # doctor
                page_width * 0.04, page_width * 0.04, page_width * 0.04, page_width * 0.05,  # adm, dis, death, re30
                page_width * 0.04, page_width * 0.04, page_width * 0.05,  # ot s, ot a, visits
                page_width * 0.05,  # avg LOS
                page_width * 0.10, page_width * 0.11, page_width * 0.11, page_width * 0.15,  # money
            ]
            t = Table(data_rows, colWidths=col_widths, repeatRows=1)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e0e0e0')),
                ('GRID', (0, 0), (-1, -1), 0.4, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            elements.append(t)

        elements.append(Spacer(1, 14))
        elements.append(Paragraph(
            "Total (Rs.) = Visit fees + OT surgeon fees (for OTs led) + OT anaesthetist fees. Outpatient consultation fees not included.",
            ParagraphStyle('NF', parent=self.styles['Normal'], fontSize=7, alignment=0,
                fontName='Helvetica-Oblique', textColor=colors.HexColor('#555555'))))
        elements.append(Paragraph(
            f"Generated on {datetime.now().strftime('%d/%m/%Y at %H:%M')}",
            ParagraphStyle('F', parent=self.styles['Normal'], fontSize=8, alignment=1)))
        _finalize(doc, elements, hospital_info)
        buffer.seek(0)
        return buffer

    def generate_monthly_outcomes_pdf(self, payload, hospital_info, include_header=True, letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT):
        """Monthly outcomes — mortality + readmission + LOS + occupancy."""
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
        elements = []
        page_width = A4[0] - 60

        title_style = ParagraphStyle('Title', parent=self.styles['Title'],
            fontSize=14, alignment=1, fontName='Helvetica-Bold', textColor=colors.black, spaceAfter=4)
        sub_style = ParagraphStyle('Sub', parent=self.styles['Normal'],
            fontSize=9, alignment=1, fontName='Helvetica', textColor=colors.black, spaceAfter=2)
        section = ParagraphStyle('Section', parent=self.styles['Normal'],
            fontSize=11, fontName='Helvetica-Bold', textColor=colors.black, spaceBefore=10, spaceAfter=4)
        cell = ParagraphStyle('Cell', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica', textColor=colors.black, leading=11)
        cell_b = ParagraphStyle('CellB', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica-Bold', textColor=colors.black, leading=11)
        big = ParagraphStyle('Big', parent=self.styles['Normal'],
            fontSize=14, alignment=1, fontName='Helvetica-Bold', textColor=colors.black)
        bigsmall = ParagraphStyle('BigSmall', parent=self.styles['Normal'],
            fontSize=8, alignment=1, fontName='Helvetica', textColor=colors.black)

        if include_header:
            elements.append(Paragraph(hospital_info.get('name', 'HOSPITAL').upper(), title_style))
            if hospital_info.get('address'):
                elements.append(Paragraph(hospital_info['address'], sub_style))
            elements.append(Spacer(1, 6))
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        else:
            elements.append(Spacer(1, 60))

        elements.append(Spacer(1, 6))
        elements.append(Paragraph(f"MONTHLY OUTCOMES — {payload.get('month', '')}",
            ParagraphStyle('H', parent=self.styles['Normal'], fontSize=14, alignment=1,
                fontName='Helvetica-Bold', textColor=colors.black, spaceAfter=4)))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.black))

        # Totals tiles
        t = payload.get("totals", {})
        def _tile(v, l):
            tbl = Table([[Paragraph(str(v), big)], [Paragraph(l, bigsmall)]],
                        colWidths=[page_width / 5 - 4])
            tbl.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
            return tbl

        elements.append(Spacer(1, 8))
        tiles_row = Table([[
            _tile(t.get("admissions", 0), "Admissions"),
            _tile(t.get("discharges", 0), "Discharges"),
            _tile(t.get("deaths", 0), "Deaths"),
            _tile(f'{t.get("mortality_rate_pct", 0)}%', "Mortality"),
            _tile(f'{t.get("readmission_rate_pct", 0)}%', "Readmit"),
        ]], colWidths=[page_width / 5] * 5)
        tiles_row.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fafafa')),
            ('BOX', (0, 0), (-1, -1), 0.4, colors.grey),
            ('GRID', (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ]))
        elements.append(tiles_row)
        elements.append(Spacer(1, 4))
        elements.append(Paragraph(
            f"Average daily occupancy: {t.get('average_daily_occupancy', 0)} beds "
            f"({t.get('average_occupancy_pct', 0)}%)",
            ParagraphStyle('OL', parent=self.styles['Normal'], fontSize=10, alignment=1,
                fontName='Helvetica-Bold', textColor=colors.HexColor('#444444'))))

        def _kv_table(title, mapping, key_label="Item"):
            elements.append(Paragraph(title, section))
            if not mapping:
                elements.append(Paragraph("(none)", cell))
                return
            rows = [[Paragraph(key_label, cell_b), Paragraph("Count", cell_b)]]
            for k, v in mapping.items():
                rows.append([Paragraph(str(k), cell), Paragraph(str(v), cell)])
            t = Table(rows, colWidths=[page_width * 0.7, page_width * 0.3], repeatRows=1)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e0e0e0')),
                ('GRID', (0, 0), (-1, -1), 0.4, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            elements.append(t)

        # Mortality breakdown
        m = payload.get("mortality", {})
        elements.append(Paragraph(
            f"MORTALITY  —  {t.get('deaths', 0)} deaths; MLC: {m.get('mlc_count', 0)}; Autopsy: {m.get('autopsy_count', 0)}",
            section))
        _kv_table("By department", m.get("by_department", {}), "Department")
        _kv_table("Top diagnoses", m.get("by_diagnosis_top10", {}), "Diagnosis")
        _kv_table("By age band", m.get("by_age_band", {}), "Age band")
        _kv_table("By gender", m.get("by_gender", {}), "Gender")

        # Readmission breakdown
        rd = payload.get("readmissions", {})
        elements.append(Paragraph("READMISSIONS", section))
        _kv_table("By days-since-discharge", rd.get("by_window_days", {}), "Window")
        _kv_table("By department", rd.get("by_department", {}), "Department")
        _kv_table("Top diagnoses (prior discharge)", rd.get("by_diagnosis_top10", {}), "Diagnosis")

        # LOS
        los = payload.get("length_of_stay", {})
        overall = los.get("overall", {})
        elements.append(Paragraph("LENGTH OF STAY", section))
        rows = [[Paragraph(h, cell_b) for h in ["Scope", "Count", "Mean", "Median", "Min", "Max"]]]
        rows.append([Paragraph("Overall", cell), Paragraph(str(overall.get("count", 0)), cell),
                     Paragraph(str(overall.get("mean", '—')), cell), Paragraph(str(overall.get("median", '—')), cell),
                     Paragraph(str(overall.get("min", '—')), cell), Paragraph(str(overall.get("max", '—')), cell)])
        for dept, s in (los.get("by_department") or {}).items():
            rows.append([Paragraph(dept, cell), Paragraph(str(s.get("count", 0)), cell),
                         Paragraph(str(s.get("mean", '—')), cell), Paragraph(str(s.get("median", '—')), cell),
                         Paragraph(str(s.get("min", '—')), cell), Paragraph(str(s.get("max", '—')), cell)])
        los_table = Table(rows, colWidths=[page_width * 0.34] + [page_width * 0.132] * 5, repeatRows=1)
        los_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e0e0e0')),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(los_table)

        elements.append(Spacer(1, 14))
        elements.append(Paragraph(
            f"Generated on {datetime.now().strftime('%d/%m/%Y at %H:%M')}",
            ParagraphStyle('F', parent=self.styles['Normal'], fontSize=8, alignment=1)))
        _finalize(doc, elements, hospital_info)
        buffer.seek(0)
        return buffer

    def generate_handover_pdf(self, payload, hospital_info, include_header=True, letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT):
        """Nurse-to-nurse shift handover sheet."""
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=30, bottomMargin=30)
        elements = []
        page_width = A4[0] - 80

        title_style = ParagraphStyle('Title', parent=self.styles['Title'],
            fontSize=14, alignment=1, fontName='Helvetica-Bold', textColor=colors.black, spaceAfter=4)
        sub_style = ParagraphStyle('Sub', parent=self.styles['Normal'],
            fontSize=9, alignment=1, fontName='Helvetica', textColor=colors.black, spaceAfter=2)
        section = ParagraphStyle('Section', parent=self.styles['Normal'],
            fontSize=11, fontName='Helvetica-Bold', textColor=colors.black, spaceBefore=8, spaceAfter=3)
        label = ParagraphStyle('Label', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica-Bold', textColor=colors.black)
        value = ParagraphStyle('Value', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica', textColor=colors.black)
        body = ParagraphStyle('Body', parent=self.styles['Normal'],
            fontSize=10, fontName='Helvetica', textColor=colors.black, spaceAfter=4, leading=13)

        if include_header:
            elements.append(Paragraph(hospital_info.get('name', 'HOSPITAL').upper(), title_style))
            if hospital_info.get('address'):
                elements.append(Paragraph(hospital_info['address'], sub_style))
            elements.append(Spacer(1, 6))
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        else:
            elements.append(Spacer(1, 80))

        elements.append(Spacer(1, 8))
        elements.append(Paragraph("NURSE SHIFT HANDOVER",
            ParagraphStyle('H', parent=self.styles['Normal'], fontSize=14, alignment=1,
                fontName='Helvetica-Bold', textColor=colors.black, spaceAfter=4)))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.black))
        elements.append(Spacer(1, 6))

        meta_rows = [
            [Paragraph("Patient:", label), Paragraph(str(payload.get('patient_name', '')), value)],
            [Paragraph("MRN:", label), Paragraph(str(payload.get('mrn', '')), value)],
            [Paragraph("Admission No:", label), Paragraph(str(payload.get('admission_number', '')), value)],
            [Paragraph("Room / Bed:", label),
             Paragraph(f"{payload.get('room', '')} / {payload.get('bed', '')}", value)],
            [Paragraph("Shift Ending:", label), Paragraph(str(payload.get('from_shift', '')).title(), value)],
            [Paragraph("Handover At:", label), Paragraph(str(payload.get('handover_date', '')), value)],
            [Paragraph("From Nurse:", label), Paragraph(str(payload.get('from_nurse', '')), value)],
            [Paragraph("To Nurse:", label), Paragraph(str(payload.get('to_nurse', '') or '— (unassigned)'), value)],
            [Paragraph("Acknowledged:", label), Paragraph(str(payload.get('acknowledged_at', '') or '— pending'), value)],
        ]
        meta_table = Table(meta_rows, colWidths=[page_width * 0.30, page_width * 0.70])
        meta_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(meta_table)

        for sec_title, key in [
            ("Patient Status Summary", "patient_status_summary"),
            ("Pending Tasks", "pending_tasks"),
            ("Alerts To Watch", "alerts_to_watch"),
            ("Family Communication", "family_communication"),
            ("On-Call Contacts", "on_call_contacts"),
            ("Notes", "notes"),
        ]:
            txt = (payload.get(key) or "").strip()
            if not txt:
                continue
            elements.append(Paragraph(sec_title, section))
            elements.append(Paragraph(txt.replace('\n', '<br/>'), body))

        elements.append(Spacer(1, 20))
        sig_table = Table([[
            Paragraph(f"____________________<br/>Outgoing Nurse: {payload.get('from_nurse', '')}", value),
            Paragraph(f"____________________<br/>Incoming Nurse: {payload.get('to_nurse', '') or '___________________'}", value),
        ]], colWidths=[page_width / 2, page_width / 2])
        sig_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                       ('TOPPADDING', (0, 0), (-1, -1), 30)]))
        elements.append(sig_table)

        elements.append(Spacer(1, 14))
        elements.append(Paragraph(
            f"Generated on {datetime.now().strftime('%d/%m/%Y at %H:%M')}",
            ParagraphStyle('F', parent=self.styles['Normal'], fontSize=8, alignment=1)))
        _finalize(doc, elements, hospital_info)
        buffer.seek(0)
        return buffer

    def generate_census_pdf(self, payload, hospital_info, include_header=True, letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT):
        """Daily census report — totals + per-ward + per-room-type breakdown."""
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
        elements = []
        page_width = A4[0] - 60

        title_style = ParagraphStyle('Title', parent=self.styles['Title'],
            fontSize=14, alignment=1, fontName='Helvetica-Bold', textColor=colors.black, spaceAfter=4)
        sub_style = ParagraphStyle('Sub', parent=self.styles['Normal'],
            fontSize=9, alignment=1, fontName='Helvetica', textColor=colors.black, spaceAfter=2)
        section = ParagraphStyle('Section', parent=self.styles['Normal'],
            fontSize=11, fontName='Helvetica-Bold', textColor=colors.black, spaceBefore=10, spaceAfter=4)
        cell = ParagraphStyle('Cell', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica', textColor=colors.black, leading=11)
        cell_b = ParagraphStyle('CellB', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica-Bold', textColor=colors.black, leading=11)
        big = ParagraphStyle('Big', parent=self.styles['Normal'],
            fontSize=14, alignment=1, fontName='Helvetica-Bold', textColor=colors.black)
        bigsmall = ParagraphStyle('BigSmall', parent=self.styles['Normal'],
            fontSize=8, alignment=1, fontName='Helvetica', textColor=colors.black)

        if include_header:
            elements.append(Paragraph(hospital_info.get('name', 'HOSPITAL').upper(), title_style))
            if hospital_info.get('address'):
                elements.append(Paragraph(hospital_info['address'], sub_style))
            elements.append(Spacer(1, 6))
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        else:
            elements.append(Spacer(1, 60))

        elements.append(Spacer(1, 6))
        as_of = payload.get("as_of", "")
        as_of_h = _fmt_system_dt(as_of, fmt="%d/%m/%Y %H:%M", empty=as_of or "")
        elements.append(Paragraph(f"DAILY CENSUS REPORT — {as_of_h}",
            ParagraphStyle('H', parent=self.styles['Normal'], fontSize=13, alignment=1,
                fontName='Helvetica-Bold', textColor=colors.black, spaceAfter=4)))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.black))

        # Totals strip — five tiles
        t = payload.get("totals", {})
        tile = lambda v, l: Table([[Paragraph(str(v), big)], [Paragraph(l, bigsmall)]],
            colWidths=[page_width / 5 - 4])
        for tbl in (tile(t.get("total_beds", 0), "Total beds"),
                    tile(t.get("occupied", 0), "Occupied"),
                    tile(t.get("free", 0), "Free"),
                    tile(t.get("cleaning", 0), "Cleaning"),
                    tile(f'{t.get("occupancy_pct", 0)}%', "Occupancy")):
            tbl.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f5f5f5')),
                ('BOX', (0, 0), (-1, -1), 0.4, colors.grey)]))
        elements.append(Spacer(1, 8))
        tiles_row = Table([[
            tile(t.get("total_beds", 0), "Total beds"),
            tile(t.get("occupied", 0), "Occupied"),
            tile(t.get("free", 0), "Free"),
            tile(t.get("cleaning", 0), "Cleaning"),
            tile(f'{t.get("occupancy_pct", 0)}%', "Occupancy"),
        ]], colWidths=[page_width / 5] * 5)
        tiles_row.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fafafa')),
            ('BOX', (0, 0), (-1, -1), 0.4, colors.grey),
            ('GRID', (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ]))
        elements.append(tiles_row)

        if t.get("on_leave", 0):
            elements.append(Spacer(1, 4))
            elements.append(Paragraph(f"On Leave (LOA): {t['on_leave']}",
                ParagraphStyle('OL', parent=self.styles['Normal'], fontSize=10, alignment=1,
                    fontName='Helvetica-Bold', textColor=colors.HexColor('#cc7700'))))

        # Per-department table
        elements.append(Paragraph("Per-ward / department", section))
        rows = [[Paragraph(h, cell_b) for h in
                 ["Department", "Rooms", "Total beds", "Occupied", "Free", "Cleaning", "On leave"]]]
        for d in payload.get("by_department", []):
            rows.append([
                Paragraph(d["department"], cell),
                Paragraph(str(d["rooms"]), cell),
                Paragraph(str(d["total_beds"]), cell),
                Paragraph(str(d["occupied"]), cell),
                Paragraph(str(d["free"]), cell),
                Paragraph(str(d["cleaning"]), cell),
                Paragraph(str(d.get("on_leave", 0)), cell),
            ])
        dept_table = Table(rows, colWidths=[page_width * 0.30] + [page_width * 0.117] * 6, repeatRows=1)
        dept_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e0e0e0')),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(dept_table)

        # Per-type table
        elements.append(Paragraph("Per room type", section))
        rows = [[Paragraph(h, cell_b) for h in
                 ["Room type", "Total beds", "Occupied", "Free", "Cleaning"]]]
        for ty in payload.get("by_room_type", []):
            rows.append([
                Paragraph(ty["room_type"], cell),
                Paragraph(str(ty["total_beds"]), cell),
                Paragraph(str(ty["occupied"]), cell),
                Paragraph(str(ty["free"]), cell),
                Paragraph(str(ty["cleaning"]), cell),
            ])
        type_table = Table(rows, colWidths=[page_width * 0.4] + [page_width * 0.15] * 4, repeatRows=1)
        type_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e0e0e0')),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(type_table)

        elements.append(Spacer(1, 14))
        elements.append(Paragraph(
            f"Generated on {datetime.now().strftime('%d/%m/%Y at %H:%M')}",
            ParagraphStyle('F', parent=self.styles['Normal'], fontSize=8, alignment=1)))
        _finalize(doc, elements, hospital_info)
        buffer.seek(0)
        return buffer

    def generate_mlc_register_pdf(self, mlc_data, hospital_info, include_header=True, letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT):
        """Medico-Legal Case (MLC) register entry — printable form for the police
        intimation copy and hospital MLC register. India: required for RTA,
        assault, poisoning, burns, sexual assault, attempted suicide cases."""
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=30, bottomMargin=30)
        elements = []
        page_width = A4[0] - 80

        title = ParagraphStyle('Title', parent=self.styles['Title'],
            fontSize=14, alignment=1, fontName='Helvetica-Bold', textColor=colors.black, spaceAfter=4)
        sub = ParagraphStyle('Sub', parent=self.styles['Normal'],
            fontSize=9, alignment=1, fontName='Helvetica', spaceAfter=2)
        heading = ParagraphStyle('H', parent=self.styles['Normal'],
            fontSize=11, fontName='Helvetica-Bold', spaceAfter=4, spaceBefore=8)
        label = ParagraphStyle('L', parent=self.styles['Normal'], fontSize=9, fontName='Helvetica-Bold')
        value = ParagraphStyle('V', parent=self.styles['Normal'], fontSize=9, fontName='Helvetica')

        if include_header:
            elements.append(Paragraph(hospital_info.get('name', 'HOSPITAL').upper(), title))
            if hospital_info.get('address'):
                elements.append(Paragraph(hospital_info['address'], sub))
            elements.append(Spacer(1, 6))
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        else:
            elements.append(Spacer(1, letterhead_gap_pt))

        elements.append(Spacer(1, 8))
        elements.append(Paragraph("MEDICO-LEGAL CASE (MLC) REGISTER ENTRY",
            ParagraphStyle('M', parent=self.styles['Normal'],
                fontSize=14, alignment=1, fontName='Helvetica-Bold', spaceAfter=6)))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.black))
        elements.append(Spacer(1, 10))

        mlc_type_labels = {
            'rta': 'Road Traffic Accident', 'assault': 'Assault',
            'poisoning': 'Poisoning', 'burn': 'Burn',
            'sexual_assault': 'Sexual Assault',
            'attempted_suicide': 'Attempted Suicide', 'other': 'Other',
        }

        mlc_meta = [
            [Paragraph("MLC Number:", label), Paragraph(str(mlc_data.get('mlc_number') or '—'), value),
             Paragraph("MLC Type:", label), Paragraph(mlc_type_labels.get(mlc_data.get('mlc_type'), mlc_data.get('mlc_type') or '—'), value)],
            [Paragraph("Admission No:", label), Paragraph(str(mlc_data.get('admission_number', '')), value),
             Paragraph("Admission Date:", label), Paragraph(str(mlc_data.get('admission_date', '')), value)],
            [Paragraph("Police Informed:", label), Paragraph(str(mlc_data.get('police_station_informed') or '—'), value),
             Paragraph("Informed At:", label), Paragraph(str(mlc_data.get('mlc_informed_at') or '—'), value)],
        ]
        t = Table(mlc_meta, colWidths=[page_width*0.18, page_width*0.32, page_width*0.18, page_width*0.32])
        t.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('BOTTOMPADDING', (0,0), (-1,-1), 4)]))
        elements.append(t)

        elements.append(Paragraph("PATIENT DETAILS", heading))
        pat_meta = [
            [Paragraph("Name:", label), Paragraph(str(mlc_data.get('patient_name', '')), value),
             Paragraph("Age / Gender:", label), Paragraph(f"{mlc_data.get('age', '')} / {mlc_data.get('gender', '')}", value)],
            [Paragraph("Phone:", label), Paragraph(str(mlc_data.get('phone') or '—'), value),
             Paragraph("Address:", label), Paragraph(str(mlc_data.get('address') or '—'), value)],
            [Paragraph("Brought By:", label), Paragraph(str(mlc_data.get('brought_by') or '—'), value),
             Paragraph("Arrival Mode:", label), Paragraph(str(mlc_data.get('arrival_mode') or '—').replace('_', ' ').title(), value)],
        ]
        t = Table(pat_meta, colWidths=[page_width*0.18, page_width*0.32, page_width*0.18, page_width*0.32])
        t.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('BOTTOMPADDING', (0,0), (-1,-1), 4)]))
        elements.append(t)

        elements.append(Paragraph("CLINICAL FINDINGS ON ARRIVAL", heading))
        body = ParagraphStyle('B', parent=self.styles['Normal'],
            fontSize=10, fontName='Helvetica', spaceAfter=4, leading=14)
        elements.append(Paragraph((mlc_data.get('chief_complaint') or '—').replace('\n', '<br/>'), body))
        if mlc_data.get('ambulance_details'):
            elements.append(Paragraph(f"<b>Ambulance:</b> {mlc_data.get('ambulance_details')}", body))

        elements.append(Paragraph("ATTENDING DOCTOR", heading))
        elements.append(Paragraph(str(mlc_data.get('doctor_name', '')), body))

        # Signatures
        elements.append(Spacer(1, 30))
        sig = Table([
            [Paragraph("Doctor Signature & Seal", label), Paragraph("Police Officer Signature", label)],
            [Paragraph("Name: ____________________", value), Paragraph("Name: ____________________", value)],
            [Paragraph("Date / Time: _____________", value), Paragraph("Designation: _____________", value)],
        ], colWidths=[page_width*0.5, page_width*0.5])
        sig.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('BOTTOMPADDING', (0,0), (-1,-1), 12)]))
        elements.append(sig)

        elements.append(Spacer(1, 14))
        elements.append(Paragraph(
            f"Generated on {datetime.now().strftime('%d/%m/%Y at %H:%M')}",
            ParagraphStyle('F', parent=self.styles['Normal'], fontSize=8, alignment=1)))
        _finalize(doc, elements, hospital_info)
        buffer.seek(0)
        return buffer


    def generate_body_release_pdf(self, rel, hospital_info, include_header=True, letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT):
        """B6 — Body release / mortuary handover form. Signed receipt for the
        family member receiving the body, witnessed by another adult."""
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=30, bottomMargin=30)
        elements = []
        page_width = A4[0] - 80

        title = ParagraphStyle('Title', parent=self.styles['Title'],
            fontSize=14, alignment=1, fontName='Helvetica-Bold', spaceAfter=4)
        sub = ParagraphStyle('Sub', parent=self.styles['Normal'], fontSize=9, alignment=1, spaceAfter=2)
        heading = ParagraphStyle('H', parent=self.styles['Normal'],
            fontSize=11, fontName='Helvetica-Bold', spaceAfter=4, spaceBefore=8)
        label = ParagraphStyle('L', parent=self.styles['Normal'], fontSize=9, fontName='Helvetica-Bold')
        value = ParagraphStyle('V', parent=self.styles['Normal'], fontSize=9, fontName='Helvetica')
        body = ParagraphStyle('B', parent=self.styles['Normal'],
            fontSize=10, fontName='Helvetica', spaceAfter=4, leading=14)

        if include_header:
            elements.append(Paragraph(hospital_info.get('name', 'HOSPITAL').upper(), title))
            if hospital_info.get('address'):
                elements.append(Paragraph(hospital_info['address'], sub))
            elements.append(Spacer(1, 6))
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        else:
            elements.append(Spacer(1, letterhead_gap_pt))

        elements.append(Spacer(1, 8))
        elements.append(Paragraph("BODY RELEASE / HANDOVER FORM",
            ParagraphStyle('R', parent=self.styles['Normal'],
                fontSize=14, alignment=1, fontName='Helvetica-Bold', spaceAfter=6)))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.black))
        elements.append(Spacer(1, 10))

        meta = [
            [Paragraph("Patient Name:", label), Paragraph(str(rel.get('patient_name', '')), value),
             Paragraph("MRN:", label), Paragraph(str(rel.get('mrn', '')), value)],
            [Paragraph("Age / Gender:", label), Paragraph(f"{rel.get('age', '')} / {rel.get('gender', '')}", value),
             Paragraph("Admission No:", label), Paragraph(str(rel.get('admission_number', '')), value)],
            [Paragraph("Date / Time of Death:", label), Paragraph(str(rel.get('death_date', '')), value),
             Paragraph("Attending Doctor:", label), Paragraph(str(rel.get('doctor_name', '')), value)],
            [Paragraph("MLC:", label), Paragraph(("Yes — " + rel.get('mlc_number', '')) if rel.get('is_mlc') else "No", value),
             Paragraph("Mortuary Slot:", label), Paragraph(str(rel.get('mortuary_slot') or '—'), value)],
        ]
        t = Table(meta, colWidths=[page_width*0.18, page_width*0.32, page_width*0.18, page_width*0.32])
        t.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('BOTTOMPADDING', (0,0), (-1,-1), 4)]))
        elements.append(t)

        elements.append(Paragraph("MORTUARY / EMBALMING / POST-MORTEM", heading))
        m = [
            [Paragraph("Body in mortuary:", label), Paragraph(str(rel.get('body_in_at') or '—'), value),
             Paragraph("Body out:", label), Paragraph(str(rel.get('body_out_at') or '—'), value)],
            [Paragraph("Embalming:", label), Paragraph("Done — " + (rel.get('embalmed_by') or '') if rel.get('embalming_done') else "Not done", value),
             Paragraph("Embalmed at:", label), Paragraph(str(rel.get('embalming_at') or '—'), value)],
            [Paragraph("Post-mortem:", label),
             Paragraph(("Required @ " + (rel.get('pm_hospital') or '—')) if rel.get('post_mortem_required') else "Not required", value),
             Paragraph("PM completed:", label), Paragraph(str(rel.get('pm_completed_at') or '—'), value)],
            [Paragraph("PM Doctor:", label), Paragraph(str(rel.get('pm_doctor') or '—'), value),
             Paragraph("PM Report No.:", label), Paragraph(str(rel.get('pm_report_number') or '—'), value)],
            [Paragraph("Police NOC:", label),
             Paragraph(("Received #" + (rel.get('police_noc_number') or '')) if rel.get('police_noc_received') else "Not received", value),
             Paragraph("NOC at:", label), Paragraph(str(rel.get('police_noc_received_at') or '—'), value)],
        ]
        tm = Table(m, colWidths=[page_width*0.18, page_width*0.32, page_width*0.18, page_width*0.32])
        tm.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('BOTTOMPADDING', (0,0), (-1,-1), 4)]))
        elements.append(tm)

        elements.append(Paragraph("RELEASED TO", heading))
        r = [
            [Paragraph("Name:", label), Paragraph(str(rel.get('released_to_name', '')), value),
             Paragraph("Relationship:", label), Paragraph(str(rel.get('released_to_relationship', '')), value)],
            [Paragraph("Phone:", label), Paragraph(str(rel.get('released_to_phone') or '—'), value),
             Paragraph("ID Proof:", label),
             Paragraph(f"{rel.get('released_to_id_proof_type', '').title()} — {rel.get('released_to_id_proof_number', '')}", value)],
            [Paragraph("Address:", label), Paragraph(str(rel.get('released_to_address') or '—'), value),
             Paragraph("Released at:", label), Paragraph(str(rel.get('body_released_at') or '—'), value)],
        ]
        tr = Table(r, colWidths=[page_width*0.18, page_width*0.32, page_width*0.18, page_width*0.32])
        tr.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('BOTTOMPADDING', (0,0), (-1,-1), 4)]))
        elements.append(tr)

        if rel.get('transport_details'):
            elements.append(Paragraph("TRANSPORT", heading))
            elements.append(Paragraph(str(rel.get('transport_details')), body))

        elements.append(Paragraph("DECLARATION", heading))
        elements.append(Paragraph(
            "I, the undersigned, hereby acknowledge receipt of the deceased's body in good condition. "
            "I have verified the identity of the deceased and confirm my relationship as stated above. "
            "I take full responsibility for further arrangements and absolve the hospital of any further "
            "claims regarding custody of the body.", body))

        # Signature blocks
        elements.append(Spacer(1, 24))
        sig = Table([
            [Paragraph("Receiver Signature", label), Paragraph("Witness Signature", label), Paragraph("Hospital Authority", label)],
            [Paragraph("Name: ___________________", value), Paragraph("Name: ___________________", value), Paragraph("Name: ___________________", value)],
            [Paragraph("Date / Time: __________", value), Paragraph("Phone: __________________", value), Paragraph("Designation: __________", value)],
        ], colWidths=[page_width*0.34, page_width*0.33, page_width*0.33])
        sig.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('BOTTOMPADDING', (0,0), (-1,-1), 12)]))
        elements.append(sig)

        elements.append(Spacer(1, 12))
        elements.append(Paragraph(
            f"Generated on {datetime.now().strftime('%d/%m/%Y at %H:%M')}",
            ParagraphStyle('F', parent=self.styles['Normal'], fontSize=8, alignment=1)))
        _finalize(doc, elements, hospital_info)
        buffer.seek(0)
        return buffer


    # ========================================================================
    # Pharmacy PDFs (Section I)
    # ========================================================================

    def _pharmacy_header(self, elements, hospital_info, include_header, title, page_width,
                         letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT):
        """Header for pharmacy PDFs. Mirrors generate_bill_pdf — logo on the
        left, hospital name/address/contact stacked to the right, divider, then
        the receipt title."""
        title_style = ParagraphStyle('PhTitle', parent=self.styles['Title'],
            fontSize=15, alignment=1, fontName='Helvetica-Bold',
            textColor=colors.black, spaceAfter=2)
        sub_style = ParagraphStyle('PhSub', parent=self.styles['Normal'],
            fontSize=9, alignment=1, fontName='Helvetica',
            textColor=colors.black, spaceAfter=2)
        receipt_title = ParagraphStyle('PhReceipt', parent=self.styles['Normal'],
            fontSize=12, alignment=1, fontName='Helvetica-Bold',
            textColor=colors.black, spaceAfter=4)

        if include_header:
            logo_path = hospital_info.get('logo_url', '')
            uploads_base = _get_uploads_base()
            has_logo = False
            full_logo_path = ''
            if logo_path:
                relative = logo_path.lstrip('/')
                if relative.startswith('uploads/'):
                    relative = relative[len('uploads/'):]
                full_logo_path = os.path.join(uploads_base, relative)
                has_logo = os.path.exists(full_logo_path)

            name = (hospital_info.get('name') or 'PHARMACY').upper()
            header_text_elems = [Paragraph(name, title_style)]
            sub = hospital_info.get('hospital_subname')
            if sub:
                header_text_elems.append(Paragraph(sub, sub_style))
            addr = hospital_info.get('address')
            if addr:
                header_text_elems.append(Paragraph(addr, sub_style))
            contact_parts = []
            if hospital_info.get('email'):
                contact_parts.append(f"Email: {hospital_info['email']}")
            if hospital_info.get('phone'):
                contact_parts.append(f"Phone: {hospital_info['phone']}")
            if contact_parts:
                header_text_elems.append(Paragraph("  |  ".join(contact_parts), sub_style))

            if has_logo:
                try:
                    logo_img = Image(full_logo_path, width=60, height=60)
                    logo_img.hAlign = 'CENTER'
                    header_table = Table([[logo_img, header_text_elems]],
                                         colWidths=[75, page_width - 75])
                    header_table.setStyle(TableStyle([
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('LEFTPADDING', (0, 0), (-1, -1), 0),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                        ('TOPPADDING', (0, 0), (-1, -1), 0),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                    ]))
                    elements.append(header_table)
                except Exception:
                    for el in header_text_elems:
                        elements.append(el)
            else:
                for el in header_text_elems:
                    elements.append(el)

            elements.append(Spacer(1, 6))
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        else:
            elements.append(Spacer(1, letterhead_gap_pt))  # leave room for pre-printed letterhead

        elements.append(Spacer(1, 4))
        elements.append(Paragraph(title, receipt_title))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        elements.append(Spacer(1, 6))

    def generate_pharmacy_sale_invoice_pdf(self, sale_data, hospital_info, include_header=True, letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT):
        """Sale invoice for `pharmacy_sales` row.

        Expected `sale_data` keys:
          sale_number, sale_date, payment_type, status,
          patient_name, patient_phone, patient_ip_id, patient_address,
          doctor_name, doctor_number,
          items: [{medicine_name, batch_number, quantity, free_quantity,
                   rate, rate_tier, discount_pct, tax_pct, line_total}],
          subtotal, discount_total, tax_total, grand_total
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
            rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=20)
        elements = []
        page_width = A4[0] - 60

        is_voided = (sale_data.get('status') == 'voided')
        watermark = "VOIDED" if is_voided else None

        self._pharmacy_header(elements, hospital_info, include_header,
                              "PHARMACY SALE INVOICE", page_width, letterhead_gap_pt)

        # ── Meta strip: sale # / date / payment ───────────────────────────
        cell = ParagraphStyle('C', parent=self.styles['Normal'], fontSize=8,
            fontName='Helvetica', textColor=colors.black, leading=11)
        def lv(label, value):
            return Paragraph(f"<b>{label}:</b> {value}", cell)

        sd = sale_data.get('sale_date')
        try:
            sd_str = datetime.fromisoformat(str(sd)).strftime('%d/%m/%Y %I:%M%p') if sd else ''
        except Exception:
            sd_str = str(sd or '')

        # Meta box rows: sale identity on top, patient identity below. Address
        # spans the right two cells so long addresses don't wrap awkwardly.
        _addr = _patient_address_line(sale_data) or sale_data.get('patient_address') or '—'
        _ipid = sale_data.get('patient_ip_id')
        _patient_label = sale_data.get('patient_name') or '—'
        if _ipid:
            _patient_label = f"{_patient_label}  (IP-ID: {_ipid})"

        meta_rows = [
            [lv("Sale #", sale_data.get('sale_number', '')),
             lv("Date", sd_str),
             lv("Payment", (sale_data.get('payment_type') or '—').upper())],
            [lv("Patient", _patient_label),
             lv("Phone", sale_data.get('patient_phone') or '—'),
             lv("Address", _addr)],
        ]
        if sale_data.get('store_name'):
            meta_rows.insert(1, [lv("Store", sale_data.get('store_name', '')),
                                 Paragraph('', cell), Paragraph('', cell)])
        meta = Table(meta_rows, colWidths=[page_width / 3] * 3)
        meta.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(meta)
        elements.append(Spacer(1, 6))

        # ── Doctor block (only if present; patient now lives in the meta box)
        doc_lines = []
        if sale_data.get('doctor_name'):
            doc_lines.append(lv("Doctor", sale_data['doctor_name']))
        if sale_data.get('doctor_number'):
            doc_lines.append(lv("Reg #", sale_data['doctor_number']))
        if doc_lines:
            party = Table([[doc_lines]], colWidths=[page_width])
            party.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            elements.append(party)
            elements.append(Spacer(1, 6))

        # ── Items table ──────────────────────────────────────────────────
        header_p = ParagraphStyle('H', parent=cell, fontName='Helvetica-Bold')
        rows = [[
            Paragraph("#", header_p), Paragraph("Medicine", header_p),
            Paragraph("Batch", header_p), Paragraph("Qty", header_p),
            Paragraph("Free", header_p), Paragraph("Rate", header_p),
            Paragraph("Tier", header_p), Paragraph("Disc%", header_p),
            Paragraph("Tax%", header_p), Paragraph("Amount", header_p),
        ]]
        for i, it in enumerate(sale_data.get('items') or [], start=1):
            qty_text = it.get('qty_display') or f"{it.get('quantity', 0)}"
            rows.append([
                Paragraph(str(i), cell),
                Paragraph(str(it.get('medicine_name') or ''), cell),
                Paragraph(str(it.get('batch_number') or '—'), cell),
                Paragraph(str(qty_text), cell),
                Paragraph(f"{it.get('free_quantity', 0)}", cell),
                Paragraph(f"Rs. {it.get('rate', 0):.2f}", cell),
                Paragraph(str(it.get('rate_tier') or '—'), cell),
                Paragraph(f"{it.get('discount_pct', 0):g}", cell),
                Paragraph(f"{it.get('tax_pct', 0):g}", cell),
                Paragraph(f"Rs. {it.get('line_total', 0):.2f}", cell),
            ])
        # Column widths sum to page_width (≈535pt on A4 with 30pt side margins).
        # Tuned so the "Free", "Disc%", "Tax%" headers fit on a single line and
        # "Rs. 30.00" / "Rs. 150.00" values don't wrap.
        items_tbl = Table(rows, colWidths=[
            22, page_width - (22 + 60 + 38 + 38 + 60 + 30 + 40 + 38 + 70),
            60, 38, 38, 60, 30, 40, 38, 70,
        ])
        items_tbl.setStyle(TableStyle([
            # Light header band with a single rule above and below it — keeps the
            # item rows clean and borderless while still separating the header.
            ('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke),
            ('LINEABOVE', (0, 0), (-1, 0), 0.5, colors.black),
            ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.black),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('ALIGN', (3, 1), (-1, -1), 'RIGHT'),
            ('ALIGN', (0, 1), (0, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(items_tbl)
        elements.append(Spacer(1, 8))

        # ── Totals block (right-aligned) ─────────────────────────────────
        tot_rows = [
            [Paragraph("Subtotal", cell), Paragraph(f"Rs. {sale_data.get('subtotal', 0):.2f}", cell)],
            [Paragraph("Discount", cell), Paragraph(f"−Rs. {sale_data.get('discount_total', 0):.2f}", cell)],
            [Paragraph("Tax (SGST+CGST)", cell), Paragraph(f"+Rs. {sale_data.get('tax_total', 0):.2f}", cell)],
            [Paragraph("<b>Grand Total</b>", cell),
             Paragraph(f"<b>Rs. {sale_data.get('grand_total', 0):.2f}</b>", cell)],
        ]
        tot = Table(tot_rows, colWidths=[120, 90], hAlign='RIGHT')
        tot.setStyle(TableStyle([
            # Single hairline above Grand Total — separates it from the
            # subtotal rows without boxing the whole totals block.
            ('LINEABOVE', (0, -1), (-1, -1), 0.75, colors.black),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(tot)

        if is_voided:
            elements.append(Spacer(1, 8))
            elements.append(Paragraph(
                f"<i>VOIDED — {sale_data.get('void_reason') or 'no reason recorded'}</i>",
                ParagraphStyle('V', parent=cell, fontSize=9, textColor=colors.red),
            ))

        _finalize(doc, elements, hospital_info, watermark=watermark)
        buffer.seek(0)
        return buffer

    def generate_pharmacy_purchase_pdf(self, purchase_data, hospital_info, include_header=True, letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT):
        """GRN / purchase order document for `pharmacy_purchases`.

        Expected keys: purchase_number, entry_date, supplier_name, invoice_number,
        bill_date, payment_type, purchase_type, status,
        items: [{medicine_name, batch_number, expiry_date, mrp, quantity,
                 free_quantity, purchase_rate, discount_pct, tax_amount, line_total}],
        subtotal, total_discount, total_tax, grand_total, notes
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
            rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=20)
        elements = []
        page_width = A4[0] - 60

        self._pharmacy_header(elements, hospital_info, include_header,
                              "PURCHASE / GOODS RECEIPT", page_width, letterhead_gap_pt)

        cell = ParagraphStyle('C', parent=self.styles['Normal'], fontSize=8,
            fontName='Helvetica', textColor=colors.black, leading=11)
        def lv(label, value):
            return Paragraph(f"<b>{label}:</b> {value}", cell)

        # Meta
        meta_rows = [
            [lv("Purchase #", purchase_data.get('purchase_number', '')),
             lv("Entry Date", str(purchase_data.get('entry_date') or '')),
             lv("Status", (purchase_data.get('status') or '—').upper())],
            [lv("Supplier", purchase_data.get('supplier_name') or '—'),
             lv("Invoice #", purchase_data.get('invoice_number') or '—'),
             lv("Payment", (purchase_data.get('payment_type') or '—').upper())],
        ]
        if purchase_data.get('store_name'):
            meta_rows.append([lv("Store", purchase_data.get('store_name', '')),
                              Paragraph('', cell), Paragraph('', cell)])
        meta = Table(meta_rows, colWidths=[page_width / 3] * 3)
        meta.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(meta)
        elements.append(Spacer(1, 6))

        # Items
        header_p = ParagraphStyle('H', parent=cell, fontName='Helvetica-Bold')
        rows = [[
            Paragraph("#", header_p), Paragraph("Medicine", header_p),
            Paragraph("Batch", header_p),
            Paragraph("MRP", header_p), Paragraph("Qty", header_p),
            Paragraph("Free", header_p), Paragraph("P-Rate", header_p),
            Paragraph("Disc%", header_p), Paragraph("Tax", header_p),
            Paragraph("Line", header_p),
        ]]
        for i, it in enumerate(purchase_data.get('items') or [], start=1):
            rows.append([
                Paragraph(str(i), cell),
                Paragraph(str(it.get('medicine_name') or ''), cell),
                Paragraph(str(it.get('batch_number') or '—'), cell),
                Paragraph(f"Rs. {it.get('mrp', 0):.2f}", cell),
                Paragraph(f"{it.get('quantity', 0)}", cell),
                Paragraph(f"{it.get('free_quantity', 0)}", cell),
                Paragraph(f"Rs. {it.get('purchase_rate', 0):.2f}", cell),
                Paragraph(f"{it.get('discount_pct', 0):g}", cell),
                Paragraph(f"Rs. {it.get('tax_amount', 0):.2f}", cell),
                Paragraph(f"Rs. {it.get('line_total', 0):.2f}", cell),
            ])
        items_tbl = Table(rows, colWidths=[
            18, page_width * 0.28, 70, 50, 35, 35, 50, 35, 50, 60,
        ])
        items_tbl.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('ALIGN', (3, 1), (-1, -1), 'RIGHT'),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
        ]))
        elements.append(items_tbl)
        elements.append(Spacer(1, 8))

        # Totals
        tot_rows = [
            [Paragraph("Subtotal", cell), Paragraph(f"Rs. {purchase_data.get('subtotal', 0):.2f}", cell)],
            [Paragraph("Discount", cell), Paragraph(f"−Rs. {purchase_data.get('total_discount', 0):.2f}", cell)],
            [Paragraph("Tax", cell), Paragraph(f"+Rs. {purchase_data.get('total_tax', 0):.2f}", cell)],
            [Paragraph("<b>Grand Total</b>", cell),
             Paragraph(f"<b>Rs. {purchase_data.get('grand_total', 0):.2f}</b>", cell)],
        ]
        tot = Table(tot_rows, colWidths=[120, 90], hAlign='RIGHT')
        tot.setStyle(TableStyle([
            ('BOX', (0, -1), (-1, -1), 0.75, colors.black),
            ('LINEABOVE', (0, -1), (-1, -1), 0.75, colors.black),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(tot)

        if purchase_data.get('notes'):
            elements.append(Spacer(1, 10))
            elements.append(Paragraph(f"<b>Notes:</b> {purchase_data['notes']}",
                ParagraphStyle('N', parent=cell, fontSize=8, leading=11)))

        watermark = None
        if (purchase_data.get('status') or '').lower() == 'draft':
            watermark = "DRAFT"
        _finalize(doc, elements, hospital_info, watermark=watermark)
        buffer.seek(0)
        return buffer

    def generate_pharmacy_transfer_pdf(self, transfer_data, hospital_info, include_header=True, letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT):
        """Stock transfer receipt for master → satellite moves."""
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
            rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=20)
        elements = []
        page_width = A4[0] - 60

        self._pharmacy_header(elements, hospital_info, include_header,
                              "STOCK TRANSFER", page_width, letterhead_gap_pt)

        cell = ParagraphStyle('C', parent=self.styles['Normal'], fontSize=8,
            fontName='Helvetica', textColor=colors.black, leading=11)
        def lv(label, value):
            return Paragraph(f"<b>{label}:</b> {value}", cell)

        meta_rows = [
            [lv("Transfer #", transfer_data.get('transfer_number', '')),
             lv("Date", str(transfer_data.get('entry_date') or '')),
             lv("Status", (transfer_data.get('status') or '—').upper())],
            [lv("From", transfer_data.get('from_store_name') or '—'),
             lv("To", transfer_data.get('to_store_name') or '—'),
             lv("Items", str(transfer_data.get('item_count') or 0))],
        ]
        meta = Table(meta_rows, colWidths=[page_width / 3] * 3)
        meta.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(meta)
        elements.append(Spacer(1, 6))

        header_p = ParagraphStyle('H', parent=cell, fontName='Helvetica-Bold')
        rows = [[Paragraph("#", header_p), Paragraph("Medicine", header_p),
                 Paragraph("Batch", header_p), Paragraph("Qty", header_p)]]
        for i, it in enumerate(transfer_data.get('items') or [], start=1):
            rows.append([
                Paragraph(str(i), cell),
                Paragraph(str(it.get('medicine_name') or ''), cell),
                Paragraph(str(it.get('batch_number') or ''), cell),
                Paragraph(str(it.get('quantity') or ''), cell),
            ])
        tbl = Table(rows, colWidths=[page_width * 0.06, page_width * 0.44, page_width * 0.25, page_width * 0.25])
        tbl.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(tbl)

        if transfer_data.get('notes'):
            elements.append(Spacer(1, 10))
            elements.append(Paragraph(f"<b>Notes:</b> {transfer_data['notes']}",
                ParagraphStyle('N', parent=cell, fontSize=8, leading=11)))

        _finalize(doc, elements, hospital_info)
        buffer.seek(0)
        return buffer

    def generate_pharmacy_dispense_slip_pdf(self, dispense_data, hospital_info, include_header=True, letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT):
        """Dispense slip — handed to the patient on Rx-linked dispensing.

        Expected keys: prescription_number, prescription_date, patient_name,
        doctor_name, lines: [{medicine_name, batch_number, quantity}],
        dispensed_by, notes
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
            rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=20)
        elements = []
        page_width = A4[0] - 60

        self._pharmacy_header(elements, hospital_info, include_header,
                              "DISPENSE SLIP", page_width, letterhead_gap_pt)

        cell = ParagraphStyle('C', parent=self.styles['Normal'], fontSize=8,
            fontName='Helvetica', textColor=colors.black, leading=11)
        def lv(label, value):
            return Paragraph(f"<b>{label}:</b> {value}", cell)

        meta_rows = [
            [lv("Rx #", dispense_data.get('prescription_number', '')),
             lv("Patient", dispense_data.get('patient_name') or '—')],
            [lv("Doctor", dispense_data.get('doctor_name') or '—'),
             lv("Dispensed by", dispense_data.get('dispensed_by') or '—')],
        ]
        if dispense_data.get('store_name'):
            meta_rows.append([lv("Store", dispense_data.get('store_name', '')),
                              Paragraph('', cell)])
        _meta_style = [
            ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]
        _disp_addr = _patient_address_line(dispense_data)
        if _disp_addr:
            _row_idx = len(meta_rows)
            meta_rows.append([lv("Address", _disp_addr), ''])
            _meta_style.append(('SPAN', (0, _row_idx), (1, _row_idx)))
        meta = Table(meta_rows, colWidths=[page_width / 2] * 2)
        meta.setStyle(TableStyle(_meta_style))
        elements.append(meta)
        elements.append(Spacer(1, 6))

        header_p = ParagraphStyle('H', parent=cell, fontName='Helvetica-Bold')
        rows = [[
            Paragraph("#", header_p), Paragraph("Medicine", header_p),
            Paragraph("Batch", header_p), Paragraph("Quantity", header_p),
        ]]
        for i, ln in enumerate(dispense_data.get('lines') or [], start=1):
            rows.append([
                Paragraph(str(i), cell),
                Paragraph(str(ln.get('medicine_name') or ''), cell),
                Paragraph(str(ln.get('batch_number') or '—'), cell),
                Paragraph(f"{ln.get('quantity', 0)}", cell),
            ])
        tbl = Table(rows, colWidths=[20, page_width - 200, 80, 80])
        tbl.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('ALIGN', (3, 1), (3, -1), 'RIGHT'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
        ]))
        elements.append(tbl)

        if dispense_data.get('notes'):
            elements.append(Spacer(1, 8))
            elements.append(Paragraph(f"<b>Notes:</b> {dispense_data['notes']}",
                ParagraphStyle('N', parent=cell, fontSize=8, leading=11)))

        _finalize(doc, elements, hospital_info)
        buffer.seek(0)
        return buffer

    def generate_narcotic_register_pdf(self, rows, period, hospital_info, include_header=True, letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT):
        """Narcotic / Schedule-H register for compliance.

        `rows` is a list of dicts with keys: sale_date, sale_number,
        medicine_name, quantity, batch_number, patient_name, patient_phone,
        doctor_name, schedule.
        `period` is a {from, to} dict (strings).
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
            rightMargin=20, leftMargin=20, topMargin=30, bottomMargin=20)
        elements = []
        page_width = A4[0] - 40

        self._pharmacy_header(elements, hospital_info, include_header,
                              "NARCOTIC / SCHEDULE-H REGISTER", page_width, letterhead_gap_pt)

        cell = ParagraphStyle('C', parent=self.styles['Normal'], fontSize=7,
            fontName='Helvetica', textColor=colors.black, leading=10)
        if period:
            elements.append(Paragraph(
                f"<b>Period:</b> {period.get('from') or '—'} to {period.get('to') or '—'} "
                f"&nbsp;&nbsp;&nbsp;<b>Entries:</b> {len(rows)}",
                ParagraphStyle('P', parent=cell, fontSize=9)))
            elements.append(Spacer(1, 6))

        header_p = ParagraphStyle('H', parent=cell, fontName='Helvetica-Bold')
        out = [[
            Paragraph("Date", header_p), Paragraph("Sale #", header_p),
            Paragraph("Medicine", header_p), Paragraph("Schedule", header_p),
            Paragraph("Qty", header_p), Paragraph("Batch", header_p),
            Paragraph("Patient", header_p), Paragraph("Phone", header_p),
            Paragraph("Doctor", header_p),
        ]]
        for r in rows or []:
            try:
                d = datetime.fromisoformat(str(r.get('sale_date')))
                d_str = d.strftime('%d/%m/%Y %H:%M')
            except Exception:
                d_str = str(r.get('sale_date') or '')
            out.append([
                Paragraph(d_str, cell),
                Paragraph(str(r.get('sale_number') or ''), cell),
                Paragraph(str(r.get('medicine_name') or ''), cell),
                Paragraph(str(r.get('schedule') or '').replace('_', ' ').title(), cell),
                Paragraph(f"{r.get('quantity', 0)}", cell),
                Paragraph(str(r.get('batch_number') or '—'), cell),
                Paragraph(str(r.get('patient_name') or '—'), cell),
                Paragraph(str(r.get('patient_phone') or '—'), cell),
                Paragraph(str(r.get('doctor_name') or '—'), cell),
            ])
        tbl = Table(out, colWidths=[
            65, 70, page_width * 0.18, 55, 28, 55,
            page_width * 0.15, 60, page_width * 0.13,
        ], repeatRows=1)
        tbl.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('ALIGN', (4, 1), (4, -1), 'RIGHT'),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(tbl)
        _finalize(doc, elements, hospital_info)
        buffer.seek(0)
        return buffer


    def generate_pharmacy_report_pdf(
        self, *, title: str, period: Optional[dict],
        columns: list, rows: list, hospital_info: dict,
        include_header: bool = True, letterhead_gap_pt: float = DEFAULT_LETTERHEAD_GAP_PT,
        meta: Optional[dict] = None,
    ):
        """Generic landscape tabular PDF for Phase-2 pharmacy reports.

        `columns` is a list of dicts: {key, label, align?, width?, formatter?}
          - key: the dict field on each row to pull
          - label: column header text
          - align: 'LEFT' (default) | 'RIGHT' | 'CENTER'
          - width: relative weight (any positive number); widths normalized to page
          - formatter: optional callable(value) -> str

        `period`: {from, to} strings shown in the sub-header. `meta`: optional
        extra dict of {label: value} pairs to render alongside the period.
        """
        from reportlab.lib.pagesizes import landscape, A4 as _A4
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=landscape(_A4),
            rightMargin=20, leftMargin=20, topMargin=30, bottomMargin=20,
        )
        elements = []
        page_width = landscape(_A4)[0] - 40

        self._pharmacy_header(elements, hospital_info, include_header, title, page_width,
                              letterhead_gap_pt)

        cell = ParagraphStyle('GenCell', parent=self.styles['Normal'], fontSize=7,
                              fontName='Helvetica', textColor=colors.black, leading=10)
        sub = ParagraphStyle('GenSub', parent=cell, fontSize=9)
        header_p = ParagraphStyle('GenHdr', parent=cell, fontName='Helvetica-Bold')

        sub_bits = []
        if period:
            sub_bits.append(
                f"<b>Period:</b> {period.get('from') or '—'} to {period.get('to') or '—'}"
            )
        sub_bits.append(f"<b>Rows:</b> {len(rows)}")
        for k, v in (meta or {}).items():
            sub_bits.append(f"<b>{k}:</b> {v}")
        elements.append(Paragraph("&nbsp;&nbsp;&nbsp;".join(sub_bits), sub))
        elements.append(Spacer(1, 6))

        out = [[Paragraph(c.get('label', c['key']), header_p) for c in columns]]
        for r in rows or []:
            cells = []
            for c in columns:
                val = r.get(c['key']) if isinstance(r, dict) else getattr(r, c['key'], None)
                fmt = c.get('formatter')
                if fmt is not None:
                    s = fmt(val)
                elif val is None:
                    s = '—'
                elif isinstance(val, float):
                    s = f"{val:,.2f}"
                elif isinstance(val, int):
                    s = f"{val:,}"
                else:
                    s = str(val)
                cells.append(Paragraph(s, cell))
            out.append(cells)

        weights = [float(c.get('width', 1)) for c in columns]
        total = sum(weights) or 1.0
        col_widths = [page_width * w / total for w in weights]

        tbl = Table(out, colWidths=col_widths, repeatRows=1)
        style = [
            ('BOX', (0, 0), (-1, -1), 0.5, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]
        for col_idx, c in enumerate(columns):
            a = (c.get('align') or 'LEFT').upper()
            if a in ('RIGHT', 'CENTER'):
                style.append(('ALIGN', (col_idx, 1), (col_idx, -1), a))
        tbl.setStyle(TableStyle(style))
        elements.append(tbl)
        _finalize(doc, elements, hospital_info)
        buffer.seek(0)
        return buffer


    def generate_canteen_sale_receipt_pdf(
        self, sale_data, hospital_info, include_header=True, letterhead_gap_pt=DEFAULT_LETTERHEAD_GAP_PT,
    ):
        """Walk-in canteen POS receipt."""
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=20,
        )
        elements = []
        page_width = A4[0] - 60
        is_voided = (sale_data.get("status") == "voided")

        self._pharmacy_header(
            elements, hospital_info, include_header,
            "CANTEEN SALE RECEIPT", page_width, letterhead_gap_pt,
        )

        cell = ParagraphStyle(
            "C", parent=self.styles["Normal"], fontSize=8,
            fontName="Helvetica", textColor=colors.black, leading=11,
        )

        def lv(label, value):
            return Paragraph(f"<b>{label}:</b> {value}", cell)

        sd = sale_data.get("sale_date")
        try:
            sd_str = datetime.fromisoformat(str(sd)).strftime("%d/%m/%Y %I:%M%p") if sd else ""
        except Exception:
            sd_str = str(sd or "")

        meta = Table(
            [
                [
                    lv("Sale #", sale_data.get("sale_number", "")),
                    lv("Date", sd_str),
                    lv("Payment", (sale_data.get("payment_type") or "—").upper()),
                ],
                [
                    lv("Customer", sale_data.get("customer_name") or "Walk-in"),
                    lv("Phone", sale_data.get("customer_phone") or "—"),
                    lv("Status", (sale_data.get("status") or "—").upper()),
                ],
            ],
            colWidths=[page_width / 3] * 3,
        )
        meta.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(meta)
        elements.append(Spacer(1, 8))

        header_p = ParagraphStyle("H", parent=cell, fontName="Helvetica-Bold")
        rows = [[
            Paragraph("#", header_p),
            Paragraph("Item", header_p),
            Paragraph("Qty", header_p),
            Paragraph("Rate", header_p),
            Paragraph("Amount", header_p),
        ]]
        for i, it in enumerate(sale_data.get("items") or [], start=1):
            rows.append([
                Paragraph(str(i), cell),
                Paragraph(str(it.get("item_name") or ""), cell),
                Paragraph(str(it.get("quantity") or 0), cell),
                Paragraph(f"{float(it.get('unit_price') or 0):.2f}", cell),
                Paragraph(f"{float(it.get('line_total') or 0):.2f}", cell),
            ])
        tbl = Table(rows, colWidths=[30, page_width - 210, 50, 65, 65])
        tbl.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        elements.append(tbl)
        elements.append(Spacer(1, 8))

        totals = Table(
            [
                [Paragraph("<b>Subtotal</b>", cell), Paragraph(f"₹{float(sale_data.get('subtotal') or 0):.2f}", cell)],
                [Paragraph("Discount", cell), Paragraph(f"₹{float(sale_data.get('discount_amount') or 0):.2f}", cell)],
                [Paragraph("<b>Grand Total</b>", cell), Paragraph(f"<b>₹{float(sale_data.get('grand_total') or 0):.2f}</b>", cell)],
            ],
            colWidths=[page_width - 100, 100],
        )
        totals.setStyle(TableStyle([
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        elements.append(totals)

        if sale_data.get("notes"):
            elements.append(Spacer(1, 6))
            elements.append(Paragraph(f"<b>Notes:</b> {sale_data['notes']}", cell))
        if is_voided:
            elements.append(Spacer(1, 8))
            void_style = ParagraphStyle(
                "Void", parent=self.styles["Normal"], fontSize=14,
                alignment=1, fontName="Helvetica-Bold", textColor=colors.red,
            )
            elements.append(Paragraph("*** VOIDED ***", void_style))
            if sale_data.get("void_reason"):
                elements.append(Paragraph(f"Reason: {sale_data['void_reason']}", cell))

        doc.build(elements)
        buffer.seek(0)
        return buffer


# Create global instance
pdf_service = PDFService()
