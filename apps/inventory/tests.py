from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient
from rest_framework import status
from apps.customers.models import CustomerProfile, Address
from apps.products.models import Category, Product, ProductVariant
from apps.orders.models import Order, OrderItem
from apps.inventory.models import StockItem, ProductionBatch, StockMovement
from apps.inventory.services import InventoryService

User = get_user_model()


class InventoryManagementTests(TestCase):
    def setUp(self):
        # 1. Product & Variant
        self.category = Category.objects.create(name='Kerala Snacks', slug='kerala-snacks', is_active=True)
        self.product = Product.objects.create(
            name='Banana Chips Salted',
            slug='banana-chips-salted',
            category=self.category,
            short_description='Authentic Vandiperiyar banana chips in coconut oil',
            is_active=True
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku='ONF-BC-S-500G',
            package_weight=Decimal('500.00'),
            package_unit='g',
            price=Decimal('160.00'),
            wholesale_price=Decimal('130.00'),
            minimum_order_quantity=10,
            is_available=True,
            is_available_retail=True,
            is_available_wholesale=True
        )

        # 2. Staff User (Admin)
        self.staff_user = User.objects.create_superuser(
            username='inventory_manager@onfresh.in',
            email='inventory_manager@onfresh.in',
            password='StaffPassword123!'
        )
        self.staff_client = APIClient()
        self.staff_client.force_authenticate(user=self.staff_user)

        # 3. Regular Retail Customer
        self.retail_user = User.objects.create_user(
            username='customer@kerala.in',
            email='customer@kerala.in',
            password='CustomerPass123!'
        )
        self.retail_client = APIClient()
        self.retail_client.force_authenticate(user=self.retail_user)

    # -------------------------------------------------------------
    # Part 1: Stock In, Out, Adjustments & Negative Stock Prevention
    # -------------------------------------------------------------

    def test_stock_in_increases_available_quantity(self):
        """Stock in operation adds units and logs audit movement."""
        stock = InventoryService.record_stock_in(
            variant=self.variant,
            quantity=100,
            movement_type='purchase_in',
            reference='PO-2026-001',
            reason='Raw package delivery from packaging supplier',
            user=self.staff_user
        )
        self.assertEqual(stock.quantity_on_hand, 100)
        self.assertEqual(stock.available_to_sell, 100)

        # Verify audit movement
        movement = StockMovement.objects.filter(variant=self.variant).first()
        self.assertIsNotNone(movement)
        self.assertEqual(movement.movement_type, 'purchase_in')
        self.assertEqual(movement.quantity, 100)
        self.assertEqual(movement.balance_after, 100)
        self.assertEqual(movement.user, self.staff_user)

    def test_stock_out_reduces_inventory(self):
        """Stock out deducts units and verifies balance."""
        InventoryService.record_stock_in(self.variant, 50, user=self.staff_user)

        stock = InventoryService.record_stock_out(
            variant=self.variant,
            quantity=15,
            movement_type='damage',
            reason='Damaged package in warehouse',
            user=self.staff_user
        )
        self.assertEqual(stock.quantity_on_hand, 35)
        self.assertEqual(stock.available_to_sell, 35)

    def test_negative_stock_prevention(self):
        """Cannot remove more stock than available to sell."""
        InventoryService.record_stock_in(self.variant, 20, user=self.staff_user)

        with self.assertRaises(ValidationError):
            InventoryService.record_stock_out(self.variant, 25, user=self.staff_user)

    def test_stock_adjustment_updates_count(self):
        """Audit adjustment reconciles physical stock count."""
        InventoryService.record_stock_in(self.variant, 50, user=self.staff_user)

        stock = InventoryService.record_stock_adjustment(
            variant=self.variant,
            new_quantity_on_hand=42,
            reason='Weekly warehouse audit count adjustment',
            user=self.staff_user
        )
        self.assertEqual(stock.quantity_on_hand, 42)
        self.assertEqual(stock.available_to_sell, 42)

    # -------------------------------------------------------------
    # Part 2 & 3: Production Batches, Idempotency & FEFO Expiry
    # -------------------------------------------------------------

    def test_production_batch_creation_and_completion(self):
        """Production batch adds manufactured quantity to stock upon completion."""
        today = timezone.localdate()
        exp_date = today + timezone.timedelta(days=90)

        batch = ProductionBatch.objects.create(
            product=self.product,
            variant=self.variant,
            production_date=today,
            expiry_date=exp_date,
            manufactured_quantity=300,
            remaining_quantity=0,
            status='in_production',
            created_by=self.staff_user
        )
        self.assertFalse(batch.is_stock_added)

        # Complete batch
        completed_batch = InventoryService.complete_production_batch(batch, user=self.staff_user)
        self.assertEqual(completed_batch.status, 'completed')
        self.assertEqual(completed_batch.remaining_quantity, 300)
        self.assertTrue(completed_batch.is_stock_added)

        # Check stock was updated
        stock = StockItem.objects.get(variant=self.variant)
        self.assertEqual(stock.quantity_on_hand, 300)

    def test_duplicate_batch_completion_idempotency(self):
        """Completing a completed batch does NOT add stock twice."""
        today = timezone.localdate()
        batch = ProductionBatch.objects.create(
            product=self.product,
            variant=self.variant,
            production_date=today,
            expiry_date=today + timezone.timedelta(days=60),
            manufactured_quantity=100,
            created_by=self.staff_user
        )
        InventoryService.complete_production_batch(batch, user=self.staff_user)
        stock_first = StockItem.objects.get(variant=self.variant).quantity_on_hand
        self.assertEqual(stock_first, 100)

        # Attempt second completion
        InventoryService.complete_production_batch(batch, user=self.staff_user)
        stock_second = StockItem.objects.get(variant=self.variant).quantity_on_hand
        self.assertEqual(stock_second, 100)  # Unchanged!

    def test_batch_expiry_validation(self):
        """Expiry date cannot be prior to or equal to production date."""
        today = timezone.localdate()
        past_date = today - timezone.timedelta(days=1)

        batch = ProductionBatch(
            product=self.product,
            variant=self.variant,
            production_date=today,
            expiry_date=past_date,
            manufactured_quantity=100
        )
        with self.assertRaises(ValidationError):
            batch.clean()

    def test_fefo_allocation_excludes_expired_batches(self):
        """
        FEFO order dispatch allocates from earliest expiring batch,
        and completely ignores expired batches.
        """
        today = timezone.localdate()

        # Batch 1: Expired yesterday (Remaining 50)
        expired_batch = ProductionBatch.objects.create(
            product=self.product,
            variant=self.variant,
            production_date=today - timezone.timedelta(days=90),
            expiry_date=today - timezone.timedelta(days=1),
            manufactured_quantity=50,
            remaining_quantity=50,
            status='completed',
            is_stock_added=True
        )

        # Batch 2: Expires in 15 days (Remaining 40)
        early_batch = ProductionBatch.objects.create(
            product=self.product,
            variant=self.variant,
            production_date=today - timezone.timedelta(days=20),
            expiry_date=today + timezone.timedelta(days=15),
            manufactured_quantity=40,
            remaining_quantity=40,
            status='completed',
            is_stock_added=True
        )

        # Batch 3: Expires in 60 days (Remaining 100)
        later_batch = ProductionBatch.objects.create(
            product=self.product,
            variant=self.variant,
            production_date=today - timezone.timedelta(days=5),
            expiry_date=today + timezone.timedelta(days=60),
            manufactured_quantity=100,
            remaining_quantity=100,
            status='completed',
            is_stock_added=True
        )

        # Physical stock = 140 non-expired units
        stock = InventoryService.get_or_create_stock_item(self.variant)
        stock.quantity_on_hand = 140
        stock.save()

        # Create and dispatch order of 50 units
        order = Order.objects.create(
            customer=self.retail_user,
            customer_type='individual',
            order_status='confirmed',
            total_amount=Decimal('8000.00'),
            is_stock_reserved=True
        )
        stock.reserved_quantity = 50
        stock.save()

        OrderItem.objects.create(
            order=order,
            variant=self.variant,
            product_name=self.product.name,
            sku=self.variant.sku,
            package_weight=self.variant.package_weight,
            package_unit=self.variant.package_unit,
            quantity=50,
            unit_price=Decimal('160.00'),
            retail_price=Decimal('160.00'),
            line_total=Decimal('8000.00')
        )

        # Dispatch order
        InventoryService.dispatch_order_stock(order, user=self.staff_user)

        # Check:
        # Expired batch MUST NOT be touched (remains 50)
        expired_batch.refresh_from_db()
        self.assertEqual(expired_batch.remaining_quantity, 50)

        # Early batch (40 units) exhausted completely (0 remaining)
        early_batch.refresh_from_db()
        self.assertEqual(early_batch.remaining_quantity, 0)
        self.assertEqual(early_batch.status, 'exhausted')

        # Later batch supplied remaining 10 units (100 - 10 = 90 remaining)
        later_batch.refresh_from_db()
        self.assertEqual(later_batch.remaining_quantity, 90)

    # -------------------------------------------------------------
    # Part 4: Order Reservation, Cancellation Release & Dispatch
    # -------------------------------------------------------------

    def test_order_stock_reservation_and_cancellation_release(self):
        """Order reservation holds units; cancellation releases them."""
        InventoryService.record_stock_in(self.variant, 50, user=self.staff_user)

        order = Order.objects.create(
            customer=self.retail_user,
            customer_type='individual',
            order_status='pending',
            total_amount=Decimal('3200.00')
        )
        OrderItem.objects.create(
            order=order,
            variant=self.variant,
            product_name=self.product.name,
            sku=self.variant.sku,
            package_weight=self.variant.package_weight,
            package_unit=self.variant.package_unit,
            quantity=20,
            unit_price=Decimal('160.00'),
            retail_price=Decimal('160.00'),
            line_total=Decimal('3200.00')
        )

        # Transition to confirmed triggers reservation
        order.transition_to('confirmed', changed_by=self.staff_user)
        self.assertTrue(order.is_stock_reserved)

        stock = StockItem.objects.get(variant=self.variant)
        self.assertEqual(stock.quantity_on_hand, 50)
        self.assertEqual(stock.reserved_quantity, 20)
        self.assertEqual(stock.available_to_sell, 30)

        # Transition to cancelled triggers release
        order.transition_to('cancelled', changed_by=self.staff_user, notes='Customer cancelled')
        self.assertFalse(order.is_stock_reserved)

        stock.refresh_from_db()
        self.assertEqual(stock.quantity_on_hand, 50)
        self.assertEqual(stock.reserved_quantity, 0)
        self.assertEqual(stock.available_to_sell, 50)

    def test_insufficient_stock_prevents_order_confirmation(self):
        """Cannot confirm an order if available stock is insufficient."""
        InventoryService.record_stock_in(self.variant, 10, user=self.staff_user)

        order = Order.objects.create(
            customer=self.retail_user,
            customer_type='individual',
            order_status='pending',
            total_amount=Decimal('4000.00')
        )
        OrderItem.objects.create(
            order=order,
            variant=self.variant,
            product_name=self.product.name,
            sku=self.variant.sku,
            package_weight=self.variant.package_weight,
            package_unit=self.variant.package_unit,
            quantity=25,  # Requires 25, only 10 available
            unit_price=Decimal('160.00'),
            retail_price=Decimal('160.00'),
            line_total=Decimal('4000.00')
        )

        with self.assertRaises(ValidationError):
            order.transition_to('confirmed', changed_by=self.staff_user)

    # -------------------------------------------------------------
    # Part 5: Authorization & API Security
    # -------------------------------------------------------------

    def test_unauthorized_customer_cannot_modify_inventory(self):
        """Regular retail/wholesale customers cannot perform stock-in or adjustments."""
        res = self.retail_client.post('/api/inventory/stock-in/', {
            'variant_id': self.variant.id,
            'quantity': 50
        })
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        adj_res = self.retail_client.post('/api/inventory/adjust/', {
            'variant_id': self.variant.id,
            'new_quantity_on_hand': 100,
            'reason': 'Hacker change'
        })
        self.assertEqual(adj_res.status_code, status.HTTP_403_FORBIDDEN)

