"""
OnFresh Invoice Generation & Tax Accounting Service.
Calculates accurate Indian GST, captures order snapshots, and renders printable PDFs via ReportLab.
"""

import io
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.conf import settings

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

from .models import Invoice, Order


class InvoiceService:
    """
    Handles business logic for invoice generation, tax computation, and PDF export.
    """

    @classmethod
    def get_or_create_invoice_for_order(cls, order: Order) -> Invoice:
        """
        Idempotently retrieves or creates the official tax invoice for an order.
        Calculates GST breakdown:
        - If shipping state is Kerala (or unspecified): CGST (2.5%) + SGST (2.5%) = 5.0%
        - If outside Kerala: IGST (5.0%)
        """
        if hasattr(order, 'invoice') and order.invoice:
            return order.invoice

        with transaction.atomic():
            # Double check inside transaction
            existing = Invoice.objects.filter(order=order).first()
            if existing:
                return existing

            shipping = order.shipping_address_snapshot or {}
            billing = order.billing_address_snapshot or shipping
            customer_profile = order.customer_profile

            recipient_name = shipping.get('recipient_name') or order.customer.get_full_name() or order.customer.username
            customer_phone = shipping.get('phone_number') or (customer_profile.phone_number if customer_profile else '')
            business_name = customer_profile.business_name if customer_profile else ''
            customer_gstin = customer_profile.gstin if customer_profile else ''

            state = str(shipping.get('state', 'Kerala')).strip().lower()
            is_intra_state = (state == 'kerala' or not state)

            tax_rate = Decimal('5.00')  # 5% standard GST on packaged snacks / bakery
            total_tax = order.tax_amount

            if is_intra_state:
                cgst = (total_tax / Decimal('2.0')).quantize(Decimal('0.01'))
                sgst = (total_tax - cgst).quantize(Decimal('0.01'))
                igst = Decimal('0.00')
            else:
                cgst = Decimal('0.00')
                sgst = Decimal('0.00')
                igst = total_tax.quantize(Decimal('0.01'))

            invoice_status = 'paid' if order.payment_status == 'paid' else 'issued'
            if order.order_status == 'cancelled':
                invoice_status = 'cancelled'

            # Find latest transaction ID if any
            latest_payment = order.payments.order_by('-created_at').first()
            payment_ref = latest_payment.transaction_id if latest_payment else ''

            invoice = Invoice.objects.create(
                order=order,
                status=invoice_status,
                customer_name=recipient_name,
                customer_email=order.customer.email,
                customer_phone=customer_phone,
                customer_type=order.customer_type,
                business_name=business_name,
                customer_gstin=customer_gstin,
                billing_address=billing,
                shipping_address=shipping,
                subtotal=order.subtotal,
                discount_amount=order.discount_amount,
                tax_rate_percent=tax_rate,
                cgst_amount=cgst,
                sgst_amount=sgst,
                igst_amount=igst,
                tax_amount=total_tax,
                delivery_charge=order.delivery_charge,
                grand_total=order.total_amount,
                payment_status=order.payment_status,
                payment_method=order.get_payment_method_display(),
                payment_reference=payment_ref,
            )

            return invoice

    @classmethod
    def generate_pdf(cls, invoice: Invoice) -> bytes:
        """
        Renders a high-resolution, professional tax invoice PDF using ReportLab.
        Styled with OnFresh branding: Deep Forest Green (#15803d) and warm neutral tones.
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=14 * mm,
            rightMargin=14 * mm,
            topMargin=14 * mm,
            bottomMargin=14 * mm,
        )

        styles = getSampleStyleSheet()
        
        # Custom typography styles
        primary_color = colors.HexColor('#15803d')
        dark_neutral = colors.HexColor('#1f2937')
        light_neutral = colors.HexColor('#f9fafb')
        border_color = colors.HexColor('#e5e7eb')

        title_style = ParagraphStyle(
            'InvoiceTitle',
            parent=styles['Heading1'],
            fontSize=18,
            leading=22,
            textColor=primary_color,
            fontName='Helvetica-Bold'
        )

        subtitle_style = ParagraphStyle(
            'CompanySub',
            parent=styles['Normal'],
            fontSize=8.5,
            leading=12,
            textColor=dark_neutral,
            fontName='Helvetica'
        )

        section_heading = ParagraphStyle(
            'SectionHead',
            parent=styles['Heading3'],
            fontSize=10,
            leading=13,
            textColor=primary_color,
            fontName='Helvetica-Bold'
        )

        cell_text = ParagraphStyle(
            'CellText',
            parent=styles['Normal'],
            fontSize=8,
            leading=10,
            textColor=dark_neutral,
            fontName='Helvetica'
        )

        cell_text_bold = ParagraphStyle(
            'CellTextBold',
            parent=styles['Normal'],
            fontSize=8,
            leading=10,
            textColor=dark_neutral,
            fontName='Helvetica-Bold'
        )

        elements = []

        # 1. Header Banner Table: Company Info (Left) vs Invoice Badge (Right)
        company_p = Paragraph(
            f"<b>{invoice.company_name}</b><br/>"
            f"{invoice.company_address}<br/>"
            f"<b>GSTIN:</b> {invoice.company_gstin} &nbsp;|&nbsp; <b>Phone:</b> {invoice.company_phone}<br/>"
            f"<b>Email:</b> {invoice.company_email} &nbsp;|&nbsp; <b>Website:</b> onfresh.in",
            subtitle_style
        )

        invoice_meta_p = Paragraph(
            f"<font color='{primary_color}'><b>TAX INVOICE</b></font><br/>"
            f"<b>Invoice No:</b> {invoice.invoice_number}<br/>"
            f"<b>Order No:</b> {invoice.order.order_number}<br/>"
            f"<b>Date:</b> {invoice.invoice_date.strftime('%d-%b-%Y')}<br/>"
            f"<b>Payment:</b> {invoice.get_payment_status_display().upper()} ({invoice.payment_method})",
            subtitle_style
        )

        header_table = Table([[company_p, invoice_meta_p]], colWidths=[110 * mm, 72 * mm])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LINEBELOW', (0, 0), (-1, -1), 1.5, primary_color),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(header_table)
        elements.append(Spacer(1, 4 * mm))

        # 2. Bill To & Ship To Details
        ship = invoice.shipping_address or {}
        bill = invoice.billing_address or ship

        bill_to_text = f"<b>{invoice.customer_name}</b>"
        if invoice.business_name:
            bill_to_text += f"<br/><b>Business:</b> {invoice.business_name}"
        if invoice.customer_gstin:
            bill_to_text += f"<br/><b>GSTIN:</b> {invoice.customer_gstin}"
        bill_to_text += f"<br/>{bill.get('address_line_1', '')}"
        if bill.get('address_line_2'):
            bill_to_text += f", {bill.get('address_line_2')}"
        bill_to_text += f"<br/>{bill.get('city', '')}, {bill.get('district', '')}, {bill.get('state', '')} - {bill.get('pincode', '')}"
        bill_to_text += f"<br/><b>Phone:</b> {invoice.customer_phone or ship.get('phone_number', '')}"
        bill_to_text += f"<br/><b>Email:</b> {invoice.customer_email}"

        ship_to_text = f"<b>{ship.get('recipient_name', invoice.customer_name)}</b>"
        ship_to_text += f"<br/>{ship.get('address_line_1', '')}"
        if ship.get('address_line_2'):
            ship_to_text += f", {ship.get('address_line_2')}"
        ship_to_text += f"<br/>{ship.get('city', '')}, {ship.get('district', '')}, {ship.get('state', '')} - {ship.get('pincode', '')}"
        ship_to_text += f"<br/><b>Phone:</b> {ship.get('phone_number', invoice.customer_phone)}"
        ship_to_text += f"<br/><b>Customer Segment:</b> {invoice.get_customer_type_display()}"

        bill_p = Paragraph(f"<b>BILL TO:</b><br/>{bill_to_text}", subtitle_style)
        ship_p = Paragraph(f"<b>SHIP TO:</b><br/>{ship_to_text}", subtitle_style)

        parties_table = Table([[bill_p, ship_p]], colWidths=[91 * mm, 91 * mm])
        parties_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), light_neutral),
            ('BOX', (0, 0), (-1, -1), 0.5, border_color),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, border_color),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(parties_table)
        elements.append(Spacer(1, 4 * mm))

        # 3. Itemized Product Table
        item_headers = ['#', 'Product & Packaging', 'SKU', 'Qty', 'Unit Price', 'Disc.', 'Total (₹)']
        table_data = [[
            Paragraph(f"<b>{h}</b>", cell_text_bold) for h in item_headers
        ]]

        items = list(invoice.order.items.all())
        for idx, item in enumerate(items, start=1):
            name_desc = f"{item.product_name} ({item.display_weight})"
            if item.pricing_rule_applied:
                name_desc += f"<br/><font color='#6b7280' size='7'>{item.pricing_rule_applied}</font>"
            table_data.append([
                Paragraph(str(idx), cell_text),
                Paragraph(name_desc, cell_text),
                Paragraph(item.sku, cell_text),
                Paragraph(str(item.quantity), cell_text),
                Paragraph(f"₹{item.unit_price:.2f}", cell_text),
                Paragraph(f"₹{item.discount_amount:.2f}", cell_text),
                Paragraph(f"₹{item.line_total:.2f}", cell_text_bold),
            ])

        items_table = Table(
            table_data,
            colWidths=[8 * mm, 68 * mm, 28 * mm, 14 * mm, 20 * mm, 18 * mm, 26 * mm]
        )
        items_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), primary_color),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOX', (0, 0), (-1, -1), 0.5, border_color),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, border_color),
        ]))
        elements.append(items_table)
        elements.append(Spacer(1, 3 * mm))

        # 4. Summary & Tax Table
        tax_rows = []
        if invoice.cgst_amount > 0 or invoice.sgst_amount > 0:
            tax_rows.append([
                Paragraph("CGST (2.5%):", cell_text),
                Paragraph(f"₹{invoice.cgst_amount:.2f}", cell_text)
            ])
            tax_rows.append([
                Paragraph("SGST (2.5%):", cell_text),
                Paragraph(f"₹{invoice.sgst_amount:.2f}", cell_text)
            ])
        elif invoice.igst_amount > 0:
            tax_rows.append([
                Paragraph("IGST (5.0%):", cell_text),
                Paragraph(f"₹{invoice.igst_amount:.2f}", cell_text)
            ])

        summary_data = [
            [Paragraph("Subtotal:", cell_text), Paragraph(f"₹{invoice.subtotal:.2f}", cell_text)],
            [Paragraph("Total Savings / Discount:", cell_text), Paragraph(f"- ₹{invoice.discount_amount:.2f}", cell_text)],
            *tax_rows,
            [Paragraph("Delivery / Shipping:", cell_text), Paragraph(f"₹{invoice.delivery_charge:.2f}", cell_text)],
            [Paragraph("<b>Grand Total:</b>", cell_text_bold), Paragraph(f"<b>₹{invoice.grand_total:.2f}</b>", cell_text_bold)],
        ]

        summary_table = Table(summary_data, colWidths=[40 * mm, 30 * mm])
        summary_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LINEABOVE', (0, -1), (-1, -1), 1, primary_color),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#dcfce7')),
        ]))

        # Place summary on right side
        notes_p = Paragraph(
            f"<b>Notes & Terms:</b><br/>"
            f"{invoice.notes}<br/>"
            f"1. Goods once sold are packed under strict FSSAI guidelines.<br/>"
            f"2. For wholesale order queries, contact <b>+91 94470 12345</b>.<br/>"
            f"3. Jurisdiction: High Court of Kerala / Idukki District Court.",
            subtitle_style
        )

        bottom_layout = Table([[notes_p, summary_table]], colWidths=[112 * mm, 70 * mm])
        bottom_layout.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(KeepTogether(bottom_layout))
        elements.append(Spacer(1, 6 * mm))

        # 5. Authorised Signatory Footer
        sig_p = Paragraph(
            "<b>For OnFresh Foods & Bakery</b><br/><br/><br/>"
            "___________________________<br/>"
            "Authorised Signatory<br/>"
            "Vandiperiyar, Idukki District",
            subtitle_style
        )
        sig_table = Table([[Paragraph("", subtitle_style), sig_p]], colWidths=[120 * mm, 62 * mm])
        sig_table.setStyle(TableStyle([
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ]))
        elements.append(KeepTogether(sig_table))

        # Build PDF
        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()

