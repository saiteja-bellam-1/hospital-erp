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
            uploads_base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
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
        age_sex = bill_data.get('patient_age', '')
        if bill_data.get('patient_gender'):
            gender = bill_data['patient_gender'].upper()
            if age_sex:
                age_sex = f"{age_sex} / {gender}"
            else:
                age_sex = gender

        phone = bill_data.get('patient_phone', '')
        patient_id = bill_data.get('patient_id', bill_data.get('reg_no', ''))
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
            [lv('Patient ID', patient_id), lv('Pay Mode', pay_category)],
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

        # Summary right-aligned under Rate column
        summary_label_w = page_width - code_w - rate_w
        cell_value_right = ParagraphStyle('CellValueRight', parent=cell_value_sm, alignment=2)

        payment_data = [
            [lv_sm('Paymode', pay_category), Paragraph('<b>Total Amt</b>', cell_value_sm), Paragraph(f"{total_amt:.2f}", cell_value_right)],
            [Paragraph('', cell_value_sm), Paragraph('<b>Discount</b>', cell_value_sm), Paragraph(f"{discount:.2f}", cell_value_right)],
            [Paragraph('', cell_value_sm), Paragraph('<b>Paid Amt</b>', cell_value_sm), Paragraph(f"{paid_amt:.2f}", cell_value_right)],
            [Paragraph('', cell_value_sm), Paragraph('<b>Balance</b>', cell_value_sm), Paragraph(f"{balance:.2f}", cell_value_right)],
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

        # Amount in words
        words_text = f"Rupees {amount_to_words(paid_amt)}"
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
            uploads_base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
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
        patient_id = prescription_data.get('patient_id_display', prescription_data.get('patient_id', ''))

        age_sex = ''
        if patient_age:
            try:
                age_sex = f"{int(patient_age)} Year"
            except ValueError:
                age_sex = str(patient_age)
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
            [Paragraph(f"<b>Patient ID</b> :  {patient_id}", cell_val), Paragraph(f"<b>Blood Group</b> :  {patient_blood_group or '—'}", cell_val)],
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
            uploads_base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")

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
        patient_age = report_data.get('patient_age', '')
        age_sex = f"{patient_age} Year" if patient_age else ''
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
            [lv('Patient ID', report_data.get('patient_uuid', '')), lv('Report ID', report_data.get('order_number', ''))],
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
        param_w = page_width * 0.30
        result_w = page_width * 0.15
        unit_w = page_width * 0.12
        ref_w = page_width * 0.28
        flag_w = page_width * 0.15

        # Section header style
        section_label_style = ParagraphStyle('LabSectionLabel', parent=self.styles['Normal'],
            fontSize=9, fontName='Helvetica-Bold', textColor=colors.Color(0.2, 0.2, 0.5))

        results_header = [
            Paragraph('<b>TEST DESCRIPTION</b>', cell_label),
            Paragraph('<b>RESULT ENTRY</b>', cell_label),
            Paragraph('<b>FLAG</b>', cell_label),
            Paragraph('<b>BIO. REF. RANGE</b>', cell_label),
            Paragraph('<b>UNIT</b>', cell_label),
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

            flag_text = ''
            if is_abnormal:
                flag_text = 'ABNORMAL'
            elif r.get('field_type') in ('numeric', 'less_than', 'greater_than') and (ref_min is not None or ref_max is not None):
                flag_text = 'Normal'
            elif r.get('field_type') in ('select', 'text') and normal_val and r.get('value'):
                flag_text = 'Normal' if not is_abnormal else ''

            flag_style = cell_abnormal if is_abnormal else cell_value

            param_text = r.get('parameter_name', '')
            remarks = r.get('remarks', '')
            if remarks:
                param_text = f"{param_text}<br/><i><font size='7' color='grey'>{remarks}</font></i>"

            results_data.append([
                Paragraph(param_text, cell_value),
                Paragraph(str(r.get('value', '')), value_style),
                Paragraph(flag_text, flag_style),
                Paragraph(ref_range, cell_value),
                Paragraph(r.get('unit', '') or '-', cell_value),
            ])

        results_table = Table(results_data, colWidths=[param_w, result_w, flag_w, ref_w, unit_w])

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
        uploads_base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
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
        patient_age = first_report.get('patient_age', '')
        age_sex = f"{patient_age} Year" if patient_age else ''
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
            [lv('Patient ID', first_report.get('patient_uuid', '')), Paragraph('', cell_value)],
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
        param_w = page_width * 0.30
        result_w = page_width * 0.15
        flag_w = page_width * 0.15
        ref_w = page_width * 0.28
        unit_w = page_width * 0.12

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
                Paragraph('<b>RESULT ENTRY</b>', cell_label),
                Paragraph('<b>FLAG</b>', cell_label),
                Paragraph('<b>BIO. REF. RANGE</b>', cell_label),
                Paragraph('<b>UNIT</b>', cell_label),
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

                flag_text = ''
                if is_abnormal:
                    flag_text = 'ABNORMAL'
                elif r.get('field_type') in ('numeric', 'less_than', 'greater_than') and (ref_min is not None or ref_max is not None):
                    flag_text = 'Normal'
                elif r.get('field_type') in ('select', 'text') and normal_val and r.get('value'):
                    flag_text = 'Normal' if not is_abnormal else ''

                flag_style = cell_abnormal if is_abnormal else cell_value

                param_text = r.get('parameter_name', '')
                remarks = r.get('remarks', '')
                if remarks:
                    param_text = f"{param_text}<br/><i><font size='7' color='grey'>{remarks}</font></i>"

                results_data.append([
                    Paragraph(param_text, cell_value),
                    Paragraph(str(r.get('value', '')), value_style),
                    Paragraph(flag_text, flag_style),
                    Paragraph(ref_range, cell_value),
                    Paragraph(r.get('unit', '') or '-', cell_value),
                ])

            results_table = Table(results_data, colWidths=[param_w, result_w, flag_w, ref_w, unit_w])

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

            # Interpretation (per test, if any)
            interpretation = report_data.get('interpretation')
            if interpretation:
                elements.append(Spacer(1, 4))
                elements.append(Paragraph(f"<b>Interpretation ({test_name}):</b>", cell_label))
                elements.append(Spacer(1, 2))
                elements.append(Paragraph(interpretation, normal_text))

        # ============================================================
        # SIGNATURES (once at the end)
        # ============================================================
        elements.append(Spacer(1, 30))
        uploads_base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")

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

# Create global instance
pdf_service = PDFService()