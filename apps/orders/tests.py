from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from apps.customers.models import CustomerProfile, Address
from apps.products.models import Category, Product, ProductVariant, QuantityPriceTier, CustomerSpecialPrice
from apps.orders.models import Cart, CartItem, Order, OrderItem, OrderStatusHistory, Payment
from apps.orders.pricing import PricingService

User = get_user_model()


class UnifiedCartAndCheckoutTests(TestCase):
    def setUp(self):
        # 1. Categories & Products
        self.category = Category.objects.create(name='Banana Chips', slug='banana-chips', is_active=True)
        self.product = Product.objects.create(
            name='Kerala Banana Chips',
            slug='kerala-banana-chips',
            category=self.category,
            short_description='Traditional salted banana chips fried in pure coconut oil',
            is_active=True
        )

        # 250g variant: Retail ₹80, Wholesale ₹65, MOQ 10
        self.variant_250 = ProductVariant.objects.create(
            product=self.product,
            sku='ONF-BC-250G',
            package_weight=Decimal('250.00'),
            package_unit='g',
            price=Decimal('80.00'),
            wholesale_price=Decimal('65.00'),
            minimum_order_quantity=10,
            is_available=True,
            is_available_retail=True,
            is_available_wholesale=True
        )

        # 500g variant: Retail ₹155, Wholesale ₹125, MOQ 10
        self.variant_500 = ProductVariant.objects.create(
            product=self.product,
            sku='ONF-BC-500G',
            package_weight=Decimal('500.00'),
            package_unit='g',
            price=Decimal('155.00'),
            wholesale_price=Decimal('125.00'),
            minimum_order_quantity=10,
            is_available=True,
            is_available_retail=True,
            is_available_wholesale=True
        )

        # Volume tier for 500g: 50+ @ ₹115, 100+ @ ₹105
        self.tier_50 = QuantityPriceTier.objects.create(
            variant=self.variant_500,
            min_quantity=50,
            price_per_unit=Decimal('115.00')
        )
        self.tier_100 = QuantityPriceTier.objects.create(
            variant=self.variant_500,
            min_quantity=100,
            price_per_unit=Decimal('105.00')
        )

        from apps.inventory.services import InventoryService
        InventoryService.record_stock_in(self.variant_250, 500, reason="Initial test stock")
        InventoryService.record_stock_in(self.variant_500, 500, reason="Initial test stock")

        # 2. Retail Customer (B2C)
        self.retail_user = User.objects.create_user(
            username='retail@customer.in',
            email='retail@customer.in',
            password='Password123!',
            first_name='Kavya',
            last_name='Nair'
        )
        self.retail_profile = CustomerProfile.objects.create(
            user=self.retail_user,
            customer_type='individual',
            wholesale_status='none',
            phone_number='9846011111'
        )
        self.retail_address = Address.objects.create(
            customer=self.retail_profile,
            address_type='shipping',
            recipient_name='Kavya Nair',
            phone_number='9846011111',
            address_line_1='Flat 4B, Hilltop Residency',
            city='Kochi',
            district='Ernakulam',
            state='Kerala',
            pincode='682001',
            is_default=True
        )
        self.retail_client = APIClient()
        self.retail_client.force_authenticate(user=self.retail_user)

        # 3. Approved Wholesale Customer (B2B)
        self.wholesale_user = User.objects.create_user(
            username='wholesale@trader.in',
            email='wholesale@trader.in',
            password='Password123!',
            first_name='Mathew',
            last_name='Joseph'
        )
        self.wholesale_profile = CustomerProfile.objects.create(
            user=self.wholesale_user,
            customer_type='business',
            wholesale_status='approved',
            business_name='Highland Bakers',
            business_type='bakery',
            contact_person='Mathew Joseph',
            phone_number='9846022222',
            gstin='32ABCDE1234F1Z5'
        )
        self.wholesale_address = Address.objects.create(
            customer=self.wholesale_profile,
            address_type='shipping',
            recipient_name='Highland Bakers Vandiperiyar',
            phone_number='9846022222',
            address_line_1='Main Bazaar Road',
            city='Vandiperiyar',
            district='Idukki',
            state='Kerala',
            pincode='685533',
            is_default=True
        )
        self.wholesale_client = APIClient()
        self.wholesale_client.force_authenticate(user=self.wholesale_user)

        # 4. Pending Wholesale Customer (Should NOT receive wholesale pricing)
        self.pending_user = User.objects.create_user(
            username='pending@trader.in',
            email='pending@trader.in',
            password='Password123!',
            first_name='Arun',
            last_name='Kumar'
        )
        self.pending_profile = CustomerProfile.objects.create(
            user=self.pending_user,
            customer_type='business',
            wholesale_status='pending',
            business_name='Kumar Stores',
            business_type='retail_shop',
            contact_person='Arun Kumar',
            phone_number='9846033333'
        )
        self.pending_client = APIClient()
        self.pending_client.force_authenticate(user=self.pending_user)

        # 5. Staff Admin
        self.admin_user = User.objects.create_superuser(
            username='admin@onfresh.in',
            email='admin@onfresh.in',
            password='AdminPassword123!'
        )
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.admin_user)

    # -----------------------------------------------------------------
    # Part 1 & 2: Cart Operations & Pricing Tests
    # -----------------------------------------------------------------

    def test_retail_customer_cart_pricing(self):
        """B2C customer gets retail MRP (₹80 for 250g, ₹155 for 500g) with MOQ=1."""
        res = self.retail_client.post('/api/cart/items/', {
            'variant_id': self.variant_250.id,
            'quantity': 2
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data['items_count'], 2)
        # 2 packets * ₹80 = ₹160
        self.assertEqual(data['subtotal'], 160.0)
        # Below ₹500 threshold: ₹50 delivery fee
        self.assertEqual(data['delivery_charge'], 50.0)
        self.assertEqual(data['total_amount'], 210.0)
        self.assertEqual(data['customer_segment'], 'retail')
        self.assertFalse(data['is_wholesale_approved'])

    def test_retail_customer_free_delivery_threshold(self):
        """Retail orders >= ₹500 receive free delivery."""
        res = self.retail_client.post('/api/cart/items/', {
            'variant_id': self.variant_500.id,
            'quantity': 4  # 4 * ₹155 = ₹620 >= ₹500
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data['subtotal'], 620.0)
        self.assertEqual(data['delivery_charge'], 0.0)
        self.assertEqual(data['total_amount'], 620.0)

    def test_wholesale_customer_base_pricing_and_moq(self):
        """Approved B2B customer gets wholesale base price (₹125 for 500g) and MOQ=10."""
        # Add 10 units of 500g: 10 * ₹125 = ₹1250 (Retail would be 10 * ₹155 = ₹1550)
        res = self.wholesale_client.post('/api/cart/items/', {
            'variant_id': self.variant_500.id,
            'quantity': 10
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertTrue(data['is_wholesale_approved'])
        self.assertEqual(data['customer_segment'], 'wholesale')
        self.assertEqual(data['subtotal'], 1250.0)
        # Wholesale discount is ₹1550 - ₹1250 = ₹300
        self.assertEqual(data['discount_amount'], 300.0)
        # Under ₹5000 wholesale threshold: ₹200 freight
        self.assertEqual(data['delivery_charge'], 200.0)
        self.assertEqual(data['total_amount'], 1450.0)

    def test_wholesale_customer_volume_tier_pricing(self):
        """Approved wholesale customer purchasing 60 units triggers Tier 1 (₹115/unit)."""
        res = self.wholesale_client.post('/api/cart/items/', {
            'variant_id': self.variant_500.id,
            'quantity': 60
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        item = data['items'][0]
        self.assertEqual(item['unit_price'], 115.0)
        # 60 * ₹115 = ₹6900
        self.assertEqual(data['subtotal'], 6900.0)
        # Over ₹5000 wholesale threshold: FREE delivery (₹0)
        self.assertEqual(data['delivery_charge'], 0.0)
        self.assertEqual(data['total_amount'], 6900.0)

    def test_wholesale_customer_super_bulk_tier(self):
        """Approved wholesale customer purchasing 100 units triggers Tier 2 (₹105/unit)."""
        res = self.wholesale_client.post('/api/cart/items/', {
            'variant_id': self.variant_500.id,
            'quantity': 100
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        item = data['items'][0]
        self.assertEqual(item['unit_price'], 105.0)
        # 100 * ₹105 = ₹10,500
        self.assertEqual(data['subtotal'], 10500.0)

    def test_unapproved_wholesale_customer_denied_wholesale_rates(self):
        """Pending wholesale account is denied wholesale discounts until approved."""
        res = self.pending_client.post('/api/cart/items/', {
            'variant_id': self.variant_500.id,
            'quantity': 20
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertFalse(data['is_wholesale_approved'])
        self.assertEqual(data['customer_segment'], 'retail')
        # Gets retail price: 20 * ₹155 = ₹3100
        self.assertEqual(data['subtotal'], 3100.0)
        self.assertEqual(data['discount_amount'], 0.0)

    def test_cart_item_update_and_remove(self):
        """Update quantity and remove cart item."""
        # Add 2 items
        self.retail_client.post('/api/cart/items/', {'variant_id': self.variant_250.id, 'quantity': 2})
        cart = Cart.objects.get(user=self.retail_user)
        cart_item = cart.items.first()

        # Update to 5 items
        update_res = self.retail_client.patch(f'/api/cart/items/{cart_item.id}/', {'quantity': 5})
        self.assertEqual(update_res.status_code, status.HTTP_200_OK)
        self.assertEqual(update_res.json()['items_count'], 5)

        # Remove item
        del_res = self.retail_client.delete(f'/api/cart/items/{cart_item.id}/')
        self.assertEqual(del_res.status_code, status.HTTP_200_OK)
        self.assertEqual(del_res.json()['items_count'], 0)

    def test_cart_clear(self):
        """Clear all items in cart."""
        self.retail_client.post('/api/cart/items/', {'variant_id': self.variant_250.id, 'quantity': 2})
        self.retail_client.post('/api/cart/items/', {'variant_id': self.variant_500.id, 'quantity': 3})

        clear_res = self.retail_client.delete('/api/cart/clear/')
        self.assertEqual(clear_res.status_code, status.HTTP_200_OK)
        self.assertEqual(clear_res.json()['items_count'], 0)
        self.assertEqual(CartItem.objects.filter(cart__user=self.retail_user).count(), 0)

    def test_cart_sync_guest_items(self):
        """Guest localStorage items are merged into user's cart on sync."""
        sync_res = self.retail_client.post('/api/cart/sync/', {
            'items': [
                {'variant_id': self.variant_250.id, 'quantity': 3},
                {'variant_id': self.variant_500.id, 'quantity': 2},
            ]
        }, format='json')
        self.assertEqual(sync_res.status_code, status.HTTP_200_OK)
        data = sync_res.json()
        self.assertEqual(data['items_count'], 5)

    # -----------------------------------------------------------------
    # Part 3 & 4: Checkout, Orders & Price Snapshots
    # -----------------------------------------------------------------

    def test_checkout_validation_empty_cart(self):
        """Checkout fails when cart is empty."""
        res = self.retail_client.post('/api/orders/checkout/', {
            'shipping_address_id': self.retail_address.id,
            'payment_method': 'cod'
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('empty cart', res.json()['message'].lower())

    def test_checkout_rejects_unowned_address(self):
        """Checkout fails if user tries to use another customer's address."""
        # Add item to cart first
        self.retail_client.post('/api/cart/items/', {'variant_id': self.variant_250.id, 'quantity': 2})

        # Try to use wholesale customer's address
        res = self.retail_client.post('/api/orders/checkout/', {
            'shipping_address_id': self.wholesale_address.id,
            'payment_method': 'cod'
        })
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_successful_retail_checkout_cod(self):
        """Successful retail checkout with Cash on Delivery."""
        self.retail_client.post('/api/cart/items/', {'variant_id': self.variant_250.id, 'quantity': 3})

        res = self.retail_client.post('/api/orders/checkout/', {
            'shipping_address_id': self.retail_address.id,
            'payment_method': 'cod',
            'customer_notes': 'Please ring bell on delivery'
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        order_data = res.json()['order']
        self.assertTrue(order_data['order_number'].startswith('ONF-'))
        self.assertEqual(order_data['order_status'], 'pending')
        self.assertEqual(order_data['payment_status'], 'pending')
        self.assertEqual(order_data['payment_method'], 'cod')
        # Subtotal: 3 * ₹80 = ₹240, Delivery: ₹50, Total: ₹290
        self.assertEqual(float(order_data['subtotal']), 240.0)
        self.assertEqual(float(order_data['delivery_charge']), 50.0)
        self.assertEqual(float(order_data['total_amount']), 290.0)
        # Cart must be cleared
        self.assertEqual(CartItem.objects.filter(cart__user=self.retail_user).count(), 0)

    def test_successful_wholesale_checkout_bank_transfer(self):
        """Successful wholesale checkout with Bank Transfer and tier discounts."""
        self.wholesale_client.post('/api/cart/items/', {'variant_id': self.variant_500.id, 'quantity': 50})

        res = self.wholesale_client.post('/api/orders/checkout/', {
            'shipping_address_id': self.wholesale_address.id,
            'payment_method': 'bank_transfer',
            'customer_notes': 'Bulk order for Vandiperiyar outlet'
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()
        order_data = data['order']
        self.assertEqual(order_data['customer_type'], 'business')
        # 50 * ₹115 = ₹5750, Free freight (>= ₹5000)
        self.assertEqual(float(order_data['subtotal']), 5750.0)
        self.assertEqual(float(order_data['delivery_charge']), 0.0)
        self.assertEqual(float(order_data['total_amount']), 5750.0)
        # Bank instructions provided in payment instructions
        self.assertIn('bank_details', data['payment_instructions'])
        self.assertEqual(data['payment_instructions']['bank_details']['account_number'], '39485720192')

    def test_price_snapshot_preservation(self):
        """Historical order prices must NOT change when administrator changes current variant pricing."""
        # 1. Place order
        self.retail_client.post('/api/cart/items/', {'variant_id': self.variant_250.id, 'quantity': 2})
        checkout_res = self.retail_client.post('/api/orders/checkout/', {
            'shipping_address_id': self.retail_address.id,
            'payment_method': 'cod'
        })
        order_number = checkout_res.json()['order']['order_number']
        order = Order.objects.get(order_number=order_number)
        item = order.items.first()
        self.assertEqual(item.unit_price, Decimal('80.00'))
        self.assertEqual(item.line_total, Decimal('160.00'))

        # 2. Admin increases variant price to ₹120.00
        self.variant_250.price = Decimal('120.00')
        self.variant_250.save()

        # 3. Retrieve order again: MUST still reflect original ₹80.00 price snapshot
        get_res = self.retail_client.get(f'/api/orders/{order_number}/')
        self.assertEqual(get_res.status_code, status.HTTP_200_OK)
        fetched_item = get_res.json()['items'][0]
        self.assertEqual(float(fetched_item['unit_price']), 80.0)
        self.assertEqual(float(fetched_item['line_total']), 160.0)

    def test_customer_isolation_cannot_view_others_orders(self):
        """Customer A cannot view Customer B's orders."""
        # Retail user creates order
        self.retail_client.post('/api/cart/items/', {'variant_id': self.variant_250.id, 'quantity': 1})
        order_res = self.retail_client.post('/api/orders/checkout/', {
            'shipping_address_id': self.retail_address.id,
            'payment_method': 'cod'
        })
        order_number = order_res.json()['order']['order_number']

        # Wholesale user attempts to fetch Retail user's order: returns 404
        spy_res = self.wholesale_client.get(f'/api/orders/{order_number}/')
        self.assertEqual(spy_res.status_code, status.HTTP_404_NOT_FOUND)

    # -----------------------------------------------------------------
    # Part 5: Order Status Transitions
    # -----------------------------------------------------------------

    def test_order_status_transitions_and_cancellation(self):
        """Order lifecycle transitions and valid cancellation."""
        self.retail_client.post('/api/cart/items/', {'variant_id': self.variant_250.id, 'quantity': 1})
        res = self.retail_client.post('/api/orders/checkout/', {
            'shipping_address_id': self.retail_address.id,
            'payment_method': 'cod'
        })
        order_number = res.json()['order']['order_number']
        order = Order.objects.get(order_number=order_number)

        # Admin transitions: pending -> confirmed -> processing
        order.transition_to('confirmed', changed_by=self.admin_user, notes='Confirmed by office')
        self.assertEqual(order.order_status, 'confirmed')

        order.transition_to('processing', changed_by=self.admin_user, notes='In kitchen frying')
        self.assertEqual(order.order_status, 'processing')

        # Invalid transition: cannot jump from processing directly to delivered
        with self.assertRaises(Exception):
            order.transition_to('delivered')

        # Check status history was logged
        history = OrderStatusHistory.objects.filter(order=order)
        self.assertEqual(history.count(), 3)  # initial pending + confirmed + processing

    # -----------------------------------------------------------------
    # Part 6: Payment Idempotency & Verification
    # -----------------------------------------------------------------

    def test_payment_idempotency_and_verification(self):
        """Online payment initiation enforces idempotency and signature verification."""
        self.retail_client.post('/api/cart/items/', {'variant_id': self.variant_250.id, 'quantity': 1})
        order_res = self.retail_client.post('/api/orders/checkout/', {
            'shipping_address_id': self.retail_address.id,
            'payment_method': 'online'
        })
        order_number = order_res.json()['order']['order_number']

        # Initiate payment
        init_res = self.retail_client.post(f'/api/orders/{order_number}/payment/initiate/', {
            'idempotency_key': 'idem_key_12345'
        })
        self.assertEqual(init_res.status_code, status.HTTP_200_OK)
        txn_id = init_res.json()['transaction_id']

        # Verify payment with signature
        verify_res = self.retail_client.post(f'/api/orders/{order_number}/payment/verify/', {
            'transaction_id': txn_id,
            'gateway_signature': 'SIG_SUCCESS_SECURE_HASH'
        })
        self.assertEqual(verify_res.status_code, status.HTTP_200_OK)
        self.assertEqual(verify_res.json()['payment_status'], 'paid')

        # Verify duplicate check
        dup_res = self.retail_client.post(f'/api/orders/{order_number}/payment/verify/', {
            'transaction_id': txn_id,
            'gateway_signature': 'SIG_SUCCESS_SECURE_HASH'
        })
        self.assertEqual(dup_res.status_code, status.HTTP_200_OK)
        self.assertIn('already verified', dup_res.json()['message'].lower())

