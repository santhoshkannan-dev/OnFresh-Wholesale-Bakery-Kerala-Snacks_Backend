import secrets
import string
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone


def generate_batch_number():
    """Generate unique batch number: ONF-BAT-YYYYMMDD-XXXX"""
    date_str = timezone.localdate().strftime('%Y%m%d')
    alphabet = string.ascii_uppercase + string.digits
    suffix = ''.join(secrets.choice(alphabet) for _ in range(4))
    return f"ONF-BAT-{date_str}-{suffix}"


class StockItem(models.Model):
    """
    Inventory balance per product package variant.
    Tracks physical quantity on hand, units reserved for pending/confirmed orders,
    and available-to-sell quantity.
    """
    variant = models.OneToOneField(
        'products.ProductVariant',
        on_delete=models.CASCADE,
        related_name='inventory'
    )
    quantity_on_hand = models.PositiveIntegerField(
        default=0,
        help_text="Physical stock available in Vandiperiyar facility"
    )
    reserved_quantity = models.PositiveIntegerField(
        default=0,
        help_text="Units reserved for placed customer orders awaiting dispatch"
    )
    low_stock_threshold = models.PositiveIntegerField(
        default=20,
        validators=[MinValueValidator(1)],
        help_text="Alert threshold when available stock drops to or below this level"
    )
    last_reorder_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Stock Item'
        verbose_name_plural = 'Stock Items'
        ordering = ['variant__product__name', 'variant__package_weight']
        constraints = [
            models.CheckConstraint(
                check=models.Q(quantity_on_hand__gte=0),
                name='stock_qty_on_hand_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(reserved_quantity__gte=0),
                name='stock_reserved_qty_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(reserved_quantity__lte=models.F('quantity_on_hand')),
                name='stock_reserved_lte_on_hand'
            ),
        ]

    def __str__(self):
        return f"{self.variant.sku} - On Hand: {self.quantity_on_hand}, Reserved: {self.reserved_quantity}, Available: {self.available_to_sell}"

    @property
    def available_to_sell(self):
        """Available stock ready for purchase by retail or wholesale customers."""
        return max(0, self.quantity_on_hand - self.reserved_quantity)

    @property
    def is_low_stock(self):
        return 0 < self.available_to_sell <= self.low_stock_threshold

    @property
    def is_out_of_stock(self):
        return self.available_to_sell <= 0


class ProductionBatch(models.Model):
    """
    Production batch entity for manufactured Kerala snacks and bakery packages.
    Supports batch-level manufacturing tracking, FEFO dispatch allocation,
    and individual batch expiry tracking.
    """
    STATUS_CHOICES = (
        ('in_production', 'In Production'),
        ('completed', 'Completed / Stock Added'),
        ('quarantined', 'Quarantined / Testing'),
        ('exhausted', 'Exhausted / Sold Out'),
        ('recalled', 'Recalled / Discarded'),
    )

    batch_number = models.CharField(
        max_length=60,
        unique=True,
        db_index=True,
        default=generate_batch_number,
        editable=False
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        related_name='production_batches'
    )
    variant = models.ForeignKey(
        'products.ProductVariant',
        on_delete=models.PROTECT,
        related_name='production_batches'
    )
    production_date = models.DateField(default=timezone.localdate)
    expiry_date = models.DateField(help_text="Best before / expiry date for this batch")
    manufactured_quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Total number of units manufactured in this batch"
    )
    remaining_quantity = models.PositiveIntegerField(
        default=0,
        help_text="Units remaining in this batch available for order allocation"
    )
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default='in_production',
        db_index=True
    )
    manufacturing_notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_batches'
    )
    is_stock_added = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Prevents duplicate inventory addition if completed more than once"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Production Batch'
        verbose_name_plural = 'Production Batches'
        ordering = ['expiry_date', '-production_date']

    def __str__(self):
        return f"{self.batch_number} - {self.variant.sku} (Qty: {self.remaining_quantity}/{self.manufactured_quantity}, Exp: {self.expiry_date})"

    def clean(self):
        super().clean()
        if self.expiry_date and self.production_date and self.expiry_date <= self.production_date:
            raise ValidationError({'expiry_date': 'Expiry date must be after the production date.'})
        if self.manufactured_quantity is not None and self.manufactured_quantity < 1:
            raise ValidationError({'manufactured_quantity': 'Manufactured quantity must be at least 1 unit.'})
        if self.remaining_quantity is not None and self.remaining_quantity > self.manufactured_quantity:
            raise ValidationError({'remaining_quantity': 'Remaining quantity cannot exceed manufactured quantity.'})

    @property
    def days_until_expiry(self):
        return (self.expiry_date - timezone.localdate()).days

    @property
    def is_expired(self):
        return timezone.localdate() > self.expiry_date

    def is_expiring_soon(self, warning_days=30):
        return not self.is_expired and self.days_until_expiry <= warning_days


class StockMovement(models.Model):
    """
    Immutable audit ledger of all inventory transactions.
    Tracks received stock, sales reservations, releases, dispatches, damages, and audits.
    """
    MOVEMENT_TYPE_CHOICES = (
        ('production_in', 'Production In'),
        ('purchase_in', 'Purchase In'),
        ('order_reservation', 'Order Reservation'),
        ('reservation_release', 'Reservation Release (Order Cancelled)'),
        ('order_dispatch', 'Order Dispatch'),
        ('customer_return', 'Customer Return'),
        ('damage', 'Damage / Wastage'),
        ('expiry', 'Expiry / Dumped'),
        ('adjustment', 'Stock Adjustment (Audit)'),
    )

    variant = models.ForeignKey(
        'products.ProductVariant',
        on_delete=models.CASCADE,
        related_name='stock_movements'
    )
    batch = models.ForeignKey(
        ProductionBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_movements'
    )
    movement_type = models.CharField(
        max_length=30,
        choices=MOVEMENT_TYPE_CHOICES,
        db_index=True
    )
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Quantity of units moved"
    )
    reference_number = models.CharField(
        max_length=100,
        db_index=True,
        blank=True,
        default='',
        help_text="Order #, Batch #, or Audit reference"
    )
    reason = models.TextField(blank=True, default='')
    balance_after = models.IntegerField(
        help_text="Snapshot of available_to_sell after this movement"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_movements'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Stock Movement'
        verbose_name_plural = 'Stock Movements'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_movement_type_display()}: {self.variant.sku} x {self.quantity} (Ref: {self.reference_number})"
