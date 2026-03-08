from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from io import BytesIO
from datetime import datetime
import os

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

    def generate_bill_pdf(self, bill_data, hospital_info):
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
        elements.append(Paragraph(hospital_info.get('name', 'HOSPITAL').upper(), title_style))

        address = hospital_info.get('address', '')
        if address:
            elements.append(Paragraph(address, subtitle_style))

        contact_parts = []
        if hospital_info.get('email'):
            contact_parts.append(f"Email: {hospital_info['email']}")
        if hospital_info.get('phone'):
            contact_parts.append(f"Phone: {hospital_info['phone']}")
        if contact_parts:
            elements.append(Paragraph("  |  ".join(contact_parts), subtitle_style))

        elements.append(Spacer(1, 6))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        elements.append(Spacer(1, 4))
        elements.append(Paragraph("RECEIPT CUM REQUISITION", receipt_title_style))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        elements.append(Spacer(1, 6))

        # ============================================================
        # PATIENT INFO + BILL INFO (two-column layout in one table)
        # ============================================================
        patient_name = bill_data.get('patient_name', '')
        age_sex = bill_data.get('patient_age', '')
        if bill_data.get('patient_gender'):
            gender = bill_data['patient_gender'].upper()
            if age_sex:
                age_sex = f"{age_sex} / {gender}"
            else:
                age_sex = gender

        phone = bill_data.get('patient_phone', '')
        doctor = bill_data.get('doctor_name', '')
        pay_category = bill_data.get('payment_method', 'Cash')
        reg_no = bill_data.get('reg_no', '')
        bill_no = bill_data.get('bill_number', '')

        col_w = page_width / 2

        patient_info_data = [
            [lv('Name', patient_name), lv('Print date', print_date_str)],
            [lv('Age & Sex', age_sex), lv('Bill date', bill_date_str)],
            [lv('Mobile no', phone), lv('Reg no', reg_no)],
            [lv('Doctor Name', doctor), lv('Bill no', bill_no)],
            [lv('PayCategory', pay_category), Paragraph('', cell_value)],
        ]

        info_table = Table(patient_info_data, colWidths=[col_w, col_w])
        info_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
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
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            # Header row bold
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
        paid_amt = bill_data.get('amount_paid', 0)
        balance = bill_data.get('balance_due', 0)

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

        label_w = page_width * 0.25
        value_w = page_width * 0.25

        payment_data = [
            [lv_sm('Paymode', pay_category), lv_sm('Total Amt', f"{total_amt:.2f}")],
            [Paragraph('', cell_value_sm), lv_sm('Discount', f"{discount:.2f}")],
            [Paragraph('', cell_value_sm), lv_sm('Paid Amt', f"{paid_amt:.2f}")],
            [Paragraph('', cell_value_sm), lv_sm('Balance', f"{balance:.2f}")],
        ]

        payment_table = Table(payment_data, colWidths=[page_width / 2, page_width / 2])
        payment_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(payment_table)
        elements.append(Spacer(1, 4))

        # Amount in words
        words_text = f"Rupees {amount_to_words(paid_amt)}"
        words_data = [[lv('In words', words_text)]]
        words_table = Table(words_data, colWidths=[page_width])
        words_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(words_table)
        elements.append(Spacer(1, 8))

        # ============================================================
        # FOOTER: prepared by / printed by
        # ============================================================
        prepared_by = bill_data.get('prepared_by', '')
        footer_data = [
            [lv('Prepared by', prepared_by), lv('Printed by', prepared_by)],
        ]
        footer_table = Table(footer_data, colWidths=[page_width / 2, page_width / 2])
        footer_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
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
        """Generate PDF for prescription – clean tabular layout, no visible cell borders"""
        buffer = BytesIO()

        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            rightMargin=40, leftMargin=40, topMargin=30, bottomMargin=30
        )

        elements = []
        page_width = A4[0] - 80  # usable width

        # --- Styles ---
        title_style = ParagraphStyle('RxTitle', parent=self.styles['Title'],
            fontSize=16, alignment=1, fontName='Helvetica-Bold',
            textColor=colors.black, spaceAfter=2)

        subtitle_style = ParagraphStyle('RxSubtitle', parent=self.styles['Normal'],
            fontSize=9, alignment=1, fontName='Helvetica',
            textColor=colors.black, spaceAfter=2)

        section_title = ParagraphStyle('RxSection', parent=self.styles['Normal'],
            fontSize=10, fontName='Helvetica-Bold', textColor=colors.black,
            spaceBefore=8, spaceAfter=4)

        cell_lbl = ParagraphStyle('RxCellLbl', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica-Bold', textColor=colors.HexColor('#444444'))

        cell_val = ParagraphStyle('RxCellVal', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica', textColor=colors.black)

        cell_val_sm = ParagraphStyle('RxCellValSm', parent=self.styles['Normal'],
            fontSize=8, fontName='Helvetica', textColor=colors.black)

        footer_style = ParagraphStyle('RxFooter', parent=self.styles['Normal'],
            fontSize=7, alignment=1, fontName='Helvetica', textColor=colors.grey)

        # No-border table style helper
        def no_border_style(extra=None):
            cmds = [
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ]
            if extra:
                cmds.extend(extra)
            return TableStyle(cmds)

        def lbl(text):
            return Paragraph(f"<b>{text}</b>", cell_lbl)

        def val(text):
            return Paragraph(str(text) if text else '—', cell_val)

        # --- Parse dates ---
        try:
            rx_date = datetime.fromisoformat(prescription_data.get('prescription_date', '')).strftime('%d/%m/%Y')
        except Exception:
            rx_date = datetime.now().strftime('%d/%m/%Y')

        # ============================================================
        # HEADER
        # ============================================================
        if include_header:
            elements.append(Paragraph(hospital_info.get('name', 'HOSPITAL').upper(), title_style))
            address = hospital_info.get('address', '')
            if address:
                elements.append(Paragraph(address, subtitle_style))
            contact_parts = []
            if hospital_info.get('phone'):
                contact_parts.append(f"Phone: {hospital_info['phone']}")
            if hospital_info.get('email'):
                contact_parts.append(f"Email: {hospital_info['email']}")
            if contact_parts:
                elements.append(Paragraph("  |  ".join(contact_parts), subtitle_style))
            elements.append(Spacer(1, 6))
            elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
            elements.append(Spacer(1, 4))

        elements.append(Paragraph("PRESCRIPTION", ParagraphStyle('RxMainTitle',
            parent=self.styles['Normal'], fontSize=12, alignment=1,
            fontName='Helvetica-Bold', textColor=colors.black, spaceAfter=4)))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
        elements.append(Spacer(1, 6))

        # ============================================================
        # PATIENT & DOCTOR INFO (2-column, no borders)
        # ============================================================
        patient_name = prescription_data.get('patient_name', '')
        patient_age = prescription_data.get('patient_age', '')
        patient_gender = prescription_data.get('patient_gender', '')
        age_sex = f"{patient_age} yrs / {patient_gender}" if patient_age else patient_gender
        doctor_name = prescription_data.get('doctor_name', '')
        doctor_spec = prescription_data.get('doctor_specialization', '')
        rx_no = prescription_data.get('prescription_number', '')

        col_w = page_width / 2
        info_rows = [
            [lbl('Patient'), val(patient_name), lbl('Rx No'), val(rx_no)],
            [lbl('Age / Gender'), val(age_sex), lbl('Date'), val(rx_date)],
            [lbl('Doctor'), val(f"{doctor_name}" + (f" ({doctor_spec})" if doctor_spec else '')), lbl('Phone'), val(prescription_data.get('patient_phone', ''))],
        ]
        info_table = Table(info_rows, colWidths=[page_width * 0.15, page_width * 0.35, page_width * 0.12, page_width * 0.38])
        info_table.setStyle(no_border_style())
        elements.append(info_table)
        elements.append(Spacer(1, 4))

        # ============================================================
        # VITALS (if available)
        # ============================================================
        vitals = prescription_data.get('vitals')
        if vitals and vitals.get('vital_signs'):
            elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
            elements.append(Spacer(1, 4))
            elements.append(Paragraph("VITALS", section_title))
            vs = vitals['vital_signs']
            vitals_items = []
            if vs.get('blood_pressure'):
                vitals_items.append([lbl('BP'), val(f"{vs['blood_pressure']} mmHg")])
            if vs.get('heart_rate'):
                vitals_items.append([lbl('Heart Rate'), val(f"{vs['heart_rate']} bpm")])
            if vs.get('temperature'):
                vitals_items.append([lbl('Temp'), val(f"{vs['temperature']}°F")])
            if vs.get('spo2'):
                vitals_items.append([lbl('SpO2'), val(f"{vs['spo2']}%")])
            if vs.get('respiratory_rate'):
                vitals_items.append([lbl('Resp Rate'), val(f"{vs['respiratory_rate']} /min")])
            if vs.get('weight'):
                vitals_items.append([lbl('Weight'), val(f"{vs['weight']} kg")])
            if vs.get('height'):
                vitals_items.append([lbl('Height'), val(f"{vs['height']} cm")])
            if vs.get('bmi'):
                vitals_items.append([lbl('BMI'), val(vs['bmi'])])

            # Arrange vitals in rows of 4 (label+value pairs → 2 pairs per row)
            vitals_rows = []
            for i in range(0, len(vitals_items), 2):
                row = vitals_items[i]
                if i + 1 < len(vitals_items):
                    row = row + vitals_items[i + 1]
                else:
                    row = row + [Paragraph('', cell_val), Paragraph('', cell_val)]
                vitals_rows.append(row)

            if vitals_rows:
                vt = Table(vitals_rows, colWidths=[page_width * 0.15, page_width * 0.35, page_width * 0.15, page_width * 0.35])
                vt.setStyle(no_border_style())
                elements.append(vt)

        # Add separator before next section (after vitals or after patient info)
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))

        # ============================================================
        # CONSULTATION FINDINGS
        # ============================================================
        consultation = prescription_data.get('consultation')
        if consultation:
            has_findings = consultation.get('chief_complaint') or consultation.get('present_history') or consultation.get('examination_findings')
            if has_findings:
                elements.append(Spacer(1, 4))
                elements.append(Paragraph("FINDINGS", section_title))
                findings_rows = []
                if consultation.get('chief_complaint'):
                    findings_rows.append([lbl('Chief Complaint'), Paragraph(consultation['chief_complaint'], cell_val)])
                if consultation.get('present_history'):
                    findings_rows.append([lbl('History'), Paragraph(consultation['present_history'], cell_val)])
                if consultation.get('examination_findings'):
                    findings_rows.append([lbl('Examination'), Paragraph(consultation['examination_findings'], cell_val)])
                ft = Table(findings_rows, colWidths=[page_width * 0.22, page_width * 0.78])
                ft.setStyle(no_border_style())
                elements.append(ft)
                elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))

        # ============================================================
        # DIAGNOSIS
        # ============================================================
        if prescription_data.get('diagnosis'):
            elements.append(Spacer(1, 4))
            elements.append(Paragraph("DIAGNOSIS", section_title))
            elements.append(Paragraph(prescription_data['diagnosis'], cell_val))
            elements.append(Spacer(1, 4))
            elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))

        # ============================================================
        # MEDICINES TABLE (with subtle header underline only)
        # ============================================================
        elements.append(Spacer(1, 4))
        elements.append(Paragraph("Rx  MEDICINES", section_title))

        med_header = [
            Paragraph('<b>#</b>', cell_lbl),
            Paragraph('<b>Medicine</b>', cell_lbl),
            Paragraph('<b>Dosage</b>', cell_lbl),
            Paragraph('<b>Duration</b>', cell_lbl),
            Paragraph('<b>Instructions</b>', cell_lbl),
        ]

        med_data = [med_header]
        food_timing_map = {
            'before_food': 'Before food', 'after_food': 'After food',
            'with_food': 'With food', 'on_empty_stomach': 'Empty stomach', 'anytime': 'Anytime'
        }

        for idx, item in enumerate(prescription_data.get('items', []), 1):
            dosage_val = item.get('dosage', 'As directed')
            freq = item.get('frequency_schedule', '1-0-0')
            food = food_timing_map.get(item.get('food_timing', 'after_food'), 'After food')
            dosage_text = f"{dosage_val}<br/><i>{freq} | {food}</i>"

            med_data.append([
                Paragraph(str(idx), cell_val),
                Paragraph(f"<b>{item.get('medicine_name', '')}</b>", cell_val),
                Paragraph(dosage_text, cell_val_sm),
                Paragraph(item.get('duration', '—'), cell_val),
                Paragraph(item.get('instructions', 'As directed'), cell_val_sm),
            ])

        sno_w = page_width * 0.05
        name_w = page_width * 0.25
        dosage_w = page_width * 0.28
        dur_w = page_width * 0.14
        instr_w = page_width * 0.28

        med_table = Table(med_data, colWidths=[sno_w, name_w, dosage_w, dur_w, instr_w])
        med_table.setStyle(no_border_style([
            ('LINEBELOW', (0, 0), (-1, 0), 0.8, colors.black),  # header underline
            ('LINEBELOW', (0, -1), (-1, -1), 0.5, colors.grey),  # bottom line
        ]))
        elements.append(med_table)

        # ============================================================
        # LAB TESTS (if any)
        # ============================================================
        lab_tests = prescription_data.get('lab_tests', [])
        if lab_tests:
            elements.append(Spacer(1, 4))
            elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
            elements.append(Spacer(1, 4))
            elements.append(Paragraph("INVESTIGATIONS", section_title))

            lab_header = [
                Paragraph('<b>#</b>', cell_lbl),
                Paragraph('<b>Test</b>', cell_lbl),
                Paragraph('<b>Code</b>', cell_lbl),
                Paragraph('<b>Status</b>', cell_lbl),
                Paragraph('<b>Date</b>', cell_lbl),
            ]
            lab_data = [lab_header]
            for idx, t in enumerate(lab_tests, 1):
                lab_data.append([
                    Paragraph(str(idx), cell_val),
                    Paragraph(t.get('test_name', ''), cell_val),
                    Paragraph(t.get('test_code', '') or '—', cell_val),
                    Paragraph((t.get('status', '') or '').capitalize(), cell_val),
                    Paragraph(t.get('order_date', ''), cell_val),
                ])

            lab_table = Table(lab_data, colWidths=[
                page_width * 0.05, page_width * 0.35, page_width * 0.18,
                page_width * 0.20, page_width * 0.22
            ])
            lab_table.setStyle(no_border_style([
                ('LINEBELOW', (0, 0), (-1, 0), 0.8, colors.black),
                ('LINEBELOW', (0, -1), (-1, -1), 0.5, colors.grey),
            ]))
            elements.append(lab_table)

        # ============================================================
        # FOLLOW-UP & NOTES
        # ============================================================
        follow_up = None
        if consultation and consultation.get('follow_up_date'):
            follow_up = consultation['follow_up_date']

        if follow_up or prescription_data.get('notes'):
            elements.append(Spacer(1, 4))
            elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
            elements.append(Spacer(1, 4))
            extra_rows = []
            if follow_up:
                extra_rows.append([lbl('Follow-up Date'), val(follow_up)])
            if prescription_data.get('notes'):
                extra_rows.append([lbl('Notes'), Paragraph(prescription_data['notes'], cell_val)])
            et = Table(extra_rows, colWidths=[page_width * 0.20, page_width * 0.80])
            et.setStyle(no_border_style())
            elements.append(et)

        # ============================================================
        # SIGNATURE
        # ============================================================
        elements.append(Spacer(1, 30))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
        elements.append(Spacer(1, 8))
        sig_rows = [[
            Paragraph('', cell_val),
            Paragraph(f"<b>{prescription_data.get('doctor_name', '')}</b><br/>"
                      f"{prescription_data.get('doctor_specialization', '')}<br/>"
                      "Signature", cell_val_sm)
        ]]
        sig_table = Table(sig_rows, colWidths=[page_width * 0.60, page_width * 0.40])
        sig_table.setStyle(no_border_style())
        elements.append(sig_table)

        # Footer
        elements.append(Spacer(1, 15))
        elements.append(Paragraph(f"Generated on {datetime.now().strftime('%d/%m/%Y at %H:%M:%S')}", footer_style))

        doc.build(elements)
        buffer.seek(0)
        return buffer

    def generate_lab_report_pdf(self, report_data, hospital_info):
        """Generate PDF for lab report"""
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

        # ============================================================
        # HEADER
        # ============================================================
        elements.append(Paragraph(hospital_info.get('name', 'HOSPITAL').upper(), title_style))
        address = hospital_info.get('address', '')
        if address:
            elements.append(Paragraph(address, subtitle_style))
        contact_parts = []
        if hospital_info.get('email'):
            contact_parts.append(f"Email: {hospital_info['email']}")
        if hospital_info.get('phone'):
            contact_parts.append(f"Phone: {hospital_info['phone']}")
        if contact_parts:
            elements.append(Paragraph("  |  ".join(contact_parts), subtitle_style))

        elements.append(Spacer(1, 6))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        elements.append(Spacer(1, 4))
        elements.append(Paragraph("LABORATORY REPORT", report_title_style))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        elements.append(Spacer(1, 6))

        # ============================================================
        # PATIENT + TEST INFO
        # ============================================================
        report_date_str = ""
        try:
            rd = datetime.fromisoformat(str(report_data.get('report_date', '')).replace('Z', '+00:00'))
            report_date_str = rd.strftime('%d/%m/%Y %I:%M %p')
        except Exception:
            report_date_str = datetime.now().strftime('%d/%m/%Y')

        patient_name = report_data.get('patient_name', '')
        patient_gender = report_data.get('patient_gender', '')
        patient_age = report_data.get('patient_age', '')
        age_sex = f"{patient_age} yrs" if patient_age else ''
        if patient_gender:
            age_sex = f"{age_sex} / {patient_gender}" if age_sex else patient_gender

        col_w = page_width / 2
        info_data = [
            [lv('Patient Name', patient_name), lv('Report Date', report_date_str)],
            [lv('Age / Gender', age_sex), lv('Order No', report_data.get('order_number', ''))],
            [lv('Referred By', report_data.get('doctor_name', 'N/A')), lv('Test', f"{report_data.get('test_name', '')} ({report_data.get('test_code', '')})")],
            *([[ lv('Method', report_data.get('method', '')), Paragraph('', cell_value) ]] if report_data.get('method') else []),
        ]

        info_table = Table(info_data, colWidths=[col_w, col_w])
        info_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 10))

        # ============================================================
        # RESULTS TABLE
        # ============================================================
        param_w = page_width * 0.30
        result_w = page_width * 0.15
        unit_w = page_width * 0.12
        ref_w = page_width * 0.28
        flag_w = page_width * 0.15

        results_header = [
            Paragraph('<b>Parameter</b>', cell_label),
            Paragraph('<b>Result</b>', cell_label),
            Paragraph('<b>Unit</b>', cell_label),
            Paragraph('<b>Reference Range</b>', cell_label),
            Paragraph('<b>Status</b>', cell_label),
        ]

        results_data = [results_header]
        results_list = report_data.get('results', [])

        for r in results_list:
            is_abnormal = r.get('is_abnormal', False)
            value_style = cell_abnormal if is_abnormal else cell_value

            ref_range = '-'
            ref_min = r.get('reference_min')
            ref_max = r.get('reference_max')
            if ref_min is not None or ref_max is not None:
                ref_range = f"{ref_min if ref_min is not None else '–'} - {ref_max if ref_max is not None else '–'}"

            flag_text = ''
            if is_abnormal:
                flag_text = 'ABNORMAL'
            elif r.get('field_type') == 'numeric' and (ref_min is not None or ref_max is not None):
                flag_text = 'Normal'

            flag_style = cell_abnormal if is_abnormal else cell_value

            results_data.append([
                Paragraph(r.get('parameter_name', ''), cell_value),
                Paragraph(str(r.get('value', '')), value_style),
                Paragraph(r.get('unit', '') or '-', cell_value),
                Paragraph(ref_range, cell_value),
                Paragraph(flag_text, flag_style),
            ])

        results_table = Table(results_data, colWidths=[param_w, result_w, unit_w, ref_w, flag_w])

        table_style_cmds = [
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
        ]

        # Highlight abnormal rows
        for idx, r in enumerate(results_list):
            if r.get('is_abnormal', False):
                row = idx + 1  # +1 for header
                table_style_cmds.append(('BACKGROUND', (0, row), (-1, row), colors.Color(1, 0.95, 0.95)))

        results_table.setStyle(TableStyle(table_style_cmds))
        elements.append(results_table)
        elements.append(Spacer(1, 10))

        # ============================================================
        # INTERPRETATION
        # ============================================================
        interpretation = report_data.get('interpretation')
        if interpretation:
            elements.append(Paragraph("<b>Interpretation:</b>", cell_label))
            elements.append(Spacer(1, 4))
            elements.append(Paragraph(interpretation, normal_text))
            elements.append(Spacer(1, 10))

        # ============================================================
        # SIGNATURES
        # ============================================================
        elements.append(Spacer(1, 30))
        tech_name = report_data.get('technician_name', '')
        sig_data = [
            [Paragraph(f"<b>Lab Technician:</b> {tech_name}", cell_value),
             Paragraph("<b>Authorized Signatory</b>", cell_value)],
        ]
        sig_table = Table(sig_data, colWidths=[page_width / 2, page_width / 2])
        sig_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(sig_table)

        # Footer
        elements.append(Spacer(1, 20))
        elements.append(Paragraph(f"Generated on {datetime.now().strftime('%d/%m/%Y at %H:%M:%S')}", footer_style))

        doc.build(elements)
        buffer.seek(0)
        return buffer

# Create global instance
pdf_service = PDFService()