from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.products.models import Product, ProductVariant
from apps.manufacturing.models import (
    RawMaterialCategory,
    RawMaterial,
    Supplier,
    SupplierMaterial,
    PurchaseOrder,
    PurchaseOrderItem,
    Recipe,
    RecipeIngredient,
    RecipePackaging,
    ProductionOrder,
    ProductionMaterialConsumption,
    ProductionPackagingConsumption,
)
from apps.manufacturing.services import RawMaterialService, PurchaseService, ProductionService


class Command(BaseCommand):
    help = 'Seed realistic initial manufacturing data, raw materials, suppliers, recipes, and POs.'

    def handle(self, *args, **options):
        self.stdout.write("Seeding OnFresh manufacturing master data...")

        # 1. Categories
        categories_data = [
            ("Agricultural Ingredients", "agricultural-ingredients", "Fresh farm-sourced crops: Nendran bananas, tapioca, jackfruit from Idukki plantations"),
            ("Cooking Oils", "cooking-oils", "Expeller-pressed pure coconut oil and sunflower oil for frying"),
            ("Spices & Seasonings", "spices-seasonings", "Hill spices: Turmeric, black pepper, chilli powder, rock salt, hing"),
            ("Flours & Starches", "flours-starches", "Rice flour, besan (gram flour), roasted rice powders for murukku and mixture"),
            ("Packaging Materials", "packaging-materials", "Nitrogen-barrier printed retail pouches, cartons, sticker labels"),
            ("Manufacturing Supplies", "manufacturing-supplies", "Food-grade nitrogen cylinder refills, consumables"),
        ]

        cat_objs = {}
        for name, slug, desc in categories_data:
            cat, _ = RawMaterialCategory.objects.get_or_create(
                slug=slug,
                defaults={'name': name, 'description': desc, 'is_active': True}
            )
            cat_objs[slug] = cat

        # 2. Raw Materials
        materials_data = [
            ("RM-BAN-001", "Raw Nendran Bananas", "agricultural-ingredients", "kg", Decimal('500.000'), Decimal('120.000'), Decimal('45.00'), "Cold Store Bay 1"),
            ("RM-TAP-001", "Raw Tapioca Tubers", "agricultural-ingredients", "kg", Decimal('350.000'), Decimal('80.000'), Decimal('32.00'), "Cold Store Bay 2"),
            ("RM-OIL-001", "Pure Cold-Pressed Coconut Oil", "cooking-oils", "l", Decimal('280.000'), Decimal('60.000'), Decimal('180.00'), "Oil Storage Tank A"),
            ("RM-OIL-002", "Refined Sunflower Oil", "cooking-oils", "l", Decimal('190.000'), Decimal('50.000'), Decimal('130.00'), "Oil Storage Tank B"),
            ("RM-FLR-001", "Fine Rice Flour", "flours-starches", "kg", Decimal('180.000'), Decimal('50.000'), Decimal('42.00'), "Dry Grains Silo"),
            ("RM-FLR-002", "Gram Flour / Besan", "flours-starches", "kg", Decimal('140.000'), Decimal('40.000'), Decimal('75.00'), "Dry Grains Silo"),
            ("RM-SPC-001", "Wayanad Black Pepper (Crushed)", "spices-seasonings", "kg", Decimal('28.000'), Decimal('8.000'), Decimal('620.00'), "Spice Loft Room"),
            ("RM-SPC-002", "Kashmiri Red Chilli Powder", "spices-seasonings", "kg", Decimal('45.000'), Decimal('12.000'), Decimal('340.00'), "Spice Loft Room"),
            ("RM-SPC-003", "Pure Turmeric Powder (Curcumin 4%)", "spices-seasonings", "kg", Decimal('38.000'), Decimal('10.000'), Decimal('220.00'), "Spice Loft Room"),
            ("RM-SPC-004", "Iodized Refined Salt", "spices-seasonings", "kg", Decimal('90.000'), Decimal('25.000'), Decimal('18.00'), "Dry Store Bay 3"),
            ("RM-SPC-005", "Pure Compounded Asafoetida (Hing)", "spices-seasonings", "kg", Decimal('14.000'), Decimal('4.000'), Decimal('950.00'), "Spice Loft Room"),
            ("PKG-POUCH-250", "250g Moisture-Barrier Printed Pouch", "packaging-materials", "pcs", Decimal('2500.000'), Decimal('600.000'), Decimal('3.20'), "Packaging Loft 1"),
            ("PKG-POUCH-500", "500g Moisture-Barrier Printed Pouch", "packaging-materials", "pcs", Decimal('1800.000'), Decimal('500.000'), Decimal('4.50'), "Packaging Loft 1"),
            ("PKG-POUCH-1KG", "1kg Moisture-Barrier Printed Pouch", "packaging-materials", "pcs", Decimal('1200.000'), Decimal('300.000'), Decimal('6.80'), "Packaging Loft 2"),
            ("PKG-BOX-CRT20", "Corrugated Master Shipping Carton (20-Pack)", "packaging-materials", "pcs", Decimal('160.000'), Decimal('40.000'), Decimal('35.00'), "Carton Storage Bay"),
        ]

        mat_objs = {}
        for code, name, cat_slug, uom, stock, min_stock, cost, loc in materials_data:
            mat, created = RawMaterial.objects.get_or_create(
                material_code=code,
                defaults={
                    'name': name,
                    'category': cat_objs[cat_slug],
                    'unit_of_measure': uom,
                    'current_stock': stock,
                    'minimum_stock_level': min_stock,
                    'reorder_quantity': min_stock * 3,
                    'unit_cost': cost,
                    'storage_location': loc,
                    'is_active': True
                }
            )
            mat_objs[code] = mat

        # 3. Suppliers
        suppliers_data = [
            ("SUP-AGR-001", "Highland Farmers Consortium", "K. R. Nair", "9447101234", "highland.agro@example.com", "Main Road, Vandiperiyar", "Idukki", "32ABCPH1234A1Z1", "Net 15 days"),
            ("SUP-OIL-002", "Malabar Coconut Mills", "Suresh Menon", "9447202345", "malabar.oil@example.com", "Industrial Estate, Kozhikode", "Kozhikode", "32AABCM5678B1Z2", "Net 30 days"),
            ("SUP-SPC-003", "Kumily Cardamom & Spice Traders", "Biju George", "9447303456", "kumily.spices@example.com", "Bypass Road, Kumily", "Idukki", "32AAGCI9012C1Z3", "Cash on Delivery"),
            ("SUP-PKG-004", "Apex Flexipack Innovations", "Ravi Verma", "9447404567", "orders@apexflexi.example.com", "Kakkanad Special Economic Zone", "Ernakulam", "32AAACA3456D1Z4", "Net 30 days"),
        ]

        sup_objs = {}
        for code, name, contact, phone, email, addr, city, gstin, terms in suppliers_data:
            sup, _ = Supplier.objects.get_or_create(
                supplier_code=code,
                defaults={
                    'name': name,
                    'contact_person': contact,
                    'phone': phone,
                    'email': email,
                    'address_line1': addr,
                    'city': city,
                    'state': 'Kerala',
                    'postal_code': '685533',
                    'gstin': gstin,
                    'payment_terms': terms,
                    'is_active': True
                }
            )
            sup_objs[code] = sup

        # Link supplied materials
        SupplierMaterial.objects.get_or_create(
            supplier=sup_objs["SUP-AGR-001"],
            material=mat_objs["RM-BAN-001"],
            defaults={'quoted_price': Decimal('45.00'), 'minimum_order_qty': Decimal('100.000'), 'is_preferred': True}
        )
        SupplierMaterial.objects.get_or_create(
            supplier=sup_objs["SUP-OIL-002"],
            material=mat_objs["RM-OIL-001"],
            defaults={'quoted_price': Decimal('180.00'), 'minimum_order_qty': Decimal('50.000'), 'is_preferred': True}
        )
        SupplierMaterial.objects.get_or_create(
            supplier=sup_objs["SUP-PKG-004"],
            material=mat_objs["PKG-POUCH-250"],
            defaults={'quoted_price': Decimal('3.20'), 'minimum_order_qty': Decimal('1000.000'), 'is_preferred': True}
        )

        # 4. Master Recipes
        banana_product = Product.objects.filter(slug='kerala-banana-chips').first()
        if not banana_product:
            banana_product = Product.objects.first()

        if banana_product:
            var_250 = banana_product.variants.filter(package_weight__icontains='250').first() or banana_product.variants.first()
            recipe, _ = Recipe.objects.get_or_create(
                recipe_code="RCP-BAN-250G-V1",
                defaults={
                    'product': banana_product,
                    'variant': var_250,
                    'name': "Authentic Kerala Banana Chips 250g Batch",
                    'version': 1,
                    'is_active': True,
                    'batch_output_quantity': Decimal('50.000'),
                    'output_unit': 'packets',
                    'target_variant_units': 200,
                    'estimated_labor_cost': Decimal('600.00'),
                    'estimated_overhead_cost': Decimal('350.00'),
                    'instructions': "1. Wash and hand-peel fresh Nendran raw bananas.\n2. Slice thinly (1.2mm) directly into cold-pressed coconut oil heated to 180°C.\n3. Add turmeric-salt water solution for crispness and natural golden color.\n4. Drain on vibrating mesh conveyor and cool to room temperature.\n5. Flush with 99.9% food-grade nitrogen and heat-seal into 250g barrier pouches."
                }
            )

            # Recipe Ingredients
            RecipeIngredient.objects.get_or_create(
                recipe=recipe,
                material=mat_objs["RM-BAN-001"],
                defaults={'quantity': Decimal('65.000'), 'unit': 'kg', 'wastage_percentage': Decimal('8.00')}
            )
            RecipeIngredient.objects.get_or_create(
                recipe=recipe,
                material=mat_objs["RM-OIL-001"],
                defaults={'quantity': Decimal('16.000'), 'unit': 'l', 'wastage_percentage': Decimal('0.00')}
            )
            RecipeIngredient.objects.get_or_create(
                recipe=recipe,
                material=mat_objs["RM-SPC-003"],
                defaults={'quantity': Decimal('0.400'), 'unit': 'kg', 'wastage_percentage': Decimal('0.00')}
            )
            RecipeIngredient.objects.get_or_create(
                recipe=recipe,
                material=mat_objs["RM-SPC-004"],
                defaults={'quantity': Decimal('1.200'), 'unit': 'kg', 'wastage_percentage': Decimal('0.00')}
            )

            # Recipe Packaging
            RecipePackaging.objects.get_or_create(
                recipe=recipe,
                packaging_material=mat_objs["PKG-POUCH-250"],
                defaults={'quantity': Decimal('200.000'), 'unit': 'pcs', 'notes': '1 printed pouch per packet'}
            )
            RecipePackaging.objects.get_or_create(
                recipe=recipe,
                packaging_material=mat_objs["PKG-BOX-CRT20"],
                defaults={'quantity': Decimal('10.000'), 'unit': 'pcs', 'notes': '1 carton holds 20 pouches'}
            )

            # 5. Sample Production Order
            if not ProductionOrder.objects.filter(recipe=recipe).exists():
                order = ProductionService.create_production_order(
                    recipe=recipe,
                    planned_quantity=200,
                    start_date=timezone.localdate(),
                    notes="Daily morning batch for retail and local wholesale fulfillment."
                )
                self.stdout.write(f"Created sample production order: {order.order_number}")

        # 6. Sample Purchase Order
        if not PurchaseOrder.objects.exists():
            po = PurchaseOrder.objects.create(
                supplier=sup_objs["SUP-AGR-001"],
                order_date=timezone.localdate(),
                expected_delivery_date=timezone.localdate() + timezone.timedelta(days=2),
                status='ordered',
                notes="Weekly Nendran banana intake directly from Vandiperiyar grower."
            )
            PurchaseOrderItem.objects.create(
                purchase_order=po,
                material=mat_objs["RM-BAN-001"],
                ordered_quantity=Decimal('400.000'),
                unit_cost=Decimal('45.00'),
                tax_rate=Decimal('0.00')
            )
            po.recalculate_totals()
            self.stdout.write(f"Created sample purchase order: {po.po_number}")

        self.stdout.write(self.style.SUCCESS("OnFresh manufacturing data successfully seeded!"))

