from decimal import Decimal
from django.core.management.base import BaseCommand
from apps.products.models import Category, Product, ProductVariant, QuantityPriceTier


class Command(BaseCommand):
    help = 'Load demonstration categories, products, and package variants for OnFresh wholesale catalogue (Illustrative data).'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Loading demonstration wholesale products for OnFresh..."))
        self.stdout.write(self.style.NOTICE("Note: All prices are illustrative demonstration examples for development only.\n"))

        categories_data = [
            {
                'name': 'Banana Chips',
                'slug': 'banana-chips',
                'description': 'Crispy golden chips sliced from prime Kerala Nendran raw bananas, fried in pure vegetable oil.',
            },
            {
                'name': 'Traditional Snacks',
                'slug': 'traditional-snacks',
                'description': 'Authentic tea-time snacks prepared according to traditional Kerala recipes (Murukku, Pakkoda).',
            },
            {
                'name': 'Mixture & Savouries',
                'slug': 'mixture-savouries',
                'description': 'Crunchy sev, roasted peanuts, fried curry leaves, and aromatic Kerala spices.',
            },
            {
                'name': 'Biscuits & Cookies',
                'slug': 'biscuits-cookies',
                'description': 'Freshly baked melt-in-mouth bakery butter cookies and tea accompaniments.',
            },
            {
                'name': 'Bakery Products',
                'slug': 'bakery-products',
                'description': 'Crisp double-baked cardamom rusks and tea counter specialities.',
            },
            {
                'name': 'Kerala Specialties',
                'slug': 'kerala-specialties',
                'description': 'Sun-dried cassava (tapioca/kappa) chips and sweet-savoury jackfruit (chakka varuthathu) slices.',
            },
        ]

        created_categories = {}
        for cat_info in categories_data:
            cat, created = Category.objects.get_or_create(
                slug=cat_info['slug'],
                defaults={
                    'name': cat_info['name'],
                    'description': cat_info['description'],
                    'is_active': True,
                }
            )
            created_categories[cat.slug] = cat
            status = "Created" if created else "Existing"
            self.stdout.write(f"Category [{status}]: {cat.name}")

        products_data = [
            {
                'name': 'Kerala Nendran Banana Chips',
                'slug': 'kerala-nendran-banana-chips',
                'category': created_categories['banana-chips'],
                'short_description': 'Thinly sliced golden Nendran raw plantains with turmeric and rock salt.',
                'description': 'Signature wholesale banana chips made from farm-harvested green Nendran plantains. Thinly sliced, fried to a light golden crisp in refined vegetable oil, and sealed immediately in high-barrier airtight wholesale pouches.',
                'ingredients': 'Raw Nendran Plantains, Refined Vegetable Oil, Turmeric, Rock Salt',
                'shelf_life': '90 Days',
                'is_featured': True,
                'variants': [
                    {'sku': 'ONF-BC-250', 'weight': Decimal('250.00'), 'unit': 'g', 'price': Decimal('80.00'), 'moq': 10},
                    {'sku': 'ONF-BC-500', 'weight': Decimal('500.00'), 'unit': 'g', 'price': Decimal('155.00'), 'moq': 10},
                    {'sku': 'ONF-BC-1000', 'weight': Decimal('1.00'), 'unit': 'kg', 'price': Decimal('300.00'), 'moq': 5},
                ]
            },
            {
                'name': 'Spicy Pepper Banana Chips',
                'slug': 'spicy-pepper-banana-chips',
                'category': created_categories['banana-chips'],
                'short_description': 'Crunchy Nendran banana chips seasoned with crushed black Malabar pepper.',
                'description': 'Zesty twist on the classic Kerala banana chip. Coated with freshly ground Malabar black pepper and a pinch of salt.',
                'ingredients': 'Nendran Plantains, Refined Vegetable Oil, Malabar Black Pepper, Salt',
                'shelf_life': '90 Days',
                'is_featured': False,
                'variants': [
                    {'sku': 'ONF-PBC-250', 'weight': Decimal('250.00'), 'unit': 'g', 'price': Decimal('85.00'), 'moq': 10},
                    {'sku': 'ONF-PBC-500', 'weight': Decimal('500.00'), 'unit': 'g', 'price': Decimal('165.00'), 'moq': 10},
                    {'sku': 'ONF-PBC-1000', 'weight': Decimal('1.00'), 'unit': 'kg', 'price': Decimal('320.00'), 'moq': 5},
                ]
            },
            {
                'name': 'Spicy Tapioca Chips (Kappa Chips)',
                'slug': 'spicy-tapioca-chips',
                'category': created_categories['kerala-specialties'],
                'short_description': 'Crispy hand-sliced cassava chips tossed with fiery red chilli powder and salt.',
                'description': 'Farm-fresh tapioca roots thinly sliced and crisped to golden perfection, coated with a balance of Kerala red chilli and rock salt. Highly popular snack in local bakeries and supermarkets.',
                'ingredients': 'Fresh Tapioca Root, Refined Vegetable Oil, Red Chilli Powder, Rock Salt',
                'shelf_life': '90 Days',
                'is_featured': True,
                'variants': [
                    {'sku': 'ONF-KC-250', 'weight': Decimal('250.00'), 'unit': 'g', 'price': Decimal('70.00'), 'moq': 10},
                    {'sku': 'ONF-KC-500', 'weight': Decimal('500.00'), 'unit': 'g', 'price': Decimal('135.00'), 'moq': 10},
                    {'sku': 'ONF-KC-1000', 'weight': Decimal('1.00'), 'unit': 'kg', 'price': Decimal('260.00'), 'moq': 5},
                ]
            },
            {
                'name': 'Jackfruit Chips (Chakka Varuthathu)',
                'slug': 'jackfruit-chips',
                'category': created_categories['kerala-specialties'],
                'short_description': 'Seasonal delicacy made from crispy deep-fried raw jackfruit bulb strips.',
                'description': 'Authentic Kerala chakka chips sliced from mature raw jackfruit pods. Sweet, aromatic, and extremely crunchy.',
                'ingredients': 'Raw Jackfruit Pods, Refined Vegetable Oil, Salt',
                'shelf_life': '60 Days',
                'is_featured': True,
                'variants': [
                    {'sku': 'ONF-JC-250', 'weight': Decimal('250.00'), 'unit': 'g', 'price': Decimal('95.00'), 'moq': 10},
                    {'sku': 'ONF-JC-500', 'weight': Decimal('500.00'), 'unit': 'g', 'price': Decimal('185.00'), 'moq': 10},
                    {'sku': 'ONF-JC-1000', 'weight': Decimal('1.00'), 'unit': 'kg', 'price': Decimal('360.00'), 'moq': 5},
                ]
            },
            {
                'name': 'Traditional Ribbon Murukku',
                'slug': 'traditional-ribbon-murukku',
                'category': created_categories['traditional-snacks'],
                'short_description': 'Crispy ribbon spirals seasoned with crushed cumin, white sesame, and asafoetida.',
                'description': 'Authentic rice flour and urad dal ribbon murukku, seasoned with crushed cumin and sesame. Light on oil, perfectly crunchy, and ideal for retail tea shops and bakery counters.',
                'ingredients': 'Rice Flour, Urad Dal Flour, Sesame Seeds, Cumin Seeds, Asafoetida, Vegetable Oil, Salt',
                'shelf_life': '60 Days',
                'is_featured': True,
                'variants': [
                    {'sku': 'ONF-MK-250', 'weight': Decimal('250.00'), 'unit': 'g', 'price': Decimal('65.00'), 'moq': 10},
                    {'sku': 'ONF-MK-500', 'weight': Decimal('500.00'), 'unit': 'g', 'price': Decimal('125.00'), 'moq': 10},
                    {'sku': 'ONF-MK-1000', 'weight': Decimal('1.00'), 'unit': 'kg', 'price': Decimal('240.00'), 'moq': 5},
                ]
            },
            {
                'name': 'Crispy Onion Pakkoda',
                'slug': 'crispy-onion-pakkoda',
                'category': created_categories['traditional-snacks'],
                'short_description': 'Golden crunchy savoury fritters spiced with fennel seeds and fried curry leaves.',
                'description': 'Deep-fried golden savoury bites with a crunchy bite, spiced with cumin, fennel, and dried chillies. Rapid seller in grocery stores and supermarket snack sections.',
                'ingredients': 'Gram Flour, Rice Flour, Onion Extracts, Curry Leaves, Fennel, Chilli, Salt',
                'shelf_life': '60 Days',
                'is_featured': True,
                'variants': [
                    {'sku': 'ONF-PK-250', 'weight': Decimal('250.00'), 'unit': 'g', 'price': Decimal('70.00'), 'moq': 10},
                    {'sku': 'ONF-PK-500', 'weight': Decimal('500.00'), 'unit': 'g', 'price': Decimal('135.00'), 'moq': 10},
                    {'sku': 'ONF-PK-1000', 'weight': Decimal('1.00'), 'unit': 'kg', 'price': Decimal('260.00'), 'moq': 5},
                ]
            },
            {
                'name': 'Special Spicy Kerala Mixture',
                'slug': 'special-spicy-kerala-mixture',
                'category': created_categories['mixture-savouries'],
                'short_description': 'Signature blend of gram flour sev, boondi, roasted peanuts, and fried curry leaves.',
                'description': 'A classic Kerala staple. Crunchy sev, puffed boondi, fried split gram, roasted peanuts, and fragrant curry leaves tossed in a secret spice blend.',
                'ingredients': 'Besan (Gram Flour), Rice Flour, Peanuts, Curry Leaves, Garlic, Chilli Powder, Salt',
                'shelf_life': '75 Days',
                'is_featured': True,
                'variants': [
                    {'sku': 'ONF-MX-250', 'weight': Decimal('250.00'), 'unit': 'g', 'price': Decimal('75.00'), 'moq': 10},
                    {'sku': 'ONF-MX-500', 'weight': Decimal('500.00'), 'unit': 'g', 'price': Decimal('145.00'), 'moq': 10},
                    {'sku': 'ONF-MX-1000', 'weight': Decimal('1.00'), 'unit': 'kg', 'price': Decimal('280.00'), 'moq': 5},
                ]
            },
            {
                'name': 'Crispy Cardamom Tea Rusk',
                'slug': 'crispy-cardamom-tea-rusk',
                'category': created_categories['bakery-products'],
                'short_description': 'Double-baked crunchy wheat rusk infused with fragrant green Idukki cardamom.',
                'description': 'Slow-baked with natural Idukki cardamom, making it the supreme accompaniment for morning and evening chai in bakeries and tea stalls.',
                'ingredients': 'Wheat Flour, Sugar, Vegetable Fat, Idukki Green Cardamom, Yeast, Milk Solids',
                'shelf_life': '120 Days',
                'is_featured': True,
                'variants': [
                    {'sku': 'ONF-RK-400', 'weight': Decimal('400.00'), 'unit': 'g', 'price': Decimal('60.00'), 'moq': 12},
                    {'sku': 'ONF-RK-800', 'weight': Decimal('800.00'), 'unit': 'g', 'price': Decimal('115.00'), 'moq': 8},
                ]
            },
            {
                'name': 'Bakery Butter Cookies',
                'slug': 'bakery-butter-cookies',
                'category': created_categories['biscuits-cookies'],
                'short_description': 'Rich melt-in-mouth butter cookies baked with a light vanilla note.',
                'description': 'Golden baked bakery cookies prepared with pure dairy butter and wholesome flour. Popular counter item in tea stalls and bakeries.',
                'ingredients': 'Wheat Flour, Pure Butter, Sugar, Milk Solids, Vanilla Extract',
                'shelf_life': '90 Days',
                'is_featured': False,
                'variants': [
                    {'sku': 'ONF-BCK-250', 'weight': Decimal('250.00'), 'unit': 'g', 'price': Decimal('85.00'), 'moq': 10},
                    {'sku': 'ONF-BCK-500', 'weight': Decimal('500.00'), 'unit': 'g', 'price': Decimal('165.00'), 'moq': 10},
                ]
            },
        ]

        total_variants_created = 0
        for prod_info in products_data:
            variants_list = prod_info.pop('variants')
            product, created = Product.objects.get_or_create(
                slug=prod_info['slug'],
                defaults=prod_info
            )
            status = "Created" if created else "Existing"
            self.stdout.write(f"  Product [{status}]: {product.name} ({product.category.name})")

            for v in variants_list:
                ws_price = round(v['price'] * Decimal('0.80'), 2)
                variant, v_created = ProductVariant.objects.get_or_create(
                    sku=v['sku'],
                    defaults={
                        'product': product,
                        'package_weight': v['weight'],
                        'package_unit': v['unit'],
                        'price': v['price'],
                        'wholesale_price': ws_price,
                        'minimum_order_quantity': v['moq'],
                        'is_available': True,
                        'is_available_retail': True,
                        'is_available_wholesale': True,
                    }
                )
                if not v_created:
                    # Update existing variant with wholesale fields
                    variant.wholesale_price = ws_price
                    variant.is_available_retail = True
                    variant.is_available_wholesale = True
                    variant.save()
                else:
                    total_variants_created += 1

                # Add sample volume price tiers for wholesale buyers
                tier_1_qty = 50
                tier_1_price = round(ws_price * Decimal('0.93'), 2)  # ~7% extra discount
                QuantityPriceTier.objects.get_or_create(
                    variant=variant,
                    min_quantity=tier_1_qty,
                    defaults={'price_per_unit': tier_1_price}
                )

                tier_2_qty = 100
                tier_2_price = round(ws_price * Decimal('0.88'), 2)  # ~12% extra discount
                QuantityPriceTier.objects.get_or_create(
                    variant=variant,
                    min_quantity=tier_2_qty,
                    defaults={'price_per_unit': tier_2_price}
                )

                # Initialize inventory & sample production batch
                from apps.inventory.services import InventoryService
                from apps.inventory.models import StockItem, ProductionBatch
                from django.utils import timezone

                stock = StockItem.objects.get_or_create(
                    variant=variant,
                    defaults={
                        'quantity_on_hand': 150,
                        'reserved_quantity': 0,
                        'low_stock_threshold': 20,
                    }
                )[0]

                if not ProductionBatch.objects.filter(variant=variant).exists():
                    today = timezone.localdate()
                    exp_date = today + timezone.timedelta(days=90)
                    batch = ProductionBatch.objects.create(
                        product=product,
                        variant=variant,
                        production_date=today - timezone.timedelta(days=5),
                        expiry_date=exp_date,
                        manufactured_quantity=200,
                        remaining_quantity=150,
                        status='completed',
                        is_stock_added=True,
                        manufacturing_notes='Fresh production batch from Vandiperiyar kitchen facility.'
                    )

        self.stdout.write(self.style.SUCCESS(
            f"\nDemonstration catalogue loaded successfully! (6 Categories, 9 Products, {total_variants_created} new variants created)"
        ))
