from decimal import Decimal
from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APIClient
from rest_framework import status

from apps.products.models import Category, Product, ProductVariant
from apps.customers.models import CustomerProfile
from apps.inventory.models import StockItem, ProductionBatch
from apps.orders.models import Order, OrderItem, Payment, Invoice
from apps.orders.invoice_service import InvoiceService
from apps.analytics.services import AnalyticsService, parse_date_range
from apps.analytics.reports import ReportExportService
from apps.accounts.roles import (
    ensure_staff_roles,
    ROLE_SUPER_ADMIN,
    ROLE_ADMIN,
    ROLE_ORDER_MANAGER,
    ROLE_INVENTORY_MANAGER,
    ROLE_ACCOUNTANT,
)

User = get_user_model()


class Phase7AnalyticsAndAdminTests(TestCase):
    """
    Automated verification suite for Phase 7 Admin Dashboard, Analytics,
    Invoicing, Staff Roles, and Reporting.
    """

    def setUp(self):
        self.client = APIClient()
        ensure_staff_roles()

        # 1. Super Admin User
        self.superadmin = User.objects.create_superuser(
            username='admin@onfresh.in',
            email='admin@onfresh.in',
            password='AdminPassword123!',
            first_name='Manoj',
            last_name='Kumar'
        )

        # 2. Staff user with Order Manager role
        self.order_manager = User.objects.create_user(
            username='orders@onfresh.in',
            email='orders@onfresh.in',
            password='StaffPassword123!',
            first_name='Anand',
            last_name='R',
            is_staff=True
        )
        self.order_manager.groups.add(Group.objects.get(name=ROLE_ORDER_MANAGER))

        # 3. Retail Customer (B2C)
        self.retail_user = User.objects.create_user(
            username='retail@example.com',
            email='retail@example.com',
            password='CustomerPass123!',
            first_name='Sreejith',
            last_name='Nair'
        )
        self.retail_profile = CustomerProfile.objects.create(
            user=self.retail_user,
            customer_type='individual',
            phone_number='9876543210'
        )

        # 4. Wholesale Business Customer (B2B)
        self.wholesale_user = User.objects.create_user(
            username='wholesale@supermarket.com',
            email='wholesale@supermarket.com',
            password='CustomerPass123!',
            first_name='Thomas',
            last_name='Mathew'
        )
        self.wholesale_profile = CustomerProfile.objects.create(
            user=self.wholesale_user,
            customer_type='business',
            wholesale_status='approved',
            business_name='Highland Supermarket',
            business_type='supermarket',
            phone_number='9846012345',
            gstin='32AAACH1234A1Z5'
        )

        # 5. Catalogue & Inventory setup
        self.category = Category.objects.create(
            name='Kerala Banana Chips',
            slug='kerala-banana-chips',
            is_active=True
        )
        self.product = Product.objects.create(
            category=self.category,
            name='Crispy Hot Banana Chips',
            slug='crispy-hot-banana-chips',
            is_active=True
        )
        self.variant_retail = ProductVariant.objects.create(
            product=self.product,
            sku='ONF-BAN-250G',
            package_weight=Decimal('250.00'),
            package_unit='g',
            price=Decimal('100.00'),
            is_available=True
        )
        self.variant_wholesale = ProductVariant.objects.create(
            product=self.product,
            sku='ONF-BAN-1KG',
            package_weight=Decimal('1.00'),
            package_unit='kg',
            price=Decimal('350.00'),
            wholesale_price=Decimal('280.00'),
            minimum_order_quantity=10,
            is_available=True
        )

        # Create stock items
        self.stock_retail = StockItem.objects.create(
            variant=self.variant_retail,
            quantity_on_hand=200,
            reserved_quantity=0,
            low_stock_threshold=20
        )
        self.stock_wholesale = StockItem.objects.create(
            variant=self.variant_wholesale,
            quantity_on_hand=150,
            reserved_quantity=0,
            low_stock_threshold=15
        )

        # Create Production Batch
        self.batch = ProductionBatch.objects.create(
            product=self.product,
            variant=self.variant_retail,
            production_date=timezone.localdate(),
            expiry_date=timezone.localdate() + timedelta(days=60),
            status='in_production',
            manufactured_quantity=100,
            remaining_quantity=100,
            created_by=self.superadmin
        )

        # 6. Orders setup:
        # Order A: Retail Delivered & Paid
        self.order_retail = Order.objects.create(
            customer=self.retail_user,
            customer_profile=self.retail_profile,
            customer_type='individual',
            order_status='delivered',
            payment_status='paid',
            payment_method='online',
            subtotal=Decimal('500.00'),
            discount_amount=Decimal('0.00'),
            delivery_charge=Decimal('40.00'),
            tax_amount=Decimal('25.00'),
            total_amount=Decimal('565.00'),
            shipping_address_snapshot={
                'recipient_name': 'Sreejith Nair',
                'address_line_1': 'House 12',
                'city': 'Vandiperiyar',
                'district': 'Idukki',
                'state': 'Kerala',
                'pincode': '685533',
                'phone_number': '9876543210',
            }
        )
        OrderItem.objects.create(
            order=self.order_retail,
            variant=self.variant_retail,
            product_name='Crispy Hot Banana Chips',
            sku='ONF-BAN-250G',
            package_weight=Decimal('250.00'),
            package_unit='g',
            quantity=5,
            unit_price=Decimal('100.00'),
            retail_price=Decimal('100.00'),
            line_total=Decimal('500.00'),
        )
        Payment.objects.create(
            order=self.order_retail,
            transaction_id='TXN-ONF-001',
            payment_method='online',
            amount=Decimal('565.00'),
            status='successful',
        )

        # Order B: Wholesale Confirmed & Pending Payment
        self.order_wholesale = Order.objects.create(
            customer=self.wholesale_user,
            customer_profile=self.wholesale_profile,
            customer_type='business',
            order_status='confirmed',
            payment_status='pending',
            payment_method='bank_transfer',
            subtotal=Decimal('2800.00'),
            discount_amount=Decimal('100.00'),
            delivery_charge=Decimal('0.00'),
            tax_amount=Decimal('135.00'),
            total_amount=Decimal('2835.00'),
            shipping_address_snapshot={
                'recipient_name': 'Thomas Mathew',
                'address_line_1': 'Kottayam Road',
                'city': 'Vandiperiyar',
                'district': 'Idukki',
                'state': 'Kerala',
                'pincode': '685533',
                'phone_number': '9846012345',
            }
        )
        OrderItem.objects.create(
            order=self.order_wholesale,
            variant=self.variant_wholesale,
            product_name='Crispy Hot Banana Chips',
            sku='ONF-BAN-1KG',
            package_weight=Decimal('1.00'),
            package_unit='kg',
            quantity=10,
            unit_price=Decimal('280.00'),
            retail_price=Decimal('350.00'),
            line_total=Decimal('2800.00'),
            pricing_rule_applied='Wholesale Base'
        )

        # Order C: Cancelled Order (MUST be excluded from revenue)
        self.order_cancelled = Order.objects.create(
            customer=self.retail_user,
            customer_profile=self.retail_profile,
            customer_type='individual',
            order_status='cancelled',
            payment_status='refunded',
            subtotal=Decimal('300.00'),
            total_amount=Decimal('340.00'),
        )

    def test_dashboard_summary_metrics(self):
        """Dashboard summary must accurately compute revenue, excluding cancelled orders."""
        start_dt, end_dt = parse_date_range('this_month')
        summary = AnalyticsService.get_dashboard_summary(start_dt, end_dt)

        # Net sales = 565.00 (retail) + 2835.00 (wholesale) = 3400.00 (cancelled 340.00 excluded)
        self.assertEqual(summary['total_revenue'], 3400.00)
        self.assertEqual(summary['gross_order_value'], 3300.00)  # 500 + 2800
        self.assertEqual(summary['collected_payments'], 565.00)
        self.assertEqual(summary['outstanding_payments'], 2835.00)
        self.assertEqual(summary['cancelled_amount'], 340.00)
        self.assertEqual(summary['total_orders'], 3)
        self.assertEqual(summary['valid_orders_count'], 2)
        self.assertEqual(summary['delivered_orders'], 1)
        self.assertEqual(summary['confirmed_orders'], 1)
        self.assertEqual(summary['cancelled_orders'], 1)
        self.assertEqual(summary['total_individual_customers'], 1)
        self.assertEqual(summary['total_wholesale_customers'], 1)
        self.assertEqual(summary['active_production_batches'], 1)

    def test_sales_analytics_endpoint(self):
        """Sales time-series API returns structured data for charts."""
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.get('/api/analytics/sales/?period=30days&interval=daily')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('time_series', response.data['data'])
        self.assertIn('payment_breakdown', response.data['data'])

    def test_b2b_b2c_comparison_metrics(self):
        """Segment comparison must cleanly separate retail and wholesale performance."""
        start_dt, end_dt = parse_date_range('this_month')
        comparison = AnalyticsService.get_b2b_b2c_comparison(start_dt, end_dt)

        retail = comparison['retail']
        wholesale = comparison['wholesale']

        self.assertEqual(retail['total_revenue'], 565.00)
        self.assertEqual(retail['order_count'], 1)
        self.assertEqual(retail['aov'], 565.00)

        self.assertEqual(wholesale['total_revenue'], 2835.00)
        self.assertEqual(wholesale['order_count'], 1)
        self.assertEqual(wholesale['aov'], 2835.00)

        self.assertTrue(len(retail['top_products']) > 0)
        self.assertTrue(len(wholesale['top_products']) > 0)

    def test_product_analytics_metrics(self):
        """Product analytics correctly tracks best-sellers and category sales."""
        start_dt, end_dt = parse_date_range('this_month')
        data = AnalyticsService.get_product_analytics(start_dt, end_dt)

        best_selling = data['best_selling']
        self.assertTrue(len(best_selling) >= 1)
        # 1kg wholesale line was ₹2800 vs 250g retail ₹500
        self.assertEqual(best_selling[0]['sku'], 'ONF-BAN-1KG')
        self.assertEqual(best_selling[0]['total_revenue'], 2800.00)

    def test_invoice_generation_and_uniqueness(self):
        """Invoices must snapshot order data, generate unique numbers, and prevent duplicate rows."""
        inv1 = InvoiceService.get_or_create_invoice_for_order(self.order_retail)
        self.assertIsNotNone(inv1.invoice_number)
        self.assertTrue(inv1.invoice_number.startswith('INV-'))
        self.assertEqual(inv1.grand_total, Decimal('565.00'))
        self.assertEqual(inv1.customer_type, 'individual')
        self.assertEqual(inv1.status, 'paid')

        # Idempotency check: second retrieval returns existing invoice
        inv2 = InvoiceService.get_or_create_invoice_for_order(self.order_retail)
        self.assertEqual(inv1.id, inv2.id)
        self.assertEqual(inv1.invoice_number, inv2.invoice_number)

    def test_invoice_pdf_rendering(self):
        """ReportLab invoice PDF generator produces valid PDF bytes."""
        inv = InvoiceService.get_or_create_invoice_for_order(self.order_wholesale)
        pdf_bytes = InvoiceService.generate_pdf(inv)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))
        self.assertTrue(len(pdf_bytes) > 1000)

    def test_invoice_api_endpoints(self):
        """Invoice download and listing API tests."""
        self.client.force_authenticate(user=self.superadmin)
        inv = InvoiceService.get_or_create_invoice_for_order(self.order_retail)

        # Admin list
        res_list = self.client.get('/api/orders/admin/invoices/')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)

        # PDF download
        res_pdf = self.client.get(f'/api/orders/admin/invoices/{inv.invoice_number}/pdf/')
        self.assertEqual(res_pdf.status_code, status.HTTP_200_OK)
        self.assertEqual(res_pdf['Content-Type'], 'application/pdf')

    def test_customer_management_apis(self):
        """Admin can list customers, view details, and toggle customer active status."""
        self.client.force_authenticate(user=self.superadmin)

        # List
        res_list = self.client.get('/api/customers/admin/customers/?customer_type=business')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertTrue(len(res_list.data['results']) >= 1)

        # Detail
        res_detail = self.client.get(f'/api/customers/admin/customers/{self.wholesale_profile.id}/')
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(res_detail.data['customer']['business_name'], 'Highland Supermarket')

        # Status toggle
        res_toggle = self.client.post(f'/api/customers/admin/customers/{self.wholesale_profile.id}/status/', {'is_active': False}, format='json')
        self.assertEqual(res_toggle.status_code, status.HTTP_200_OK)
        self.wholesale_user.refresh_from_db()
        self.assertFalse(self.wholesale_user.is_active)

    def test_staff_role_permissions(self):
        """Non-admin users cannot access administrative endpoints."""
        self.client.force_authenticate(user=self.retail_user)

        # Retail customer trying to access dashboard
        res = self.client.get('/api/analytics/dashboard/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Retail customer trying to access admin customer list
        res_cust = self.client.get('/api/customers/admin/customers/')
        self.assertEqual(res_cust.status_code, status.HTTP_403_FORBIDDEN)

        # Retail customer trying to view another order's invoice
        res_inv = self.client.get(f'/api/orders/{self.order_wholesale.order_number}/invoice/')
        self.assertEqual(res_inv.status_code, status.HTTP_404_NOT_FOUND)

    def test_report_exports_csv_and_excel(self):
        """Admin can export reports in CSV and Excel formats."""
        self.client.force_authenticate(user=self.superadmin)

        # CSV export
        res_csv = self.client.get('/api/analytics/export/?type=sales&format=csv')
        self.assertEqual(res_csv.status_code, status.HTTP_200_OK)
        self.assertEqual(res_csv['Content-Type'], 'text/csv')
        self.assertIn(b'Order Number', res_csv.content)

        # Excel export
        res_xlsx = self.client.get('/api/analytics/export/?type=inventory&format=excel')
        self.assertEqual(res_xlsx.status_code, status.HTTP_200_OK)
        self.assertEqual(res_xlsx['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertTrue(len(res_xlsx.content) > 1000)
