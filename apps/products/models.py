from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.utils.text import slugify


class Category(models.Model):
    """
    Product Category model for wholesale bakery & Kerala snacks.
    """
    name = models.CharField(max_length=150, unique=True, db_index=True)
    slug = models.SlugField(max_length=160, unique=True, db_index=True)
    description = models.TextField(blank=True, default='')
    image = models.ImageField(upload_to='categories/', blank=True, null=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Category'
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def active_product_count(self):
        return self.products.filter(is_active=True).count()


class Product(models.Model):
    """
    Core Product entity representing a snack or bakery item.
    Packaging sizes & specific wholesale prices are modeled via ProductVariant.
    """
    name = models.CharField(max_length=200, db_index=True)
    slug = models.SlugField(max_length=220, unique=True, db_index=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='products',
        help_text="Category cannot be deleted while products reference it."
    )
    short_description = models.CharField(max_length=300, blank=True, default='')
    description = models.TextField(blank=True, default='')
    main_image = models.ImageField(upload_to='products/', blank=True, null=True)
    ingredients = models.TextField(
        blank=True,
        default='',
        help_text="Comma-separated list of ingredients"
    )
    shelf_life = models.CharField(max_length=100, blank=True, default='90 Days')
    is_active = models.BooleanField(default=True, db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        # Enforce requirement: Active product cannot be assigned to an inactive category
        if self.is_active and self.category and not self.category.is_active:
            raise ValidationError({
                'category': 'Cannot assign an active product to an inactive category.'
            })

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def available_variants(self):
        return self.variants.filter(is_available=True).order_by('package_weight')

    @property
    def min_price(self):
        first = self.available_variants.order_by('price').first()
        return first.price if first else None

    @property
    def max_price(self):
        last = self.available_variants.order_by('price').last()
        return last.price if last else None

    @property
    def min_wholesale_price(self):
        first = self.available_variants.exclude(wholesale_price__isnull=True).order_by('wholesale_price').first()
        if first and first.wholesale_price is not None:
            return first.wholesale_price
        return self.min_price

    @property
    def max_wholesale_price(self):
        last = self.available_variants.exclude(wholesale_price__isnull=True).order_by('wholesale_price').last()
        if last and last.wholesale_price is not None:
            return last.wholesale_price
        return self.max_price


class ProductVariant(models.Model):
    """
    Product Variant model representing specific packaging sizes (e.g. 250g, 500g, 1kg),
    SKU, retail price, wholesale price in INR, and minimum order quantity (MOQ).
    """
    PACKAGE_UNIT_CHOICES = (
        ('g', 'Grams (g)'),
        ('kg', 'Kilograms (kg)'),
        ('pkt', 'Packet'),
        ('box', 'Bulk Box'),
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='variants'
    )
    sku = models.CharField(max_length=60, unique=True, db_index=True)
    package_weight = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Weight or volume quantity (e.g. 250, 500, 1)"
    )
    package_unit = models.CharField(
        max_length=20,
        choices=PACKAGE_UNIT_CHOICES,
        default='g'
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Standard retail price in INR (₹) per package for B2C individual customers"
    )
    wholesale_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Base wholesale price in INR (₹) per package for approved B2B customers. Defaults to retail price if blank."
    )
    minimum_order_quantity = models.PositiveIntegerField(
        default=10,
        validators=[MinValueValidator(1)],
        help_text="Minimum wholesale quantity required per order for B2B customers"
    )
    is_available = models.BooleanField(default=True, db_index=True)
    is_available_retail = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Available for individual retail (B2C) customers"
    )
    is_available_wholesale = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Available for approved wholesale business (B2B) customers"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Product Variant'
        verbose_name_plural = 'Product Variants'
        unique_together = ('product', 'package_weight', 'package_unit')
        ordering = ['package_weight']

    def __str__(self):
        return f"{self.product.name} - {self.display_weight} (SKU: {self.sku})"

    @property
    def display_weight(self):
        # Format integer weights without unnecessary decimal zeroes (e.g. 250 g instead of 250.00 g)
        if self.package_weight == int(self.package_weight):
            weight_str = str(int(self.package_weight))
        else:
            weight_str = f"{self.package_weight:.2f}".rstrip('0').rstrip('.')
        return f"{weight_str} {self.package_unit}"

    @property
    def retail_price(self):
        return self.price

    @property
    def effective_wholesale_price(self):
        return self.wholesale_price if self.wholesale_price is not None else self.price

    def get_effective_price(self, customer_profile=None, quantity=1):
        """
        Authoritative calculation of unit price based on customer segment,
        wholesale approval status, custom negotiated pricing, and volume tiers.
        """
        # Approved wholesale customer flow
        if customer_profile and customer_profile.is_wholesale_approved:
            # 1. Custom agreed price for this customer
            special = self.customer_special_prices.filter(customer=customer_profile, is_active=True).first()
            if special:
                return special.special_price

            # 2. Volume-based quantity tiers
            tier = self.price_tiers.filter(min_quantity__lte=quantity).order_by('-min_quantity').first()
            if tier:
                return tier.price_per_unit

            # 3. Base wholesale price
            return self.effective_wholesale_price

        # Standard B2C retail flow (individual, guest, or unapproved business)
        return self.price

    def get_moq_for_customer(self, customer_profile=None):
        if customer_profile and customer_profile.is_wholesale_approved:
            return self.minimum_order_quantity
        return 1

    def is_available_for_customer(self, customer_profile=None):
        if not self.is_available:
            return False
        if customer_profile and customer_profile.is_wholesale_approved:
            return self.is_available_wholesale
        return self.is_available_retail

    def clean(self):
        super().clean()
        if self.price is not None and self.price <= Decimal('0.00'):
            raise ValidationError({'price': 'Retail price must be greater than zero.'})
        if self.wholesale_price is not None and self.wholesale_price <= Decimal('0.00'):
            raise ValidationError({'wholesale_price': 'Wholesale price must be greater than zero.'})
        if self.package_weight is not None and self.package_weight <= Decimal('0.00'):
            raise ValidationError({'package_weight': 'Package weight must be greater than zero.'})
        if self.minimum_order_quantity is not None and self.minimum_order_quantity < 1:
            raise ValidationError({'minimum_order_quantity': 'Minimum order quantity must be at least 1.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class QuantityPriceTier(models.Model):
    """
    Volume-based wholesale price tiers for bulk purchasers.
    Example: For 500g Banana Chips:
      - Qty 10-49: ₹125/pack (base wholesale)
      - Qty 50-99: ₹115/pack (Tier 1 bulk discount)
      - Qty 100+:  ₹105/pack (Tier 2 super-bulk discount)
    """
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name='price_tiers'
    )
    min_quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Minimum quantity threshold for this price tier"
    )
    price_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Discounted price per unit for orders meeting or exceeding min_quantity"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Quantity Price Tier'
        verbose_name_plural = 'Quantity Price Tiers'
        ordering = ['min_quantity']
        unique_together = ('variant', 'min_quantity')

    def __str__(self):
        return f"{self.variant.sku} - Qty {self.min_quantity}+ @ ₹{self.price_per_unit}"

    def clean(self):
        super().clean()
        if self.price_per_unit is not None and self.price_per_unit <= Decimal('0.00'):
            raise ValidationError({'price_per_unit': 'Tier price must be greater than zero.'})


class CustomerSpecialPrice(models.Model):
    """
    Custom negotiated pricing agreed with a specific approved business customer
    for a product variant.
    """
    customer = models.ForeignKey(
        'customers.CustomerProfile',
        on_delete=models.CASCADE,
        related_name='special_prices'
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name='customer_special_prices'
    )
    special_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Custom agreed price in INR (₹) for this customer"
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Customer Special Price'
        verbose_name_plural = 'Customer Special Prices'
        unique_together = ('customer', 'variant')

    def __str__(self):
        return f"{self.customer.business_name or self.customer.user.email} - {self.variant.sku} @ ₹{self.special_price}"

    def clean(self):
        super().clean()
        if self.special_price is not None and self.special_price <= Decimal('0.00'):
            raise ValidationError({'special_price': 'Special price must be greater than zero.'})
