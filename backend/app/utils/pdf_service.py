from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, HRFlowable, XPreformatted
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from io import BytesIO
from datetime import datetime
import os


def _get_uploads_base():
    """Get the uploads directory path. Works in both dev and bundled (.exe) mode."""
    try:
        from app.utils.paths import get_uploads_dir
        return get_uploads_dir()
    except Exception:
        return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")


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

    def generate_inpatient_bill_pdf(self, bill_data, hospital_info, include_header=True):
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
        print_date_str = datetime.now().strftime('%d/%m/%Y  %I:%M:%S%p')

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
            elements.append(Spacer(1, 100))

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
        age_sex = ''
        if p.get('age') not in (None, ''):
            age_sex = f"{p.get('age')} Years"
        if p.get('gender'):
            g = str(p['gender']).upper()
            age_sex = f"{age_sex} / {g}" if age_sex else g

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
            [lv('Phone', p.get('phone', '')),               lv('Print Date', print_date_str)],
            [lv('MRN',   p.get('mrn') or p.get('patient_id', '')),
             lv('Pay Mode',   payer_str)],
            [lv('Referred By', ref_value),                  Paragraph('', cell_value)],
        ]
        info_table = Table(info_data, colWidths=[col_w, col_w])
        info_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ]))
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
        # ITEMS TABLE — Sno | Description | Code | Rate (same as OPD)
        # ============================================================
        sno_w = 0.4 * inch
        code_w = 1.0 * inch
        rate_w = 1.2 * inch
        desc_w = page_width - sno_w - code_w - rate_w

        items_header = [
            Paragraph('<b>Sno</b>', cell_label),
            Paragraph('<b>Description</b>', cell_label),
            Paragraph('<b>Qty</b>', cell_label),
            Paragraph('<b>Rate</b>', ParagraphStyle('R', parent=cell_label, alignment=2)),
        ]
        items_data = [items_header]
        items = bill_data.get('items') or []
        for idx, it in enumerate(items, start=1):
            items_data.append([
                Paragraph(str(idx), cell_value),
                Paragraph(it.get('description', ''), cell_value),
                Paragraph(str(it.get('qty', '')) or '—', cell_value),
                Paragraph(
                    f"{float(it.get('amount') or 0):,.2f}",
                    ParagraphStyle('R', parent=cell_value, alignment=2),
                ),
            ])
        if len(items_data) == 1:
            items_data.append([
                Paragraph('—', cell_value),
                Paragraph('No itemised charges', cell_value),
                Paragraph('—', cell_value),
                Paragraph('0.00',
                    ParagraphStyle('R', parent=cell_value, alignment=2)),
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

        summary_label_w = page_width - code_w - rate_w
        payment_data = [
            [lv_sm('Paymode', payer_str),
             Paragraph('<b>Sub Total</b>', cell_value_sm),
             Paragraph(f"{subtotal:,.2f}", cell_value_right)],
        ]
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
        payment_data.extend([
            [Paragraph('', cell_value_sm),
             Paragraph('<b>Total Amt</b>', cell_value_sm),
             Paragraph(f"{total:,.2f}", cell_value_right)],
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
        payment_table = Table(payment_data, colWidths=[summary_label_w, code_w, rate_w])
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

        doc.build(elements)
        buffer.seek(0)
        return buffer


    def generate_bill_pdf(self, bill_data, hospital_info, include_header=True):
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

        print_date_str = datetime.now().strftime('%d/%m/%Y  %I:%M:%S%p')

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
            elements.append(Spacer(1, 100))

        elements.append(Spacer(1, 4))
        elements.append(Paragraph("RECEIPT CUM REQUISITION", receipt_title_style))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        elements.append(Spacer(1, 6))

        # ============================================================
        # PATIENT INFO + BILL INFO (bordered box, like lab report)
        # ============================================================
        patient_name = bill_data.get('patient_name', '')
        _age_raw = bill_data.get('patient_age')
        age_sex = f"{_age_raw} Years" if _age_raw is not None and _age_raw != '' else ''
        if bill_data.get('patient_gender'):
            gender = bill_data['patient_gender'].upper()
            if age_sex:
                age_sex = f"{age_sex} / {gender}"
            else:
                age_sex = gender

        phone = bill_data.get('patient_phone', '')
        patient_id = bill_data.get('mrn') or bill_data.get('patient_id', bill_data.get('reg_no', ''))
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

        patient_info_data = [
            [lv('Name', patient_name), lv('Bill No', bill_no)],
            [lv('Age / Gender', age_sex), lv('Bill Date', bill_date_str)],
            [lv('Phone', phone), lv('Print Date', print_date_str)],
            [lv('MRN', patient_id), lv('Pay Mode', pay_category)],
            [lv(ref_label, ref_value), Paragraph('', cell_value)],
        ]

        info_table = Table(patient_info_data, colWidths=[col_w, col_w])
        info_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ]))
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

        payment_data = [
            [lv_sm('Paymode', pay_category), Paragraph('<b>Total Amt</b>', cell_value_sm), Paragraph(f"{total_amt:.2f}", cell_value_right)],
            [Paragraph('', cell_value_sm), Paragraph('<b>Discount</b>', cell_value_sm), Paragraph(f"{discount:.2f}", cell_value_right)],
        ]
        if tax_amt:
            payment_data.append(
                [Paragraph('', cell_value_sm), Paragraph('<b>Tax</b>', cell_value_sm), Paragraph(f"{tax_amt:.2f}", cell_value_right)]
            )
        payment_data.append(
            [Paragraph('', cell_value_sm), Paragraph('<b>Net Total</b>', cell_value_sm), Paragraph(f"{net_total:.2f}", cell_value_right)]
        )
        if not hide_payment_summary:
            payment_data.append(
                [Paragraph('', cell_value_sm), Paragraph('<b>Paid Amt</b>', cell_value_sm), Paragraph(f"{paid_amt:.2f}", cell_value_right)]
            )
            payment_data.append(
                [Paragraph('', cell_value_sm), Paragraph('<b>Balance</b>', cell_value_sm), Paragraph(f"{balance:.2f}", cell_value_right)]
            )

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
        doc.build(elements)
        buffer.seek(0)
        return buffer

    def generate_prescription_pdf(self, prescription_data, hospital_info, include_header=True):
        """Generate PDF for prescription matching the reference layout:
        Header → Doctor+Patient info box → Diagnosis → Vitals (left) + Medicines (right) → Instructions
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
            elements.append(Spacer(1, 100))

        # ============================================================
        # PATIENT + DOCTOR INFO — bordered box (like lab report)
        # ============================================================
        doctor_name = prescription_data.get('doctor_name', '')
        doctor_spec = prescription_data.get('doctor_specialization', '')
        doctor_reg = prescription_data.get('doctor_registration_number', '')
        patient_name = prescription_data.get('patient_name', '')
        patient_age = prescription_data.get('patient_age', '')
        patient_gender = prescription_data.get('patient_gender', '')
        patient_blood_group = prescription_data.get('patient_blood_group', '')
        patient_phone = prescription_data.get('patient_phone', '')
        patient_id = prescription_data.get('mrn') or prescription_data.get('patient_id_display', prescription_data.get('patient_id', ''))

        age_sex = f"{patient_age} Years" if patient_age is not None and patient_age != '' else ''
        if patient_gender:
            age_sex = f"{age_sex} / {patient_gender.capitalize()}" if age_sex else patient_gender.capitalize()

        doctor_display = doctor_name
        if doctor_spec:
            doctor_display = f"{doctor_name} ({doctor_spec})"

        col_w = page_width / 2
        info_data = [
            [Paragraph(f"<b>Name</b> :  {patient_name}", cell_val), Paragraph(f"<b>Prescribed By</b> :  {doctor_display}", cell_val)],
            [Paragraph(f"<b>Age / Gender</b> :  {age_sex}", cell_val), Paragraph(f"<b>Reg. No.</b> :  {doctor_reg or '—'}", cell_val)],
            [Paragraph(f"<b>Phone</b> :  {patient_phone}", cell_val), Paragraph(f"<b>Date</b> :  {rx_date}", cell_val)],
            [Paragraph(f"<b>MRN</b> :  {patient_id}", cell_val), Paragraph(f"<b>Blood Group</b> :  {patient_blood_group or '—'}", cell_val)],
        ]

        info_table = Table(info_data, colWidths=[col_w, col_w])
        info_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 10))

        # ============================================================
        # DIAGNOSIS — bordered section
        # ============================================================
        diagnosis_text = prescription_data.get('diagnosis', '')
        consultation = prescription_data.get('consultation')
        # Add appointment reason if available
        appointment_reason = prescription_data.get('appointment_reason', '')

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
        # VITALS (left) + MEDICINES TABLE (right) — side by side
        # ============================================================
        vitals = prescription_data.get('vitals')
        vitals_left_width = page_width * 0.25
        meds_right_width = page_width * 0.73
        gap = page_width * 0.02

        # --- Build vitals sub-table ---
        vitals_rows = [[Paragraph('<b><u>Vitals</u></b>', cell_lbl), '']]
        if vitals and vitals.get('vital_signs'):
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
        vitals_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('SPAN', (0, 0), (1, 0)),  # header spans
        ]))

        # --- Lab tests ordered (below vitals) ---
        lab_tests = prescription_data.get('lab_tests', [])
        lab_rows = []
        if lab_tests:
            lab_rows.append([Paragraph('<b><u>Tests Done</u></b>', cell_lbl), ''])
            for t in lab_tests:
                status_text = (t.get('status', '') or '').capitalize()
                lab_rows.append([
                    Paragraph(f"&bull; {t.get('test_name', '')}", cell_val_sm),
                    Paragraph(status_text, cell_val_sm),
                ])

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
            left_col_parts.append([Spacer(1, 8)])
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

        # No empty padding rows — only show actual medicines

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

        # Combine vitals + medicines into right column
        meds_combined = [[meds_title_table], [med_table]]
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
        elements.append(Spacer(1, 10))

        # ============================================================
        # INSTRUCTIONS — bordered section
        # ============================================================
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

        # ============================================================
        # SIGNATURE
        # ============================================================
        elements.append(Spacer(1, 30))
        sig_rows = [[
            Paragraph(f"Date: {rx_date}", cell_val),
            Paragraph(f"<b>{doctor_name}</b><br/>"
                      f"{doctor_spec}<br/>"
                      f"Reg. No: {doctor_reg}" if doctor_reg else
                      f"<b>{doctor_name}</b><br/>{doctor_spec}",
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

        doc.build(elements)
        buffer.seek(0)
        return buffer

    def generate_lab_report_pdf(self, report_data, hospital_info, lab_config=None, include_header=True):
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
            fontSize=9, fontName='Helvetica-Bold', textColor=colors.red)

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
            elements.append(Spacer(1, 100))

        elements.append(Spacer(1, 4))
        elements.append(Paragraph("LABORATORY REPORT", report_title_style))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        elements.append(Spacer(1, 6))

        # ============================================================
        # PATIENT INFO — bordered box matching reference layout
        # ============================================================
        def _fmt_dt(val):
            """Format a date/datetime value for display."""
            if not val:
                return '-'
            try:
                if isinstance(val, str):
                    val = datetime.fromisoformat(val.replace('Z', '+00:00'))
                return val.strftime('%d/%m/%Y %I:%M %p')
            except Exception:
                return str(val)

        patient_name = report_data.get('patient_name', '')
        patient_gender = report_data.get('patient_gender', '')
        _age_raw = report_data.get('patient_age')
        age_sex = f"{_age_raw} Years" if _age_raw is not None and _age_raw != '' else ''
        if patient_gender:
            age_sex = f"{age_sex} / {patient_gender.capitalize()}" if age_sex else patient_gender.capitalize()

        order_date_str = _fmt_dt(report_data.get('order_date'))
        collection_date_str = _fmt_dt(report_data.get('collection_date'))
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
            [lv('MRN', report_data.get('mrn') or report_data.get('patient_uuid', '')), lv('Report ID', report_data.get('order_number', ''))],
        ]

        info_table = Table(info_data, colWidths=[col_w, col_w])
        info_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ]))
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
        param_w = page_width * 0.28
        result_w = page_width * 0.15
        unit_w = page_width * 0.12
        ref_w = page_width * 0.25
        method_w = page_width * 0.20

        # Section header style
        section_label_style = ParagraphStyle('LabSectionLabel', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica-Bold', textColor=colors.Color(0.2, 0.2, 0.5))

        results_header = [
            Paragraph('<b>TEST DESCRIPTION</b>', cell_label),
            Paragraph('<b>RESULT</b>', cell_label),
            Paragraph('<b>UNIT</b>', cell_label),
            Paragraph('<b>BIO. REF. RANGE</b>', cell_label),
            Paragraph('<b>METHOD</b>', cell_label),
        ]

        results_data = [results_header]
        results_list = report_data.get('results', [])

        # Track section rows for styling
        section_row_indices = []
        current_section = None

        for r in results_list:
            # Insert section header row if section changed
            section = r.get('section', '')
            if section and section != current_section:
                current_section = section
                section_row_indices.append(len(results_data))
                results_data.append([
                    Paragraph(f'<b>{section}</b>', section_label_style),
                    Paragraph('', cell_value),
                    Paragraph('', cell_value),
                    Paragraph('', cell_value),
                    Paragraph('', cell_value),
                ])
            elif not section and current_section is not None:
                current_section = None

            is_abnormal = r.get('is_abnormal', False)
            value_style = cell_abnormal if is_abnormal else cell_value

            ref_range = '-'
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

            param_text = r.get('parameter_name', '')
            remarks = r.get('remarks', '')
            if remarks:
                param_text = f"{param_text}<br/><i><font size='7' color='grey'>{remarks}</font></i>"

            method_text = r.get('method', '') or ''

            results_data.append([
                Paragraph(param_text, cell_value),
                Paragraph(str(r.get('value', '')), value_style),
                Paragraph(r.get('unit', '') or '-', cell_value),
                Paragraph(ref_range, cell_value),
                Paragraph(method_text, cell_value),
            ])

        results_table = Table(results_data, colWidths=[param_w, result_w, unit_w, ref_w, method_w])

        table_style_cmds = [
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
        ]

        # Style section header rows — span across all columns, light background
        for sec_row in section_row_indices:
            table_style_cmds.append(('SPAN', (0, sec_row), (-1, sec_row)))
            table_style_cmds.append(('BACKGROUND', (0, sec_row), (-1, sec_row), colors.Color(0.92, 0.93, 0.97)))
            table_style_cmds.append(('TOPPADDING', (0, sec_row), (-1, sec_row), 5))
            table_style_cmds.append(('BOTTOMPADDING', (0, sec_row), (-1, sec_row), 5))

        # Highlight abnormal rows (need to account for inserted section rows)
        row_idx = 1  # start after header
        current_section_2 = None
        for r in results_list:
            section = r.get('section', '')
            if section and section != current_section_2:
                current_section_2 = section
                row_idx += 1  # skip section header row
            elif not section and current_section_2 is not None:
                current_section_2 = None

            if r.get('is_abnormal', False):
                table_style_cmds.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.Color(1, 0.95, 0.95)))
            row_idx += 1

        results_table.setStyle(TableStyle(table_style_cmds))
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

        # Footer
        elements.append(Spacer(1, 20))
        elements.append(Paragraph(f"Generated on {datetime.now().strftime('%d/%m/%Y at %H:%M:%S')}", footer_style))

        doc.build(elements)
        buffer.seek(0)
        return buffer

    def generate_combined_lab_report_pdf(self, reports_list, hospital_info, lab_config=None, include_header=True):
        """Generate a single continuous PDF with all tests flowing together.
        Header repeats on every page (or blank space for pre-printed letterhead).
        Patient info on first page only, tests flow continuously, signatures at the end."""
        if lab_config is None:
            lab_config = {}

        buffer = BytesIO()
        # Reserve top margin for the header drawn via onPage callback
        header_height = 100 if include_header else 100  # ~3.5cm
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
            fontSize=9, fontName='Helvetica-Bold', textColor=colors.red)
        normal_text = ParagraphStyle('CLabNormalText', parent=self.styles['Normal'],
            fontSize=10, spaceAfter=6, fontName='Helvetica', textColor=colors.black)
        footer_style = ParagraphStyle('CLabFooter', parent=self.styles['Normal'],
            fontSize=8, alignment=1, fontName='Helvetica', textColor=colors.grey)
        section_label_style = ParagraphStyle('CLabSectionLabel', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica-Bold', textColor=colors.Color(0.2, 0.2, 0.5))

        def lv(label, value):
            return Paragraph(f"<b>{label}</b> :  {value}", cell_value)

        def _fmt_dt(val):
            if not val:
                return '-'
            try:
                if isinstance(val, str):
                    val = datetime.fromisoformat(val.replace('Z', '+00:00'))
                return val.strftime('%d/%m/%Y %I:%M %p')
            except Exception:
                return str(val)

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
        _age_raw = first_report.get('patient_age')
        age_sex = f"{_age_raw} Years" if _age_raw is not None and _age_raw != '' else ''
        if patient_gender:
            age_sex = f"{age_sex} / {patient_gender.capitalize()}" if age_sex else patient_gender.capitalize()

        referral_label = first_report.get('referral_label', 'Referred By')
        referral_name = first_report.get('referral_name', 'Self')
        patient_phone = first_report.get('patient_phone', '')

        col_w = page_width / 2
        info_data = [
            [lv('Name', patient_name), lv('Booked Date', _fmt_dt(first_report.get('order_date')))],
            [lv('Age / Gender', age_sex), lv('Collection Date', _fmt_dt(first_report.get('collection_date')))],
            [lv('Phone', patient_phone), lv('Report Date', _fmt_dt(first_report.get('report_date')))],
            [lv(referral_label, referral_name), lv('Report Status', first_report.get('report_status', 'Final'))],
            [lv('MRN', first_report.get('mrn') or first_report.get('patient_uuid', '')), Paragraph('', cell_value)],
        ]

        info_table = Table(info_data, colWidths=[col_w, col_w])
        info_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 10))

        # ============================================================
        # RESULTS TABLE COLUMN WIDTHS
        # ============================================================
        param_w = page_width * 0.28
        result_w = page_width * 0.15
        unit_w = page_width * 0.12
        ref_w = page_width * 0.25
        method_w = page_width * 0.20

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

            # Results table
            results_header = [
                Paragraph('<b>TEST DESCRIPTION</b>', cell_label),
                Paragraph('<b>RESULT</b>', cell_label),
                Paragraph('<b>UNIT</b>', cell_label),
                Paragraph('<b>BIO. REF. RANGE</b>', cell_label),
                Paragraph('<b>METHOD</b>', cell_label),
            ]
            results_data = [results_header]
            results_list_inner = report_data.get('results', [])

            section_row_indices = []
            current_section = None

            for r in results_list_inner:
                section = r.get('section', '')
                if section and section != current_section:
                    current_section = section
                    section_row_indices.append(len(results_data))
                    results_data.append([
                        Paragraph(f'<b>{section}</b>', section_label_style),
                        Paragraph('', cell_value), Paragraph('', cell_value),
                        Paragraph('', cell_value), Paragraph('', cell_value),
                    ])
                elif not section and current_section is not None:
                    current_section = None

                is_abnormal = r.get('is_abnormal', False)
                value_style = cell_abnormal if is_abnormal else cell_value

                ref_range = '-'
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

                param_text = r.get('parameter_name', '')
                remarks = r.get('remarks', '')
                if remarks:
                    param_text = f"{param_text}<br/><i><font size='7' color='grey'>{remarks}</font></i>"

                method_text = r.get('method', '') or ''

                results_data.append([
                    Paragraph(param_text, cell_value),
                    Paragraph(str(r.get('value', '')), value_style),
                    Paragraph(r.get('unit', '') or '-', cell_value),
                    Paragraph(ref_range, cell_value),
                    Paragraph(method_text, cell_value),
                ])

            results_table = Table(results_data, colWidths=[param_w, result_w, unit_w, ref_w, method_w])

            table_style_cmds = [
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 6), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
            ]

            for sec_row in section_row_indices:
                table_style_cmds.append(('SPAN', (0, sec_row), (-1, sec_row)))
                table_style_cmds.append(('BACKGROUND', (0, sec_row), (-1, sec_row), colors.Color(0.92, 0.93, 0.97)))
                table_style_cmds.append(('TOPPADDING', (0, sec_row), (-1, sec_row), 5))
                table_style_cmds.append(('BOTTOMPADDING', (0, sec_row), (-1, sec_row), 5))

            row_idx = 1
            current_section_2 = None
            for r in results_list_inner:
                section = r.get('section', '')
                if section and section != current_section_2:
                    current_section_2 = section
                    row_idx += 1
                elif not section and current_section_2 is not None:
                    current_section_2 = None
                if r.get('is_abnormal', False):
                    table_style_cmds.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.Color(1, 0.95, 0.95)))
                row_idx += 1

            results_table.setStyle(TableStyle(table_style_cmds))
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

        doc.build(elements, onFirstPage=_draw_header, onLaterPages=_draw_header)
        buffer.seek(0)
        return buffer

    def generate_discharge_summary_pdf(self, discharge_data, hospital_info, include_header=True):
        """Generate PDF for discharge summary"""
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

        # Helper for label:value pairs
        def lv(label, value):
            return Paragraph(f"<b>{label}:</b> {value}", cell_value)

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
            # Leave blank space for pre-printed letterhead
            elements.append(Spacer(1, 100))

        elements.append(Spacer(1, 4))
        elements.append(Paragraph("DISCHARGE SUMMARY", doc_title_style))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        elements.append(Spacer(1, 6))

        # ============================================================
        # PATIENT INFO BOX
        # ============================================================
        _age_raw = discharge_data.get('age')
        age_gender = f"{_age_raw} Years" if _age_raw is not None and _age_raw != '' else ''
        if discharge_data.get('gender'):
            gender = discharge_data['gender'].upper()
            age_gender = f"{age_gender} / {gender}" if age_gender else gender

        col_w = page_width / 2
        patient_info_data = [
            [lv('Patient', discharge_data.get('patient_name', '')),
             lv('MRN', discharge_data.get('mrn') or discharge_data.get('patient_id', ''))],
            [lv('Age / Gender', age_gender),
             lv('Doctor', discharge_data.get('doctor_name', ''))],
            [lv('Admission No', discharge_data.get('admission_number', '')),
             lv('Total Stay', f"{discharge_data.get('total_stay_days', 0)} days")],
            [lv('Admitted', discharge_data.get('admission_date', '')),
             lv('Discharged', discharge_data.get('discharge_date', ''))],
            [lv('Discharge Type', discharge_data.get('discharge_type', '')),
             lv('Condition on Admission', discharge_data.get('condition_on_admission', ''))],
        ]

        info_table = Table(patient_info_data, colWidths=[col_w, col_w])
        info_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 8))

        # ============================================================
        # CLINICAL SECTIONS
        # ============================================================
        sections = [
            ("Diagnosis", discharge_data.get("diagnosis", "")),
            ("Treatment Given", discharge_data.get("treatment", "")),
            ("Discharge Summary", discharge_data.get("discharge_summary", "")),
        ]

        for title, content in sections:
            if content:
                elements.append(Paragraph(title, section_heading))
                # Support multiline content
                for line in content.split('\n'):
                    line = line.strip()
                    if line:
                        elements.append(Paragraph(line, cell_value))

        # ============================================================
        # TAKE-HOME MEDICATIONS — structured list (preferred) or legacy text.
        # ============================================================
        take_home = discharge_data.get("take_home_medications") or []
        if take_home:
            elements.append(Paragraph("Take-Home Medications", section_heading))
            header = ['#', 'Medicine', 'Dosage', 'Frequency', 'Duration', 'Qty', 'Instructions']
            rows = [header]
            for i, m in enumerate(take_home, start=1):
                rows.append([
                    str(i),
                    str(m.get('medicine_name') or ''),
                    str(m.get('dosage') or ''),
                    str(m.get('frequency') or ''),
                    str(m.get('duration') or ''),
                    str(m.get('quantity') or ''),
                    str(m.get('instructions') or ''),
                ])
            med_table = Table(rows, colWidths=[20, 130, 70, 70, 60, 30, 130])
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
            # Legacy free-text fallback for older discharges
            medications = discharge_data.get("medications", "")
            if medications:
                elements.append(Paragraph("Medications Prescribed", section_heading))
                med_lines = [m.strip() for m in medications.replace(';', '\n').split('\n') if m.strip()]
                if len(med_lines) > 1:
                    for med in med_lines:
                        bullet = med if med.startswith(('•', '-', '*')) else f"• {med}"
                        elements.append(Paragraph(bullet, cell_value))
                else:
                    elements.append(Paragraph(medications, cell_value))

        # ============================================================
        # FOLLOW-UP INSTRUCTIONS
        # ============================================================
        follow_up = discharge_data.get("follow_up", "")
        follow_up_date = discharge_data.get("follow_up_date", "")
        if follow_up or follow_up_date:
            elements.append(Paragraph("Follow-up Instructions", section_heading))
            if follow_up:
                elements.append(Paragraph(follow_up, cell_value))
            if follow_up_date:
                elements.append(Paragraph(f"<b>Follow-up Date:</b> {follow_up_date}", cell_value))

        # ============================================================
        # DIET & ACTIVITY
        # ============================================================
        diet = discharge_data.get("diet_instructions", "")
        activity = discharge_data.get("activity_restrictions", "")
        if diet or activity:
            elements.append(Paragraph("Diet &amp; Activity", section_heading))
            if diet:
                elements.append(Paragraph(f"<b>Diet:</b> {diet}", cell_value))
            if activity:
                elements.append(Paragraph(f"<b>Activity Restrictions:</b> {activity}", cell_value))

        # ============================================================
        # CONDITION ON DISCHARGE & PREPARED BY
        # ============================================================
        elements.append(Spacer(1, 16))
        condition_discharge = discharge_data.get("condition_on_discharge", "")
        if condition_discharge:
            elements.append(Paragraph(f"<b>Condition on Discharge:</b> {condition_discharge}", cell_value))
            elements.append(Spacer(1, 12))

        doctor_name = discharge_data.get("doctor_name", "")
        if doctor_name:
            sig_data = [
                [Paragraph('', cell_value),
                 Paragraph('_' * 30, ParagraphStyle('SigLine', parent=self.styles['Normal'],
                    fontSize=9, alignment=2))],
                [Paragraph('', cell_value),
                 Paragraph(f"<b>{doctor_name}</b>", ParagraphStyle('SigName', parent=self.styles['Normal'],
                    fontSize=9, fontName='Helvetica-Bold', alignment=2))],
                [Paragraph('', cell_value),
                 Paragraph("Attending Physician", ParagraphStyle('SigTitle', parent=self.styles['Normal'],
                    fontSize=8, fontName='Helvetica', textColor=colors.grey, alignment=2))],
            ]
            sig_table = Table(sig_data, colWidths=[page_width / 2, page_width / 2])
            sig_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
                ('TOPPADDING', (0, 0), (-1, -1), 1),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ]))
            elements.append(sig_table)

        # ============================================================
        # FOOTER
        # ============================================================
        elements.append(Spacer(1, 20))
        elements.append(Paragraph(
            f"Generated on {datetime.now().strftime('%d/%m/%Y at %H:%M:%S')}",
            footer_style
        ))

        doc.build(elements)
        buffer.seek(0)
        return buffer

    def generate_deposit_receipt_pdf(self, deposit_data, hospital_info, include_header=True):
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
        print_date_str = datetime.now().strftime('%d/%m/%Y  %I:%M:%S%p')

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
            elements.append(Spacer(1, 100))

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
            [lv('MRN', deposit_data.get('patient_id', '')),
             lv('Print Date', print_date_str)],
            [lv('Admission No', deposit_data.get('admission_number', '')),
             lv('Pay Mode', pay_method)],
            [lv('Type', deposit_type_label),
             lv('Reference', deposit_data.get('reference_number') or '-')],
        ]
        info_table = Table(info_data, colWidths=[col_w, col_w])
        info_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ]))
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

        doc.build(elements)
        buffer.seek(0)
        return buffer

    def generate_refund_receipt_pdf(self, refund_data, hospital_info, include_header=True):
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
            elements.append(Spacer(1, 90))

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
        meta_table = Table(rows, colWidths=[page_width * 0.20, page_width * 0.30, page_width * 0.18, page_width * 0.32])
        meta_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
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

        doc.build(elements)
        buffer.seek(0)
        return buffer

    def generate_credit_note_pdf(self, cn_data, hospital_info, include_header=True):
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
            elements.append(Spacer(1, 90))

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
        meta = Table(rows, colWidths=[page_width * 0.20, page_width * 0.30, page_width * 0.18, page_width * 0.32])
        meta.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
        elements.append(meta)
        elements.append(Spacer(1, 10))

        # Line items
        items = cn_data.get('items') or []
        if items:
            head = [Paragraph("<b>Item</b>", value_style), Paragraph("<b>Qty</b>", value_style),
                    Paragraph("<b>Unit ₹</b>", value_style), Paragraph("<b>Total ₹</b>", value_style)]
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

        doc.build(elements)
        buffer.seek(0)
        return buffer

    def generate_consent_pdf(self, consent_data, hospital_info, include_header=True):
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
            # Header row: hospital name left, doc number right
            header_rows = [[
                Paragraph(hospital_info.get('name', 'HOSPITAL').upper(), title_style),
                Paragraph(
                    f'<b>Doc No:</b> {doc_number}' if doc_number else '',
                    ParagraphStyle('DocNum', parent=self.styles['Normal'],
                        fontSize=9, fontName='Helvetica-Bold', alignment=2, textColor=colors.black)
                ),
            ]]
            header_table = Table(header_rows, colWidths=[page_width * 0.7, page_width * 0.3])
            header_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
            elements.append(header_table)
            if hospital_info.get('hospital_subname'):
                elements.append(Paragraph(hospital_info['hospital_subname'], sub_style))
            if hospital_info.get('address'):
                elements.append(Paragraph(hospital_info['address'], sub_style))
            elements.append(Spacer(1, 6))
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        else:
            elements.append(Spacer(1, 90))
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
        mrn = consent_data.get('mrn') or consent_data.get('patient_id', '')
        meta_rows = [
            [Paragraph("Patient:", label_small), Paragraph(str(consent_data.get('patient_name', '')), body),
             Paragraph("MRN:", label_small), Paragraph(str(mrn), body)],
            [Paragraph("Admission #:", label_small), Paragraph(str(consent_data.get('admission_number', '')), body),
             Paragraph("Doctor:", label_small), Paragraph(str(consent_data.get('doctor_name', '')), body)],
            [Paragraph("Admitted on:", label_small), Paragraph(str(consent_data.get('admission_date', '')), body),
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
        meta_table = Table(meta_rows, colWidths=[page_width * 0.15, page_width * 0.35, page_width * 0.15, page_width * 0.35])
        meta_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
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
        doc.build(elements)
        buffer.seek(0)
        return buffer

    def generate_death_certificate_pdf(self, cert_data, hospital_info, include_header=True):
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
            elements.append(Spacer(1, 90))

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
            [Paragraph("Age / Gender:", label), Paragraph(f"{cert_data.get('age', '')} Years / {cert_data.get('gender', '')}" if cert_data.get('age') else cert_data.get('gender', ''), value)],
            [Paragraph("MRN:", label), Paragraph(str(cert_data.get('mrn') or cert_data.get('patient_id', '')), value)],
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
        doc.build(elements)
        buffer.seek(0)
        return buffer

    def generate_dama_pdf(self, dama_data, hospital_info, include_header=True):
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
            elements.append(Spacer(1, 90))

        elements.append(Spacer(1, 8))
        elements.append(Paragraph("DISCHARGE AGAINST MEDICAL ADVICE (DAMA)",
            ParagraphStyle('DA', parent=self.styles['Normal'],
                fontSize=14, alignment=1, fontName='Helvetica-Bold', textColor=colors.black, spaceAfter=6)))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.black))
        elements.append(Spacer(1, 10))

        meta_rows = [
            [Paragraph("Patient Name:", label), Paragraph(str(dama_data.get('patient_name', '')), value)],
            [Paragraph("MRN:", label), Paragraph(str(dama_data.get('mrn') or dama_data.get('patient_id', '')), value)],
            [Paragraph("Age / Gender:", label),
             Paragraph(f"{dama_data.get('age', '')} / {dama_data.get('gender', '')}", value)],
            [Paragraph("Admission No:", label), Paragraph(str(dama_data.get('admission_number', '')), value)],
            [Paragraph("Attending Doctor:", label), Paragraph(str(dama_data.get('doctor_name', '')), value)],
            [Paragraph("Admission Date:", label), Paragraph(str(dama_data.get('admission_date', '')), value)],
            [Paragraph("Discharge Date/Time:", label), Paragraph(str(dama_data.get('discharge_date', '')), value)],
            [Paragraph("Language Used:", label), Paragraph(str(dama_data.get('language_used', '')).title(), value)],
        ]
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
        doc.build(elements)
        buffer.seek(0)
        return buffer


    def generate_gate_pass_pdf(self, payload, hospital_info, include_header=True):
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
            elements.append(Spacer(1, 100))

        elements.append(Spacer(1, 6))
        elements.append(Paragraph("GATE PASS / DISCHARGE EXIT SLIP", receipt_title_style))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        elements.append(Spacer(1, 8))

        # Detail table
        rows = [
            [Paragraph("Pass Number", label), Paragraph(payload.get('pass_number', '-'), value),
             Paragraph("Issued at", label), Paragraph(payload.get('issued_at', '-'), value)],
            [Paragraph("Admission No", label), Paragraph(payload.get('admission_number', '-'), value),
             Paragraph("Patient ID", label), Paragraph(payload.get('patient_id', '-'), value)],
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

        doc.build(elements)
        buffer.seek(0)
        return buffer


    def generate_doctor_productivity_pdf(self, payload, hospital_info, include_header=True):
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
                      "Visit ₹", "OT Surgeon ₹", "OT Anaes ₹", "Total ₹"]
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
            "Total ₹ = Visit fees + OT surgeon fees (for OTs led) + OT anaesthetist fees. Outpatient consultation fees not included.",
            ParagraphStyle('NF', parent=self.styles['Normal'], fontSize=7, alignment=0,
                fontName='Helvetica-Oblique', textColor=colors.HexColor('#555555'))))
        elements.append(Paragraph(
            f"Generated on {datetime.now().strftime('%d/%m/%Y at %H:%M')}",
            ParagraphStyle('F', parent=self.styles['Normal'], fontSize=8, alignment=1)))
        doc.build(elements)
        buffer.seek(0)
        return buffer

    def generate_monthly_outcomes_pdf(self, payload, hospital_info, include_header=True):
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
        doc.build(elements)
        buffer.seek(0)
        return buffer

    def generate_handover_pdf(self, payload, hospital_info, include_header=True):
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
            [Paragraph("MRN:", label), Paragraph(str(payload.get('mrn') or payload.get('patient_id', '')), value)],
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
        doc.build(elements)
        buffer.seek(0)
        return buffer

    def generate_census_pdf(self, payload, hospital_info, include_header=True):
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
        try:
            as_of_h = datetime.fromisoformat(as_of.replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M")
        except Exception:
            as_of_h = as_of
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
        doc.build(elements)
        buffer.seek(0)
        return buffer

    def generate_mlc_register_pdf(self, mlc_data, hospital_info, include_header=True):
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
            elements.append(Spacer(1, 90))

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
        doc.build(elements)
        buffer.seek(0)
        return buffer


    def generate_body_release_pdf(self, rel, hospital_info, include_header=True):
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
            elements.append(Spacer(1, 90))

        elements.append(Spacer(1, 8))
        elements.append(Paragraph("BODY RELEASE / HANDOVER FORM",
            ParagraphStyle('R', parent=self.styles['Normal'],
                fontSize=14, alignment=1, fontName='Helvetica-Bold', spaceAfter=6)))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.black))
        elements.append(Spacer(1, 10))

        meta = [
            [Paragraph("Patient Name:", label), Paragraph(str(rel.get('patient_name', '')), value),
             Paragraph("MRN:", label), Paragraph(str(rel.get('mrn') or rel.get('patient_id', '')), value)],
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
        doc.build(elements)
        buffer.seek(0)
        return buffer


# Create global instance
pdf_service = PDFService()