import secrets
import string
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone


def generate_order_number():
    """
    Generate human-readable, unique order number with date prefix.
    Example: ONF-20261104-7K9A2
    """
    date_str = timezone.now().strftime('%Y%m%d')
    alphabet = string.ascii_uppercase + string.digits
    suffix = ''.join(secrets.choice(alphabet) for _ in range(5))
    return f"ONF-{date_str}-{suffix}"


class Cart(models.Model):
    """
    Unified shopping cart associated with an authenticated customer.
    Supports both B2C (retail) and B2B (wholesale) customer profiles.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cart'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cart'
        verbose_name_plural = 'Carts'

    def __str__(self):
        return f"Cart ({self.user.email})"

    @property
    def total_items_count(self):
        return sum(item.quantity for item in self.items.all())

    def clear(self):
        self.items.all().delete()


class CartItem(models.Model):
    """
    Individual product variant in a customer's cart.
    Enforces unique constraint so the same variant cannot have duplicate rows.
    """
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name='items'
    )
    variant = models.ForeignKey(
        'products.ProductVariant',
        on_delete=models.CASCADE,
        related_name='cart_items'
    )
    quantity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Number of packages of this variant"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cart Item'
        verbose_name_plural = 'Cart Items'
        unique_together = ('cart', 'variant')
        ordering = ['created_at']

    def __str__(self):
        return f"{self.variant.product.name} ({self.variant.display_weight}) x {self.quantity}"

    def clean(self):
        super().clean()
        if self.quantity < 1:
            raise ValidationError({'quantity': 'Quantity must be at least 1.'})


class Order(models.Model):
    """
    Unified Order entity supporting both Retail (B2C) and Wholesale (B2B) orders.
    Stores immutable snapshots of customer profile type, addresses, and pricing rules.
    """
    ORDER_STATUS_CHOICES = (
        ('pending', 'Pending Confirmation'),
        ('confirmed', 'Confirmed'),
        ('processing', 'Processing / In Production'),
        ('ready_for_dispatch', 'Ready for Dispatch'),
        ('dispatched', 'Dispatched / In Transit'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    )

    PAYMENT_STATUS_CHOICES = (
        ('pending', 'Pending Payment'),
        ('partially_paid', 'Partially Paid'),
        ('paid', 'Paid'),
        ('failed', 'Payment Failed'),
        ('refunded', 'Refunded'),
    )

    PAYMENT_METHOD_CHOICES = (
        ('cod', 'Cash on Delivery (COD)'),
        ('bank_transfer', 'Direct Bank Transfer (NEFT/RTGS)'),
        ('online', 'Online Payment Gateway'),
    )

    CUSTOMER_TYPE_CHOICES = (
        ('individual', 'Individual (Retail Customer)'),
        ('business', 'Business (Wholesale Customer)'),
    )

    # Allowed forward status transitions
    VALID_STATUS_TRANSITIONS = {
        'pending': ['confirmed', 'cancelled'],
        'confirmed': ['processing', 'cancelled'],
        'processing': ['ready_for_dispatch', 'cancelled'],
        'ready_for_dispatch': ['dispatched', 'cancelled'],
        'dispatched': ['delivered'],
        'delivered': [],
        'cancelled': [],
    }

    order_number = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        editable=False,
        default=generate_order_number
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='orders'
    )
    customer_profile = models.ForeignKey(
        'customers.CustomerProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders'
    )
    customer_type = models.CharField(
        max_length=20,
        choices=CUSTOMER_TYPE_CHOICES,
        default='individual',
        db_index=True,
        help_text="Customer segment snapshot at order time"
    )
    order_status = models.CharField(
        max_length=30,
        choices=ORDER_STATUS_CHOICES,
        default='pending',
        db_index=True
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='pending',
        db_index=True
    )
    payment_method = models.CharField(
        max_length=30,
        choices=PAYMENT_METHOD_CHOICES,
        default='cod'
    )

    # Immutable address snapshots captured during checkout
    shipping_address_snapshot = models.JSONField(
        default=dict,
        help_text="Immutable snapshot of shipping address at order time"
    )
    billing_address_snapshot = models.JSONField(
        default=dict,
        help_text="Immutable snapshot of billing address at order time"
    )

    # Monetary fields in INR (₹)
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Sum of line totals before discounts and delivery"
    )
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Total savings / volume discount applied"
    )
    delivery_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Delivery or freight fee in INR"
    )
    tax_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Applicable GST or tax in INR"
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Final payable amount (subtotal - discount + delivery + tax)"
    )

    customer_notes = models.TextField(blank=True, default='')
    admin_notes = models.TextField(blank=True, default='')

    is_stock_reserved = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Indicates whether inventory has been reserved for this order"
    )
    is_stock_deducted = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Indicates whether physical stock has been deducted upon dispatch"
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.order_number} - {self.customer.email} (₹{self.total_amount})"

    def can_transition_to(self, new_status):
        """Validate if a status transition is permitted."""
        allowed = self.VALID_STATUS_TRANSITIONS.get(self.order_status, [])
        return new_status in allowed

    def can_cancel(self):
        """Customers or admins may cancel while order is pending or confirmed."""
        return self.order_status in ['pending', 'confirmed']

    def transition_to(self, new_status, changed_by=None, notes=''):
        """Transition order to new status and log history."""
        if not self.can_transition_to(new_status):
            raise ValidationError(
                f"Cannot transition order from '{self.get_order_status_display()}' to '{new_status}'."
            )

        # Stock lifecycle integration
        if new_status == 'confirmed' and not self.is_stock_reserved and not self.is_stock_deducted:
            from apps.inventory.services import InventoryService
            InventoryService.reserve_order_stock(self, user=changed_by)
        elif new_status == 'cancelled' and self.is_stock_reserved and not self.is_stock_deducted:
            from apps.inventory.services import InventoryService
            InventoryService.release_order_stock(self, user=changed_by)
        elif new_status == 'dispatched' and not self.is_stock_deducted:
            from apps.inventory.services import InventoryService
            InventoryService.dispatch_order_stock(self, user=changed_by)

        old_status = self.order_status
        self.order_status = new_status
        self.save(update_fields=['order_status', 'updated_at'])

        OrderStatusHistory.objects.create(
            order=self,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by,
            notes=notes
        )


class OrderItem(models.Model):
    """
    Immutable line item snapshot for an order.
    Preserves exact product, variant, packaging, SKU, price, and tier at purchase.
    Changes to product catalogue or pricing will NEVER alter historical order records.
    """
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items'
    )
    variant = models.ForeignKey(
        'products.ProductVariant',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_items'
    )
    product_name = models.CharField(max_length=255)
    sku = models.CharField(max_length=60)
    package_weight = models.DecimalField(max_digits=8, decimal_places=2)
    package_unit = models.CharField(max_length=20)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Effective unit price charged in INR"
    )
    retail_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Standard retail MRP at order time"
    )
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Discount savings per line"
    )
    line_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Total for this line item (unit_price * quantity)"
    )
    pricing_rule_applied = models.CharField(
        max_length=150,
        blank=True,
        default='',
        help_text="Description of rule applied (e.g. Retail MRP, Wholesale Base, Tier 50+)"
    )

    class Meta:
        verbose_name = 'Order Item'
        verbose_name_plural = 'Order Items'

    def __str__(self):
        return f"{self.product_name} ({self.package_weight} {self.package_unit}) x {self.quantity} in {self.order.order_number}"

    @property
    def display_weight(self):
        if self.package_weight == int(self.package_weight):
            weight_str = str(int(self.package_weight))
        else:
            weight_str = f"{self.package_weight:.2f}".rstrip('0').rstrip('.')
        return f"{weight_str} {self.package_unit}"


class OrderStatusHistory(models.Model):
    """
    Audit log of all order lifecycle status updates.
    """
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='status_history'
    )
    old_status = models.CharField(max_length=30, blank=True, default='')
    new_status = models.CharField(max_length=30)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_status_changes'
    )
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Order Status History'
        verbose_name_plural = 'Order Status Histories'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.order.order_number}: {self.old_status} -> {self.new_status} at {self.created_at}"


class Payment(models.Model):
    """
    Payment transaction record for an order.
    Enforces idempotency and tracks gateway responses.
    """
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('successful', 'Successful'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    )

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='payments'
    )
    transaction_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Unique transaction or reference identifier"
    )
    idempotency_key = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="Idempotency key to prevent duplicate payment processing"
    )
    payment_method = models.CharField(
        max_length=30,
        help_text="Method used (cod, bank_transfer, online)"
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True
    )
    gateway_provider = models.CharField(
        max_length=50,
        blank=True,
        default='manual',
        help_text="Payment provider (e.g. cod, manual, razorpay, cashfree)"
    )
    gateway_payload = models.JSONField(
        blank=True,
        default=dict,
        help_text="Raw or structured gateway response payload"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
        ordering = ['-created_at']

    def __str__(self):
        return f"Payment {self.transaction_id} for {self.order.order_number} (₹{self.amount} - {self.status})"


def generate_invoice_number():
    """
    Generate unique, sequentially inspired invoice number.
    Format: INV-YYYYMMDD-XXXXX
    """
    date_str = timezone.now().strftime('%Y%m%d')
    alphabet = string.ascii_uppercase + string.digits
    suffix = ''.join(secrets.choice(alphabet) for _ in range(5))
    return f"INV-{date_str}-{suffix}"


class Invoice(models.Model):
    """
    Formal tax invoice for an order.
    Complies with Indian GST requirements and preserves immutable order snapshots.
    Supports both B2C (retail) and B2B (wholesale) customer orders.
    """
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('issued', 'Issued'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    )

    order = models.OneToOneField(
        Order,
        on_delete=models.PROTECT,
        related_name='invoice',
        help_text="Order associated with this invoice"
    )
    invoice_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        default=generate_invoice_number,
        help_text="Unique invoice identifier (e.g. INV-20261104-XXXXX)"
    )
    invoice_date = models.DateField(
        default=timezone.now,
        db_index=True,
        help_text="Date when invoice was generated"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='issued',
        db_index=True
    )

    # Company Details (OnFresh Vandiperiyar, Idukki, Kerala)
    company_name = models.CharField(max_length=200, default='OnFresh Foods & Bakery')
    company_address = models.TextField(
        default='Vandiperiyar, Idukki District, Kerala - 685533, India'
    )
    company_gstin = models.CharField(max_length=20, default='32AAAFO1234A1Z5')
    company_phone = models.CharField(max_length=30, default='+91 94470 12345')
    company_email = models.EmailField(default='orders@onfresh.in')

    # Customer & Business Snapshot
    customer_name = models.CharField(max_length=200)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=30, blank=True, default='')
    customer_type = models.CharField(max_length=20, choices=Order.CUSTOMER_TYPE_CHOICES)
    business_name = models.CharField(max_length=200, blank=True, default='')
    customer_gstin = models.CharField(max_length=20, blank=True, default='')

    # Address Snapshots
    billing_address = models.JSONField(default=dict)
    shipping_address = models.JSONField(default=dict)

    # Financial Breakdowns
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    tax_rate_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.00'),
        help_text="Applicable GST percentage (e.g. 5% on packaged snacks)"
    )
    cgst_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Central GST (2.5% for intra-state)"
    )
    sgst_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="State GST (2.5% for intra-state Kerala)"
    )
    igst_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Integrated GST for inter-state"
    )
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    delivery_charge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    # Payment references
    payment_status = models.CharField(
        max_length=20,
        choices=Order.PAYMENT_STATUS_CHOICES,
        default='pending'
    )
    payment_method = models.CharField(max_length=50, default='cod')
    payment_reference = models.CharField(max_length=100, blank=True, default='')

    notes = models.TextField(
        blank=True,
        default='Thank you for your business with OnFresh. All traditional Kerala snacks are manufactured fresh in Vandiperiyar.'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Invoice'
        verbose_name_plural = 'Invoices'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.invoice_number} ({self.order.order_number}) - ₹{self.grand_total}"

