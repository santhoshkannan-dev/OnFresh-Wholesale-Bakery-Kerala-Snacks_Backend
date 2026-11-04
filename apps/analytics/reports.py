"""
OnFresh Multi-Format Report Export Engine.
Generates comprehensive CSV and Excel (.xlsx) reports for:
- Sales
- Orders
- Customers
- Inventory
- Product Performance
"""

import io
import csv
from datetime import datetime
from decimal import Decimal
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from ..orders.models import Order, OrderItem, Payment
from ..customers.models import CustomerProfile
from ..products.models import ProductVariant
from ..inventory.models import StockItem


class ReportExportService:
    """
    Renders structured tabular data to CSV or Excel with header styling and number formatting.
    """

    @classmethod
    def export(cls, report_type: str, export_format: str, start_dt, end_dt) -> tuple[bytes, str, str]:
        """
        Returns (content_bytes, mime_type, filename).
        """
        headers, rows = cls._get_data(report_type, start_dt, end_dt)
        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        base_name = f"OnFresh_{report_type.capitalize()}_{timestamp_str}"

        if export_format == 'excel':
            content = cls._generate_excel(report_type.capitalize(), headers, rows)
            mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            filename = f"{base_name}.xlsx"
        else:
            content = cls._generate_csv(headers, rows)
            mime_type = 'text/csv'
            filename = f"{base_name}.csv"

        return content, mime_type, filename

    @classmethod
    def _get_data(cls, report_type: str, start_dt, end_dt):
        if report_type == 'sales':
            headers = [
                'Order Number', 'Date', 'Customer Email', 'Customer Type',
                'Status', 'Payment Status', 'Payment Method', 'Subtotal (INR)',
                'Discount (INR)', 'Delivery (INR)', 'Tax (INR)', 'Grand Total (INR)'
            ]
            orders = Order.objects.filter(
                created_at__range=(start_dt, end_dt)
            ).exclude(order_status='cancelled').select_related('customer').order_by('-created_at')

            rows = [
                [
                    o.order_number,
                    o.created_at.strftime('%Y-%m-%d %H:%M'),
                    o.customer.email,
                    o.get_customer_type_display(),
                    o.get_order_status_display(),
                    o.get_payment_status_display(),
                    o.get_payment_method_display(),
                    float(o.subtotal),
                    float(o.discount_amount),
                    float(o.delivery_charge),
                    float(o.tax_amount),
                    float(o.total_amount),
                ]
                for o in orders
            ]
            return headers, rows

        elif report_type == 'orders':
            headers = [
                'Order Number', 'Date', 'Customer Email', 'Recipient Name',
                'Phone', 'City', 'District', 'State', 'Pincode',
                'Items Count', 'Status', 'Payment Status', 'Total (INR)'
            ]
            orders = Order.objects.filter(
                created_at__range=(start_dt, end_dt)
            ).select_related('customer').prefetch_related('items').order_by('-created_at')

            rows = []
            for o in orders:
                ship = o.shipping_address_snapshot or {}
                rows.append([
                    o.order_number,
                    o.created_at.strftime('%Y-%m-%d %H:%M'),
                    o.customer.email,
                    ship.get('recipient_name', ''),
                    ship.get('phone_number', ''),
                    ship.get('city', ''),
                    ship.get('district', ''),
                    ship.get('state', ''),
                    ship.get('pincode', ''),
                    o.items.count(),
                    o.get_order_status_display(),
                    o.get_payment_status_display(),
                    float(o.total_amount),
                ])
            return headers, rows

        elif report_type == 'customers':
            headers = [
                'Customer ID', 'Full Name', 'Email', 'Phone', 'Customer Type',
                'Wholesale Status', 'Business Name', 'Business Type', 'GSTIN',
                'Active', 'Date Joined'
            ]
            profiles = CustomerProfile.objects.select_related('user').order_by('-created_at')
            rows = [
                [
                    p.user_id,
                    p.user.get_full_name() or p.user.username,
                    p.user.email,
                    p.phone_number,
                    p.get_customer_type_display(),
                    p.get_wholesale_status_display(),
                    p.business_name,
                    p.get_business_type_display() if p.business_name else '',
                    p.gstin,
                    'Yes' if p.user.is_active else 'No',
                    p.created_at.strftime('%Y-%m-%d'),
                ]
                for p in profiles
            ]
            return headers, rows

        elif report_type == 'inventory':
            headers = [
                'Product', 'Variant SKU', 'Package Size', 'Quantity on Hand',
                'Reserved', 'Available to Sell', 'Low Stock Threshold',
                'Stock Status'
            ]
            stock_items = StockItem.objects.select_related('variant__product').order_by('variant__product__name')
            rows = []
            for item in stock_items:
                status_text = 'Out of Stock' if item.is_out_of_stock else ('Low Stock' if item.is_low_stock else 'In Stock')
                rows.append([
                    item.variant.product.name,
                    item.variant.sku,
                    item.variant.display_weight,
                    item.quantity_on_hand,
                    item.reserved_quantity,
                    item.available_to_sell,
                    item.low_stock_threshold,
                    status_text,
                ])
            return headers, rows

        elif report_type == 'products':
            headers = [
                'Product Name', 'SKU', 'Package Size', 'Units Sold',
                'Total Revenue (INR)', 'Stock on Hand', 'Available to Sell'
            ]
            items = OrderItem.objects.filter(
                order__created_at__range=(start_dt, end_dt)
            ).exclude(order__order_status='cancelled').select_related('variant__stock_item')

            # Aggregate in python
            summary = {}
            for line in items:
                sku = line.sku
                if sku not in summary:
                    stock_item = getattr(line.variant, 'stock_item', None) if line.variant else None
                    on_hand = stock_item.quantity_on_hand if stock_item else 0
                    ats = stock_item.available_to_sell if stock_item else 0
                    summary[sku] = {
                        'name': line.product_name,
                        'sku': sku,
                        'size': line.display_weight,
                        'units': 0,
                        'revenue': Decimal('0.00'),
                        'on_hand': on_hand,
                        'ats': ats,
                    }
                summary[sku]['units'] += line.quantity
                summary[sku]['revenue'] += line.line_total

            sorted_items = sorted(summary.values(), key=lambda x: x['revenue'], reverse=True)
            rows = [
                [
                    item['name'],
                    item['sku'],
                    item['size'],
                    item['units'],
                    float(item['revenue']),
                    item['on_hand'],
                    item['ats'],
                ]
                for item in sorted_items
            ]
            return headers, rows

        return ['No Data'], []

    @classmethod
    def _generate_csv(cls, headers, rows) -> bytes:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(row)
        return output.getvalue().encode('utf-8')

    @classmethod
    def _generate_excel(cls, title: str, headers, rows) -> bytes:
        wb = Workbook()
        ws = wb.active
        ws.title = title[:30]

        # Brand header styling
        header_fill = PatternFill(start_color='15803D', end_color='15803D', fill_type='solid')
        header_font = Font(name='Calibri', size=11, bold=True, color='FFFFFF')
        thin_border = Border(
            left=Side(style='thin', color='E5E7EB'),
            right=Side(style='thin', color='E5E7EB'),
            top=Side(style='thin', color='E5E7EB'),
            bottom=Side(style='thin', color='E5E7EB'),
        )

        # Write headers
        ws.append(headers)
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')

        # Write data rows
        for row_data in rows:
            ws.append(row_data)

        # Auto-adjust column widths
        for col in ws.columns:
            max_len = 0
            col_letter = col[0].column_letter
            for cell in col:
                cell.border = thin_border
                val_str = str(cell.value or '')
                if len(val_str) > max_len:
                    max_len = len(val_str)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output.getvalue()

