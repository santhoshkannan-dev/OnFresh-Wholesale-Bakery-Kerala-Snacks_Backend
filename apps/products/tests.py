from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from .models import Category, Product, ProductVariant, QuantityPriceTier, CustomerSpecialPrice
from apps.customers.models import CustomerProfile

User = get_user_model()


class ProductModelTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name='Kerala Chips',
            slug='kerala-chips',
            description='Authentic Kerala chips',
            is_active=True
        )

    def test_category_creation_and_str(self):
        self.assertEqual(str(self.category), 'Kerala Chips')
        self.assertEqual(self.category.slug, 'kerala-chips')

    def test_product_creation_and_variant(self):
        product = Product.objects.create(
            name='Banana Chips Classic',
            slug='banana-chips-classic',
            category=self.category,
            short_description='Thin crispy chips',
            is_active=True
        )
        variant = ProductVariant.objects.create(
            product=product,
            sku='ONF-TEST-250',
            package_weight=Decimal('250.00'),
            package_unit='g',
            price=Decimal('80.00'),
            minimum_order_quantity=10,
            is_available=True
        )
        self.assertEqual(product.min_price, Decimal('80.00'))
        self.assertEqual(variant.display_weight, '250 g')
        self.assertEqual(product.available_variants.count(), 1)

    def test_inactive_category_validation(self):
        inactive_cat = Category.objects.create(
            name='Old Snacks',
            slug='old-snacks',
            is_active=False
        )
        product = Product(
            name='Old Banana Chips',
            slug='old-banana-chips',
            category=inactive_cat,
            is_active=True
        )
        with self.assertRaises(ValidationError):
            product.clean()

    def test_price_must_be_positive(self):
        product = Product.objects.create(
            name='Salted Murukku',
            slug='salted-murukku',
            category=self.category
        )
        variant = ProductVariant(
            product=product,
            sku='ONF-ZERO-PRICE',
            package_weight=Decimal('250.00'),
            package_unit='g',
            price=Decimal('0.00'),
            minimum_order_quantity=10
        )
        with self.assertRaises(ValidationError):
            variant.clean()

    def test_weight_must_be_positive(self):
        product = Product.objects.create(
            name='Spicy Mixture',
            slug='spicy-mixture-test',
            category=self.category
        )
        variant = ProductVariant(
            product=product,
            sku='ONF-ZERO-WEIGHT',
            package_weight=Decimal('-10.00'),
            package_unit='g',
            price=Decimal('50.00'),
            minimum_order_quantity=5
        )
        with self.assertRaises(ValidationError):
            variant.clean()


class ProductAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin_user = User.objects.create_superuser(
            username='admin_test',
            email='admin@onfresh.test',
            password='testpassword123'
        )
        self.cat_active = Category.objects.create(
            name='Active Category',
            slug='active-cat',
            is_active=True
        )
        self.cat_inactive = Category.objects.create(
            name='Inactive Category',
            slug='inactive-cat',
            is_active=False
        )

        # Active product in active category
        self.prod_active = Product.objects.create(
            name='Active Banana Chips',
            slug='active-banana-chips',
            category=self.cat_active,
            short_description='Delicious chips',
            is_active=True,
            is_featured=True
        )
        ProductVariant.objects.create(
            product=self.prod_active,
            sku='ONF-ACT-250',
            package_weight=Decimal('250.00'),
            package_unit='g',
            price=Decimal('75.00'),
            minimum_order_quantity=10,
            is_available=True
        )

        # Inactive product
        self.prod_inactive = Product.objects.create(
            name='Hidden Banana Chips',
            slug='hidden-banana-chips',
            category=self.cat_active,
            is_active=False
        )

    def test_public_can_only_see_active_categories(self):
        res = self.client.get('/api/categories/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        slugs = [c['slug'] for c in res.data['results'] if 'slug' in c] if 'results' in res.data else [c['slug'] for c in res.data]
        self.assertIn('active-cat', slugs)
        self.assertNotIn('inactive-cat', slugs)

    def test_public_can_only_see_active_products(self):
        res = self.client.get('/api/products/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data['results'] if 'results' in res.data else res.data
        slugs = [p['slug'] for p in results]
        self.assertIn('active-banana-chips', slugs)
        self.assertNotIn('hidden-banana-chips', slugs)

    def test_filter_by_category(self):
        res = self.client.get('/api/products/?category=active-cat')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data['results'] if 'results' in res.data else res.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['slug'], 'active-banana-chips')

    def test_filter_by_featured(self):
        res = self.client.get('/api/products/?is_featured=true')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data['results'] if 'results' in res.data else res.data
        self.assertTrue(all(p['is_featured'] for p in results))

    def test_search_products(self):
        res = self.client.get('/api/products/?search=Banana')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data['results'] if 'results' in res.data else res.data
        self.assertEqual(len(results), 1)

    def test_product_detail_endpoint(self):
        res = self.client.get('/api/products/active-banana-chips/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['name'], 'Active Banana Chips')
        self.assertIn('variants', res.data)
        self.assertEqual(len(res.data['variants']), 1)

    def test_unauthorized_user_cannot_create_product(self):
        res = self.client.post('/api/products/', {
            'name': 'Unauthorized Product',
            'slug': 'unauth-prod',
            'category': self.cat_active.id,
        })
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_user_can_create_product(self):
        self.client.force_authenticate(user=self.admin_user)
        res = self.client.post('/api/products/', {
            'name': 'Admin Created Product',
            'slug': 'admin-created-product',
            'category': self.cat_active.id,
            'short_description': 'Created by admin',
            'is_active': True,
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Product.objects.filter(slug='admin-created-product').count(), 1)

    def test_b2c_and_b2b_pricing_calculations(self):
        # Create wholesale variant with retail price 100, base wholesale 80
        prod = Product.objects.create(
            name='Test Banana Chips',
            slug='test-banana-chips',
            category=self.cat_active,
            is_active=True
        )
        variant = ProductVariant.objects.create(
            product=prod,
            sku='ONF-TEST-TIER-500',
            package_weight=Decimal('500.00'),
            package_unit='g',
            price=Decimal('100.00'),
            wholesale_price=Decimal('80.00'),
            minimum_order_quantity=10,
            is_available=True
        )
        # Add tier for 50+ units @ 75
        QuantityPriceTier.objects.create(
            variant=variant,
            min_quantity=50,
            price_per_unit=Decimal('75.00')
        )

        # 1. Individual retail user (B2C)
        retail_user = User.objects.create_user(
            username='retail_buyer@onfresh.test',
            email='retail_buyer@onfresh.test',
            password='Password123!'
        )
        retail_profile = CustomerProfile.objects.create(
            user=retail_user,
            customer_type='individual',
            wholesale_status='none',
            phone_number='9846000001'
        )

        # Retail customer ordering 10 units -> gets retail price 100
        self.assertEqual(variant.get_effective_price(retail_profile, quantity=10), Decimal('100.00'))
        self.assertEqual(variant.get_moq_for_customer(retail_profile), 1)

        # 2. Business user pending approval -> still receives retail price 100
        pending_user = User.objects.create_user(
            username='pending_biz@onfresh.test',
            email='pending_biz@onfresh.test',
            password='Password123!'
        )
        pending_profile = CustomerProfile.objects.create(
            user=pending_user,
            customer_type='business',
            wholesale_status='pending',
            business_name='Pending Tea Shop',
            phone_number='9846000002'
        )
        self.assertEqual(variant.get_effective_price(pending_profile, quantity=10), Decimal('100.00'))

        # 3. Approved wholesale business user -> receives base wholesale price 80 for 10 units
        approved_user = User.objects.create_user(
            username='approved_biz@onfresh.test',
            email='approved_biz@onfresh.test',
            password='Password123!'
        )
        approved_profile = CustomerProfile.objects.create(
            user=approved_user,
            customer_type='business',
            wholesale_status='approved',
            business_name='Approved Supermarket',
            phone_number='9846000003'
        )
        self.assertEqual(variant.get_effective_price(approved_profile, quantity=10), Decimal('80.00'))
        self.assertEqual(variant.get_moq_for_customer(approved_profile), 10)

        # 4. Approved wholesale customer ordering 60 units -> triggers quantity tier @ 75
        self.assertEqual(variant.get_effective_price(approved_profile, quantity=60), Decimal('75.00'))

        # 5. Customer with negotiated special price @ 70
        CustomerSpecialPrice.objects.create(
            customer=approved_profile,
            variant=variant,
            special_price=Decimal('70.00'),
            is_active=True
        )
        self.assertEqual(variant.get_effective_price(approved_profile, quantity=10), Decimal('70.00'))

    def test_authoritative_calculate_pricing_endpoint(self):
        prod = Product.objects.create(
            name='Chips Box',
            slug='chips-box',
            category=self.cat_active,
            is_active=True
        )
        variant = ProductVariant.objects.create(
            product=prod,
            sku='ONF-BOX-1000',
            package_weight=Decimal('1.00'),
            package_unit='kg',
            price=Decimal('250.00'),
            wholesale_price=Decimal('200.00'),
            minimum_order_quantity=5,
            is_available=True
        )
        QuantityPriceTier.objects.create(
            variant=variant,
            min_quantity=50,
            price_per_unit=Decimal('185.00')
        )

        client = APIClient()

        # Retail anonymous user ordering 2 units
        res = client.post('/api/products/calculate-pricing/', {
            'items': [{'variant_id': variant.id, 'quantity': 2}]
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['customer_segment'], 'retail')
        self.assertEqual(res.data['items'][0]['effective_unit_price'], 250.00)
        self.assertEqual(res.data['items'][0]['line_total'], 500.00)
        self.assertEqual(res.data['subtotal'], 500.00)
        self.assertTrue(res.data['all_moq_met'])

        # Approved wholesale user
        ws_user = User.objects.create_user(
            username='ws@keralastore.com',
            email='ws@keralastore.com',
            password='Password123!'
        )
        CustomerProfile.objects.create(
            user=ws_user,
            customer_type='business',
            wholesale_status='approved',
            business_name='Kerala Store Idukki',
            phone_number='9846000004'
        )
        client.force_authenticate(user=ws_user)

        # 1. Wholesale user below MOQ (qty 3 < MOQ 5)
        res_below_moq = client.post('/api/products/calculate-pricing/', {
            'items': [{'variant_id': variant.id, 'quantity': 3}]
        }, format='json')
        self.assertEqual(res_below_moq.status_code, status.HTTP_200_OK)
        self.assertEqual(res_below_moq.data['customer_segment'], 'wholesale')
        self.assertFalse(res_below_moq.data['all_moq_met'])
        self.assertGreater(len(res_below_moq.data['warnings']), 0)

        # 2. Wholesale user meeting volume tier (qty 50)
        res_tier = client.post('/api/products/calculate-pricing/', {
            'items': [{'variant_id': variant.id, 'quantity': 50}]
        }, format='json')
        self.assertEqual(res_tier.status_code, status.HTTP_200_OK)
        self.assertEqual(res_tier.data['customer_segment'], 'wholesale')
        self.assertTrue(res_tier.data['all_moq_met'])
        self.assertEqual(res_tier.data['items'][0]['effective_unit_price'], 185.00)
        self.assertEqual(res_tier.data['items'][0]['line_total'], 9250.00)
        self.assertEqual(res_tier.data['subtotal'], 9250.00)
