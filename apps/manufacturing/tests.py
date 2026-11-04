from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from apps.products.models import Category, Product, ProductVariant
from apps.inventory.models import StockItem, ProductionBatch
from apps.accounts.roles import ROLE_ADMIN, ROLE_SUPER_ADMIN, ensure_staff_roles
from .models import (
    RawMaterialCategory,
    RawMaterial,
    RawMaterialMovement,
    Supplier,
    PurchaseOrder,
    PurchaseOrderItem,
    Recipe,
    RecipeIngredient,
    RecipePackaging,
    ProductionOrder,
    QualityInspection,
)
from .services import (
    RawMaterialService,
    PurchaseService,
    ProductionService,
    QualityService,
)

User = get_user_model()


class ManufacturingAppTests(TestCase):
    def setUp(self):
        ensure_staff_roles()

        self.admin_user = User.objects.create_superuser(
            username='mfgadmin',
            email='mfgadmin@onfresh.test',
            password='Password123!',
            first_name='Mfg',
            last_name='Admin'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin_user)

        # Base Product & Variant
        self.prod_cat = Category.objects.create(name='Banana Chips', slug='banana-chips')
        self.product = Product.objects.create(
            name='Kerala Banana Chips',
            slug='kerala-banana-chips',
            category=self.prod_cat
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            package_weight=Decimal('250.00'),
            package_unit='g',
            sku='ONF-CHIP-250G',
            price=Decimal('80.00'),
            wholesale_price=Decimal('65.00')
        )

        # Raw Material Categories
        self.cat_agro = RawMaterialCategory.objects.create(
            name='Agricultural Ingredients',
            slug='agricultural-ingredients'
        )
        self.cat_pkg = RawMaterialCategory.objects.create(
            name='Packaging Materials',
            slug='packaging-materials'
        )

        # Raw Materials
        self.mat_banana = RawMaterial.objects.create(
            material_code='RM-TEST-BAN',
            name='Raw Nendran Bananas',
            category=self.cat_agro,
            unit_of_measure='kg',
            current_stock=Decimal('200.000'),
            minimum_stock_level=Decimal('50.000'),
            unit_cost=Decimal('45.00')
        )
        self.mat_oil = RawMaterial.objects.create(
            material_code='RM-TEST-OIL',
            name='Cold-Pressed Coconut Oil',
            category=self.cat_agro,
            unit_of_measure='l',
            current_stock=Decimal('100.000'),
            minimum_stock_level=Decimal('30.000'),
            unit_cost=Decimal('180.00')
        )
        self.mat_pouch = RawMaterial.objects.create(
            material_code='PKG-TEST-POUCH',
            name='250g Printed Pouch',
            category=self.cat_pkg,
            unit_of_measure='pcs',
            current_stock=Decimal('1000.000'),
            minimum_stock_level=Decimal('200.000'),
            unit_cost=Decimal('3.50')
        )

        # Supplier
        self.supplier = Supplier.objects.create(
            supplier_code='SUP-TEST-001',
            name='Idukki Agro Farms',
            phone='9447000001',
            address_line1='Vandiperiyar Town',
            city='Vandiperiyar',
            state='Kerala'
        )

        # Master Recipe
        self.recipe = Recipe.objects.create(
            recipe_code='RCP-TEST-BAN-V1',
            name='Standard 250g Banana Chips Recipe',
            product=self.product,
            variant=self.variant,
            batch_output_quantity=Decimal('50.000'),
            output_unit='packets',
            target_variant_units=100,
            estimated_labor_cost=Decimal('300.00'),
            estimated_overhead_cost=Decimal('150.00')
        )
        RecipeIngredient.objects.create(
            recipe=self.recipe,
            material=self.mat_banana,
            quantity=Decimal('30.000'),
            unit='kg',
            wastage_percentage=Decimal('5.00')
        )
        RecipeIngredient.objects.create(
            recipe=self.recipe,
            material=self.mat_oil,
            quantity=Decimal('8.000'),
            unit='l',
            wastage_percentage=Decimal('0.00')
        )
        RecipePackaging.objects.create(
            recipe=self.recipe,
            packaging_material=self.mat_pouch,
            quantity=Decimal('100.000'),
            unit='pcs'
        )

    def test_raw_material_stock_in_and_out(self):
        # Initial stock: 200.000
        RawMaterialService.record_stock_in(
            material=self.mat_banana,
            quantity=Decimal('50.000'),
            unit_cost=Decimal('46.00'),
            reference_number='PO-IN-001',
            user=self.admin_user
        )
        self.mat_banana.refresh_from_db()
        self.assertEqual(self.mat_banana.current_stock, Decimal('250.000'))
        self.assertEqual(self.mat_banana.unit_cost, Decimal('46.00'))

        # Deduct stock
        RawMaterialService.record_stock_out(
            material=self.mat_banana,
            quantity=Decimal('20.000'),
            reference_number='KITCHEN-001',
            user=self.admin_user
        )
        self.mat_banana.refresh_from_db()
        self.assertEqual(self.mat_banana.current_stock, Decimal('230.000'))

        # Check movements
        movements = RawMaterialMovement.objects.filter(material=self.mat_banana)
        self.assertEqual(movements.count(), 2)

    def test_raw_material_negative_stock_prevented(self):
        with self.assertRaises(Exception):
            RawMaterialService.record_stock_out(
                material=self.mat_banana,
                quantity=Decimal('500.000')  # Exceeds 200 available
            )

    def test_raw_material_physical_audit_adjustment(self):
        RawMaterialService.record_adjustment(
            material=self.mat_banana,
            new_quantity=Decimal('185.000'),
            notes='Quarterly stock take',
            user=self.admin_user
        )
        self.mat_banana.refresh_from_db()
        self.assertEqual(self.mat_banana.current_stock, Decimal('185.000'))
        movement = RawMaterialMovement.objects.filter(material=self.mat_banana).first()
        self.assertEqual(movement.movement_type, 'adjustment')
        self.assertEqual(movement.quantity, Decimal('15.000'))

    def test_purchase_order_flow_and_idempotent_receipt(self):
        po = PurchaseOrder.objects.create(
            supplier=self.supplier,
            order_date=timezone.localdate(),
            status='ordered'
        )
        PurchaseOrderItem.objects.create(
            purchase_order=po,
            material=self.mat_banana,
            ordered_quantity=Decimal('100.000'),
            unit_cost=Decimal('45.00')
        )
        po.recalculate_totals()
        self.assertEqual(po.total_amount, Decimal('4500.00'))
        self.assertFalse(po.is_stock_added)

        # Banana stock prior to receipt
        initial_stock = self.mat_banana.current_stock

        # Receive PO
        received_po = PurchaseService.receive_purchase_order(
            purchase_order=po,
            vendor_invoice_number='INV-VND-889',
            user=self.admin_user
        )
        self.assertEqual(received_po.status, 'received')
        self.assertTrue(received_po.is_stock_added)

        self.mat_banana.refresh_from_db()
        self.assertEqual(self.mat_banana.current_stock, initial_stock + Decimal('100.000'))

        # Idempotent second receipt call should not double-add stock
        PurchaseService.receive_purchase_order(purchase_order=received_po)
        self.mat_banana.refresh_from_db()
        self.assertEqual(self.mat_banana.current_stock, initial_stock + Decimal('100.000'))

    def test_purchase_order_supplier_payment(self):
        po = PurchaseOrder.objects.create(
            supplier=self.supplier,
            status='ordered',
            total_amount=Decimal('5000.00')
        )
        payment = PurchaseService.record_supplier_payment(
            purchase_order=po,
            amount=Decimal('5000.00'),
            payment_method='bank_transfer',
            reference_number='UTR888999000',
            user=self.admin_user
        )
        po.refresh_from_db()
        self.assertEqual(po.payment_status, 'paid')
        self.assertEqual(po.amount_paid, Decimal('5000.00'))

    def test_recipe_cost_calculation(self):
        # 30kg * 1.05 waste = 31.5kg * ₹45 = ₹1417.50
        # 8l * ₹180 = ₹1440.00
        # Packaging: 100 * ₹3.50 = ₹350.00
        # Labor: ₹300.00, Overhead: ₹150.00
        # Total = 1417.50 + 1440.00 + 350.00 + 300.00 + 150.00 = ₹3657.50
        total_cost = self.recipe.estimated_total_cost
        self.assertEqual(total_cost, Decimal('3657.50'))

        # Cost per packet (100 packets): ₹36.58
        cost_per_unit = self.recipe.estimated_cost_per_unit
        self.assertEqual(cost_per_unit, Decimal('36.58'))

    def test_ingredient_availability_check(self):
        # Target 100 packets requires 31.5kg banana, 8l oil, 100 pouches
        # Stock: 200kg banana, 100l oil, 1000 pouches -> ample stock
        check = ProductionService.check_ingredient_availability(self.recipe, target_units=100)
        self.assertTrue(check['is_sufficient'])
        self.assertEqual(len(check['shortfalls']), 0)

        # Target 10,000 packets -> causes shortfall
        check_excess = ProductionService.check_ingredient_availability(self.recipe, target_units=10000)
        self.assertFalse(check_excess['is_sufficient'])
        self.assertTrue(len(check_excess['shortfalls']) > 0)

    def test_production_order_execution_and_quarantine(self):
        # 1. Create order
        order = ProductionService.create_production_order(
            recipe=self.recipe,
            planned_quantity=100,
            user=self.admin_user
        )
        self.assertEqual(order.status, 'planned')

        # 2. Kitchen run execution
        banana_before = self.mat_banana.current_stock
        updated_order, batch = ProductionService.execute_and_send_to_qc(
            production_order=order,
            produced_quantity=98,
            rejected_quantity=2,
            user=self.admin_user
        )
        self.assertEqual(updated_order.status, 'quality_check')
        self.assertEqual(batch.status, 'quarantined')
        self.assertFalse(batch.is_stock_added)

        # Verify raw material deduction
        self.mat_banana.refresh_from_db()
        self.assertTrue(self.mat_banana.current_stock < banana_before)

        # Verify finished goods NOT yet in available-to-sell inventory
        stock_item = StockItem.objects.filter(variant=self.variant).first()
        available_qty = stock_item.available_to_sell if stock_item else 0
        self.assertEqual(available_qty, 0)

    def test_quality_inspection_pass_releases_stock(self):
        order = ProductionService.create_production_order(
            recipe=self.recipe,
            planned_quantity=100,
            user=self.admin_user
        )
        updated_order, batch = ProductionService.execute_and_send_to_qc(
            production_order=order,
            produced_quantity=100,
            user=self.admin_user
        )

        # QC inspection passes
        inspection = QualityService.process_inspection(
            production_order=updated_order,
            sample_size=5,
            appearance_status='pass',
            taste_crispness_status='pass',
            moisture_status='pass',
            packaging_seal_status='pass',
            label_batch_verification='pass',
            overall_result='passed',
            inspector=self.admin_user
        )
        self.assertEqual(inspection.release_status, 'released')

        # Batch is completed and added to inventory
        batch.refresh_from_db()
        self.assertEqual(batch.status, 'completed')
        self.assertTrue(batch.is_stock_added)

        # StockItem now has 100 available to sell!
        stock_item = StockItem.objects.get(variant=self.variant)
        self.assertEqual(stock_item.available_to_sell, 100)

    def test_quality_inspection_fail_rejects_and_locks_stock(self):
        order = ProductionService.create_production_order(
            recipe=self.recipe,
            planned_quantity=100,
            user=self.admin_user
        )
        updated_order, batch = ProductionService.execute_and_send_to_qc(
            production_order=order,
            produced_quantity=100,
            user=self.admin_user
        )

        # QC inspection fails due to high moisture / burnt spots
        inspection = QualityService.process_inspection(
            production_order=updated_order,
            sample_size=5,
            appearance_status='fail',
            taste_crispness_status='marginal',
            moisture_status='fail',
            packaging_seal_status='pass',
            label_batch_verification='pass',
            overall_result='failed',
            defect_notes='Over-fried batch with burnt slices; moisture exceeds 3.5%',
            corrective_actions='Reject and discard batch; adjust fryer temperature',
            inspector=self.admin_user
        )
        self.assertEqual(inspection.release_status, 'rejected')

        batch.refresh_from_db()
        self.assertEqual(batch.status, 'recalled')
        self.assertFalse(batch.is_stock_added)

        # StockItem remains zero available
        stock_item = StockItem.objects.filter(variant=self.variant).first()
        available = stock_item.available_to_sell if stock_item else 0
        self.assertEqual(available, 0)

    def test_manufacturing_api_endpoints(self):
        # 1. Dashboard API
        resp = self.client.get('/api/manufacturing/dashboard/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('kpis', resp.data)
        self.assertIn('total_raw_materials', resp.data['kpis'])

        # 2. Raw materials list API
        resp = self.client.get('/api/manufacturing/raw-materials/')
        self.assertEqual(resp.status_code, 200)

        # 3. Recipe check availability API
        resp = self.client.get(f'/api/manufacturing/recipes/{self.recipe.id}/check_availability/?target_units=100')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['is_sufficient'])
