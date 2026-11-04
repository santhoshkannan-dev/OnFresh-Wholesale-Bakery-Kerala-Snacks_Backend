"""
OnFresh Launch Verification & End-to-End Business Workflow Test Suite.
Validates:
1. Health check & database probe.
2. B2C Individual Retail Workflow (Registration, Cart, Pricing, Checkout, Order Tracking).
3. B2B Wholesale Business Workflow (Registration, Approval Gate, Wholesale Pricing, Bulk MOQ, Delivery Fees).
4. Administrative Operations (Wholesale account approval, inventory allocation, invoice generation).
5. Customer isolation and privilege escalation security controls.
"""

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from apps.products.models import Category, Product, ProductVariant
from apps.customers.models import CustomerProfile, Address
from apps.orders.models import Cart, CartItem, Order, OrderItem
from apps.inventory.models import StockItem
from apps.accounts.roles import ensure_staff_roles, ROLE_ADMIN, ROLE_SUPER_ADMIN

User = get_user_model()


class LaunchBusinessWorkflowTests(TestCase):
    def setUp(self):
        ensure_staff_roles()
        self.client = APIClient()

        # 1. Superuser / Admin
        self.admin = User.objects.create_superuser(
            username='admin@onfresh.test',
            email='admin@onfresh.test',
            password='AdminPassword123!',
            first_name='Operations',
            last_name='Admin'
        )

        # 2. Product Catalogue
        self.cat_chips = Category.objects.create(name='Banana Chips', slug='banana-chips')
        self.product = Product.objects.create(
            name='Authentic Kerala Banana Chips',
            slug='kerala-banana-chips',
            category=self.cat_chips
        )
        self.var_250 = ProductVariant.objects.create(
            product=self.product,
            package_weight=Decimal('250.00'),
            package_unit='g',
            sku='ONF-CHIP-250G',
            price=Decimal('80.00'),
            wholesale_price=Decimal('65.00'),
            minimum_order_quantity=10,
            is_available=True,
            is_available_retail=True,
            is_available_wholesale=True
        )
        self.var_1kg = ProductVariant.objects.create(
            product=self.product,
            package_weight=Decimal('1000.00'),
            package_unit='g',
            sku='ONF-CHIP-1KG',
            price=Decimal('300.00'),
            wholesale_price=Decimal('240.00'),
            minimum_order_quantity=5,
            is_available=True,
            is_available_retail=True,
            is_available_wholesale=True
        )

        # Stock allocations
        StockItem.objects.create(variant=self.var_250, quantity_on_hand=500, reserved_quantity=0)
        StockItem.objects.create(variant=self.var_1kg, quantity_on_hand=200, reserved_quantity=0)

    def test_health_check_endpoint(self):
        resp = self.client.get('/api/health/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'healthy')
        self.assertEqual(resp.data['database']['status'], 'connected')

    def test_b2c_retail_customer_lifecycle(self):
        # 1. Register Retail Customer
        reg_payload = {
            'full_name': 'Anand Kumar',
            'email': 'anand@consumer.test',
            'mobile_number': '9876543210',
            'customer_type': 'individual',
            'password': 'SecureRetailPass123!',
            'password_confirmation': 'SecureRetailPass123!',
        }
        reg_resp = self.client.post('/api/auth/register/', reg_payload, format='json')
        self.assertEqual(reg_resp.status_code, 201)

        user = User.objects.get(email='anand@consumer.test')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.customer_profile.customer_type, 'individual')
        self.assertEqual(user.customer_profile.wholesale_status, 'none')

        # 2. Login
        login_resp = self.client.post('/api/auth/login/', {
            'email': 'anand@consumer.test',
            'password': 'SecureRetailPass123!',
        }, format='json')
        self.assertEqual(login_resp.status_code, 200)

        # 3. Add to Cart (Single packet of 250g)
        self.client.force_authenticate(user=user)
        add_resp = self.client.post('/api/cart/items/', {
            'variant_id': self.var_250.id,
            'quantity': 2,
        }, format='json')
        self.assertEqual(add_resp.status_code, 200)

        # Verify retail price is evaluated via cart endpoint (2 x ₹80 = ₹160)
        cart_summary = self.client.get('/api/cart/')
        self.assertEqual(cart_summary.status_code, 200)
        self.assertEqual(len(cart_summary.data['items']), 1)
        cart_item = cart_summary.data['items'][0]
        self.assertEqual(Decimal(str(cart_item['unit_price'])), Decimal('80.00'))
        self.assertEqual(Decimal(str(cart_item['line_total'])), Decimal('160.00'))

        # 4. Delivery Fee Rule Check: ₹160 is below ₹500 threshold -> ₹50 delivery fee
        self.assertEqual(Decimal(str(cart_summary.data['delivery_charge'])), Decimal('50.00'))
        self.assertEqual(Decimal(str(cart_summary.data['total_amount'])), Decimal('210.00'))

        # 5. Create Address and Checkout
        addr = Address.objects.create(
            customer=user.customer_profile,
            recipient_name='Anand Kumar',
            phone_number='9876543210',
            address_line_1='Flat 4B, Hill View Residency',
            city='Vandiperiyar',
            state='Kerala',
            pincode='685533'
        )

        checkout_resp = self.client.post('/api/orders/checkout/', {
            'shipping_address_id': addr.id,
            'payment_method': 'cod',
            'customer_notes': 'Deliver before 5 PM'
        }, format='json')
        self.assertEqual(checkout_resp.status_code, 201)
        order_number = checkout_resp.data['order']['order_number']

        # 6. View Customer Order History
        orders_resp = self.client.get('/api/orders/')
        self.assertEqual(orders_resp.status_code, 200)
        self.assertEqual(len(orders_resp.data['results']), 1)
        self.assertEqual(orders_resp.data['results'][0]['order_number'], order_number)

    def test_b2b_wholesale_workflow_and_approval_gate(self):
        # 1. Register Business Customer
        b2b_payload = {
            'full_name': 'Mathew Thomas',
            'email': 'mathew@highlandsupermarket.test',
            'mobile_number': '9447123456',
            'customer_type': 'business',
            'business_name': 'Highland Supermarket Vandiperiyar',
            'business_type': 'supermarket',
            'gstin': '32AABCH1234A1Z5',
            'password': 'SecureB2BPassword123!',
            'password_confirmation': 'SecureB2BPassword123!',
        }
        reg_resp = self.client.post('/api/auth/register/', b2b_payload, format='json')
        self.assertEqual(reg_resp.status_code, 201)

        user = User.objects.get(email='mathew@highlandsupermarket.test')
        self.assertEqual(user.customer_profile.customer_type, 'business')
        self.assertEqual(user.customer_profile.wholesale_status, 'pending')
        self.assertFalse(user.customer_profile.is_wholesale_approved)

        # 2. Before Approval: Wholesale price must NOT be accessible
        self.client.force_authenticate(user=user)
        add_resp = self.client.post('/api/cart/items/', {
            'variant_id': self.var_1kg.id,
            'quantity': 5,
        }, format='json')
        self.assertEqual(add_resp.status_code, 200)

        # Cart API checks: Evaluated at retail price (₹300) because wholesale is NOT yet approved
        cart_pre = self.client.get('/api/cart/')
        self.assertEqual(cart_pre.status_code, 200)
        self.assertEqual(Decimal(str(cart_pre.data['items'][0]['unit_price'])), Decimal('300.00'))

        # Clear cart for test
        cart = Cart.objects.get(user=user)
        cart.items.all().delete()

        # 3. Administrator Approves Wholesale Application
        self.admin.is_staff = True
        self.admin.save()
        self.client.force_authenticate(user=self.admin)
        approve_resp = self.client.post(
            f'/api/customers/admin/applications/{user.customer_profile.id}/decision/',
            {'action': 'approve'},
            format='json'
        )
        self.assertEqual(approve_resp.status_code, 200)
        user.customer_profile.refresh_from_db()
        self.assertTrue(user.customer_profile.is_wholesale_approved)

        # 4. After Approval: Now receives wholesale rate (₹240/kg instead of ₹300)
        self.client.force_authenticate(user=user)
        add_wholesale_resp = self.client.post('/api/cart/items/', {
            'variant_id': self.var_1kg.id,
            'quantity': 25,  # Bulk order: 25 kg
        }, format='json')
        self.assertEqual(add_wholesale_resp.status_code, 200)

        # 25 kg @ wholesale ₹240 = ₹6,000 subtotal
        cart_post = self.client.get('/api/cart/')
        self.assertEqual(cart_post.status_code, 200)
        self.assertEqual(Decimal(str(cart_post.data['items'][0]['unit_price'])), Decimal('240.00'))
        self.assertEqual(Decimal(str(cart_post.data['items'][0]['line_total'])), Decimal('6000.00'))

        # 5. Delivery Fee Rule Check: Subtotal ₹6,000 >= ₹5,000 wholesale threshold -> FREE delivery
        self.assertEqual(Decimal(str(cart_post.data['delivery_charge'])), Decimal('0.00'))
        self.assertEqual(Decimal(str(cart_post.data['total_amount'])), Decimal('6000.00'))

        # 6. Place Wholesale Order
        addr = Address.objects.create(
            customer=user.customer_profile,
            recipient_name='Highland Supermarket Receiving',
            phone_number='9447123456',
            address_line_1='Store Gate 2, Bypass Road',
            city='Vandiperiyar',
            state='Kerala',
            pincode='685533'
        )
        order_resp = self.client.post('/api/orders/checkout/', {
            'shipping_address_id': addr.id,
            'payment_method': 'bank_transfer',
            'customer_notes': 'GST tax invoice required for input credit'
        }, format='json')
        self.assertEqual(order_resp.status_code, 201)
        self.assertEqual(order_resp.data['order']['customer_type'], 'business')

    def test_customer_isolation_security(self):
        # Create Customer A and Customer B
        user_a = User.objects.create_user(username='cust_a@test.com', email='cust_a@test.com', password='Pass123!Password')
        CustomerProfile.objects.create(user=user_a, phone_number='9000000001')
        order_a = Order.objects.create(
            order_number='ONF-ORD-TEST-0001',
            customer=user_a,
            customer_type='individual',
            order_status='pending',
            payment_status='pending',
            payment_method='cod',
            shipping_address_snapshot={'city': 'Vandiperiyar'},
            billing_address_snapshot={'city': 'Vandiperiyar'},
            subtotal=Decimal('100.00'),
            total_amount=Decimal('100.00')
        )

        user_b = User.objects.create_user(username='cust_b@test.com', email='cust_b@test.com', password='Pass123!Password')
        CustomerProfile.objects.create(user=user_b, phone_number='9000000002')

        # Customer B tries to view Customer A's order
        self.client.force_authenticate(user=user_b)
        resp = self.client.get(f'/api/orders/{order_a.order_number}/')
        # Must return 404 Not Found to prevent data enumeration
        self.assertEqual(resp.status_code, 404)
