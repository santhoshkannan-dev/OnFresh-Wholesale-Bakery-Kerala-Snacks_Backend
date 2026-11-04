import secrets
import string
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


def generate_code_suffix(length: int = 4) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def generate_po_number() -> str:
    date_str = timezone.localdate().strftime('%Y%m%d')
    return f"ONF-PO-{date_str}-{generate_code_suffix()}"


def generate_prd_order_number() -> str:
    date_str = timezone.localdate().strftime('%Y%m%d')
    return f"ONF-PRD-{date_str}-{generate_code_suffix()}"


def generate_qc_number() -> str:
    date_str = timezone.localdate().strftime('%Y%m%d')
    return f"ONF-QC-{date_str}-{generate_code_suffix()}"


def generate_payment_number() -> str:
    date_str = timezone.localdate().strftime('%Y%m%d')
    return f"ONF-PAY-{date_str}-{generate_code_suffix()}"


class RawMaterialCategory(models.Model):
    """
    Categories for raw materials, agricultural produce, oils, spices, and packaging supplies.
    """
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Raw Material Category'
        verbose_name_plural = 'Raw Material Categories'
        ordering = ['name']

    def __str__(self):
        return self.name


class RawMaterial(models.Model):
    """
    Raw material inventory item stored at the Vandiperiyar production facility.
    Tracks agricultural produce, flours, oils, spices, and packaging materials.
    """
    UNIT_CHOICES = (
        ('kg', 'Kilogram (kg)'),
        ('g', 'Gram (g)'),
        ('l', 'Litre (l)'),
        ('ml', 'Millilitre (ml)'),
        ('pcs', 'Pieces (pcs)'),
        ('roll', 'Roll'),
        ('bundle', 'Bundle'),
        ('box', 'Box'),
    )

    material_code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Unique SKU/Code e.g. RM-BAN-001, RM-OIL-001, PKG-POUCH-250"
    )
    name = models.CharField(max_length=150, db_index=True)
    category = models.ForeignKey(
        RawMaterialCategory,
        on_delete=models.PROTECT,
        related_name='materials'
    )
    unit_of_measure = models.CharField(
        max_length=10,
        choices=UNIT_CHOICES,
        default='kg'
    )
    current_stock = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal('0.000'),
        help_text="Current physical inventory in base units"
    )
    minimum_stock_level = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal('10.000'),
        help_text="Reorder point threshold triggering replenishment alerts"
    )
    reorder_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal('50.000'),
        help_text="Suggested standard purchase replenishment quantity"
    )
    unit_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Latest or standard cost per base unit in INR"
    )
    storage_location = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="e.g. Cold Room 1, Dry Spices Loft, Packaging Bay B"
    )
    shelf_life_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Typical shelf life in days from receipt"
    )
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Raw Material'
        verbose_name_plural = 'Raw Materials'
        ordering = ['category__name', 'name']
        constraints = [
            models.CheckConstraint(
                check=models.Q(current_stock__gte=0),
                name='raw_material_stock_non_negative'
            ),
            models.CheckConstraint(
                check=models.Q(minimum_stock_level__gte=0),
                name='raw_material_min_stock_non_negative'
            ),
        ]

    def __str__(self):
        return f"{self.material_code} - {self.name} ({self.current_stock} {self.unit_of_measure})"

    @property
    def is_low_stock(self) -> bool:
        return 0 < self.current_stock <= self.minimum_stock_level

    @property
    def is_out_of_stock(self) -> bool:
        return self.current_stock <= Decimal('0.000')

    @property
    def total_stock_value(self) -> Decimal:
        return (self.current_stock * self.unit_cost).quantize(Decimal('0.01'))


class RawMaterialMovement(models.Model):
    """
    Immutable ledger of all stock transactions for raw materials and packaging.
    Guarantees full traceability from PO receipts to kitchen consumption and wastage.
    """
    MOVEMENT_TYPES = (
        ('purchase_in', 'Purchase Receipt / Inward'),
        ('production_consumption', 'Production Consumption'),
        ('wastage', 'Production Wastage / Damage'),
        ('adjustment', 'Physical Audit Adjustment'),
        ('return', 'Vendor Return'),
    )

    material = models.ForeignKey(
        RawMaterial,
        on_delete=models.CASCADE,
        related_name='movements'
    )
    movement_type = models.CharField(max_length=30, choices=MOVEMENT_TYPES, db_index=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit = models.CharField(max_length=10)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    balance_after = models.DecimalField(max_digits=12, decimal_places=3)
    reference_number = models.CharField(max_length=100, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='raw_material_movements'
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'Raw Material Movement'
        verbose_name_plural = 'Raw Material Movements'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.material.material_code} {self.movement_type} {self.quantity} {self.unit} (Bal: {self.balance_after})"


class Supplier(models.Model):
    """
    Agricultural and packaging suppliers delivering materials to OnFresh facility in Vandiperiyar.
    """
    name = models.CharField(max_length=150, unique=True, db_index=True)
    supplier_code = models.CharField(max_length=50, unique=True, db_index=True)
    contact_person = models.CharField(max_length=100, blank=True, default='')
    phone = models.CharField(max_length=20, db_index=True)
    email = models.EmailField(blank=True, default='')
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True, default='')
    city = models.CharField(max_length=100, default='Vandiperiyar')
    state = models.CharField(max_length=100, default='Kerala')
    postal_code = models.CharField(max_length=20, default='685533')
    country = models.CharField(max_length=100, default='India')
    gstin = models.CharField(max_length=20, blank=True, default='', db_index=True)
    payment_terms = models.CharField(
        max_length=100,
        blank=True,
        default='Net 15 days',
        help_text="e.g. Net 15 days, Advance 50%, Cash on Delivery"
    )
    lead_time_days = models.PositiveIntegerField(
        default=3,
        help_text="Estimated delivery lead time in days"
    )
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Supplier'
        verbose_name_plural = 'Suppliers'
        ordering = ['name']

    def __str__(self):
        return f"{self.supplier_code} - {self.name} ({self.city}, {self.state})"


class SupplierMaterial(models.Model):
    """
    Mapping between a supplier and the raw materials they supply, including quoted prices.
    """
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name='supplied_materials'
    )
    material = models.ForeignKey(
        RawMaterial,
        on_delete=models.CASCADE,
        related_name='supplier_sources'
    )
    supplier_material_code = models.CharField(max_length=50, blank=True, default='')
    quoted_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Standard vendor contract price per unit in INR"
    )
    minimum_order_qty = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=Decimal('1.000'),
        validators=[MinValueValidator(Decimal('0.001'))]
    )
    is_preferred = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Supplier Material'
        verbose_name_plural = 'Supplier Materials'
        unique_together = ('supplier', 'material')

    def __str__(self):
        return f"{self.supplier.name} -> {self.material.name} (₹{self.quoted_price}/{self.material.unit_of_measure})"


class PurchaseOrder(models.Model):
    """
    Purchase Order for procurement of raw agricultural ingredients, oils, and packaging.
    Stock is only credited when explicitly received into facility.
    """
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('ordered', 'Ordered / Placed with Vendor'),
        ('partially_received', 'Partially Received'),
        ('received', 'Fully Received & Stocked'),
        ('cancelled', 'Cancelled'),
    )

    PAYMENT_STATUS_CHOICES = (
        ('unpaid', 'Unpaid'),
        ('partially_paid', 'Partially Paid'),
        ('paid', 'Fully Paid'),
    )

    po_number = models.CharField(
        max_length=60,
        unique=True,
        db_index=True,
        default=generate_po_number,
        editable=False
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='purchase_orders'
    )
    order_date = models.DateField(default=timezone.localdate)
    expected_delivery_date = models.DateField(null=True, blank=True)
    received_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default='draft',
        db_index=True
    )
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    is_stock_added = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Prevents duplicate inventory addition on repeat confirmations"
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='unpaid',
        db_index=True
    )
    amount_paid = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    vendor_invoice_number = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Supplier's bill / invoice number"
    )
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_purchase_orders'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Purchase Order'
        verbose_name_plural = 'Purchase Orders'
        ordering = ['-order_date', '-created_at']

    def __str__(self):
        return f"{self.po_number} - {self.supplier.name} (₹{self.total_amount}) [{self.status}]"

    def recalculate_totals(self):
        subtotal = Decimal('0.00')
        tax = Decimal('0.00')
        for item in self.items.all():
            item_sub = (item.ordered_quantity * item.unit_cost).quantize(Decimal('0.01'))
            item_tax = (item_sub * (item.tax_rate / Decimal('100.00'))).quantize(Decimal('0.01'))
            subtotal += item_sub
            tax += item_tax
        self.subtotal = subtotal
        self.tax_amount = tax
        self.total_amount = subtotal + tax
        self.save(update_fields=['subtotal', 'tax_amount', 'total_amount', 'updated_at'])


class PurchaseOrderItem(models.Model):
    """
    Line item in a Purchase Order.
    """
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name='items'
    )
    material = models.ForeignKey(
        RawMaterial,
        on_delete=models.PROTECT,
        related_name='purchase_items'
    )
    ordered_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))]
    )
    received_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal('0.000'),
        validators=[MinValueValidator(Decimal('0.000'))]
    )
    unit_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="GST percentage rate e.g. 5.00, 12.00, 18.00"
    )
    total_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )

    class Meta:
        verbose_name = 'Purchase Order Item'
        verbose_name_plural = 'Purchase Order Items'

    def __str__(self):
        return f"{self.purchase_order.po_number} -> {self.material.name} ({self.ordered_quantity} {self.material.unit_of_measure})"

    def save(self, *args, **kwargs):
        line_sub = (self.ordered_quantity * self.unit_cost).quantize(Decimal('0.01'))
        line_tax = (line_sub * (self.tax_rate / Decimal('100.00'))).quantize(Decimal('0.01'))
        self.total_cost = line_sub + line_tax
        super().save(*args, **kwargs)


class SupplierPayment(models.Model):
    """
    Payment voucher recorded against a Purchase Order.
    """
    PAYMENT_METHODS = (
        ('bank_transfer', 'NEFT / RTGS / Bank Transfer'),
        ('upi', 'UPI Payment'),
        ('cheque', 'Cheque'),
        ('cash', 'Cash'),
        ('credit', 'Trade Credit / Adjust'),
    )

    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.PROTECT,
        related_name='payments'
    )
    payment_number = models.CharField(
        max_length=60,
        unique=True,
        db_index=True,
        default=generate_payment_number,
        editable=False
    )
    payment_date = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    payment_method = models.CharField(
        max_length=30,
        choices=PAYMENT_METHODS,
        default='bank_transfer'
    )
    reference_number = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="UTR / Cheque / Txn reference number"
    )
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recorded_supplier_payments'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Supplier Payment'
        verbose_name_plural = 'Supplier Payments'
        ordering = ['-payment_date', '-created_at']

    def __str__(self):
        return f"{self.payment_number} - {self.purchase_order.po_number}: ₹{self.amount} via {self.payment_method}"


class Recipe(models.Model):
    """
    Master Bill of Materials (BOM) & standard formulation for Kerala snacks and bakery products.
    Supports recipe versioning to maintain historical production integrity.
    """
    OUTPUT_UNITS = (
        ('packets', 'Packets'),
        ('kg', 'Kilograms (kg)'),
        ('boxes', 'Boxes'),
        ('pcs', 'Pieces'),
    )

    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        related_name='recipes'
    )
    variant = models.ForeignKey(
        'products.ProductVariant',
        on_delete=models.PROTECT,
        related_name='recipes',
        null=True,
        blank=True,
        help_text="Optionally tie recipe to a specific package size/variant"
    )
    recipe_code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="e.g. RCP-BAN-CHIP-V1, RCP-MIXTURE-V2"
    )
    name = models.CharField(max_length=150)
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True, db_index=True)
    batch_output_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=Decimal('50.000'),
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text="Standard batch yield quantity in output units"
    )
    output_unit = models.CharField(
        max_length=20,
        choices=OUTPUT_UNITS,
        default='packets'
    )
    target_variant_units = models.PositiveIntegerField(
        default=100,
        help_text="Number of finished retail/wholesale packet units produced per batch"
    )
    estimated_labor_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Estimated labor cost per standard batch in INR"
    )
    estimated_overhead_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Estimated overhead (electricity, gas/firewood, nitrogen, machinery) in INR"
    )
    instructions = models.TextField(
        blank=True,
        default='',
        help_text="Step by step manufacturing and frying guidelines in Vandiperiyar kitchen"
    )
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Recipe (BOM)'
        verbose_name_plural = 'Recipes (BOMs)'
        ordering = ['product__name', '-version']

    def __str__(self):
        return f"{self.recipe_code} - {self.name} (v{self.version})"

    @property
    def estimated_raw_material_cost(self) -> Decimal:
        total = Decimal('0.00')
        for ing in self.ingredients.all():
            total += ing.effective_cost
        return total.quantize(Decimal('0.01'))

    @property
    def estimated_packaging_cost(self) -> Decimal:
        total = Decimal('0.00')
        for pkg in self.packaging_materials.all():
            total += pkg.effective_cost
        return total.quantize(Decimal('0.01'))

    @property
    def estimated_total_cost(self) -> Decimal:
        return (
            self.estimated_raw_material_cost +
            self.estimated_packaging_cost +
            self.estimated_labor_cost +
            self.estimated_overhead_cost
        ).quantize(Decimal('0.01'))

    @property
    def estimated_cost_per_unit(self) -> Decimal:
        units = self.target_variant_units or int(self.batch_output_quantity) or 1
        return (self.estimated_total_cost / Decimal(units)).quantize(Decimal('0.01'))


class RecipeIngredient(models.Model):
    """
    Raw material component of a recipe BOM with expected wastage factor.
    """
    recipe = models.ForeignKey(
        Recipe,
        on_delete=models.CASCADE,
        related_name='ingredients'
    )
    material = models.ForeignKey(
        RawMaterial,
        on_delete=models.PROTECT,
        related_name='recipe_usages'
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text="Standard raw quantity required per recipe batch"
    )
    unit = models.CharField(max_length=10)
    wastage_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Expected peeling, moisture loss or trimming percentage (e.g. 8.00%)"
    )

    class Meta:
        verbose_name = 'Recipe Ingredient'
        verbose_name_plural = 'Recipe Ingredients'

    def __str__(self):
        return f"{self.recipe.recipe_code} -> {self.material.name}: {self.quantity} {self.unit} (+{self.wastage_percentage}% waste)"

    @property
    def effective_quantity(self) -> Decimal:
        waste_multiplier = Decimal('1.00') + (self.wastage_percentage / Decimal('100.00'))
        return (self.quantity * waste_multiplier).quantize(Decimal('0.001'))

    @property
    def effective_cost(self) -> Decimal:
        return (self.effective_quantity * self.material.unit_cost).quantize(Decimal('0.01'))


class RecipePackaging(models.Model):
    """
    Packaging requirement for a recipe (pouches, corrugated cartons, labels).
    """
    recipe = models.ForeignKey(
        Recipe,
        on_delete=models.CASCADE,
        related_name='packaging_materials'
    )
    packaging_material = models.ForeignKey(
        RawMaterial,
        on_delete=models.PROTECT,
        related_name='recipe_packaging_usages'
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        help_text="Quantity of packaging units per recipe batch"
    )
    unit = models.CharField(max_length=10, default='pcs')
    notes = models.CharField(
        max_length=200,
        blank=True,
        default='',
        help_text="e.g. 100 printed pouches + 5 master cartons"
    )

    class Meta:
        verbose_name = 'Recipe Packaging Material'
        verbose_name_plural = 'Recipe Packaging Materials'

    def __str__(self):
        return f"{self.recipe.recipe_code} -> {self.packaging_material.name}: {self.quantity} {self.unit}"

    @property
    def effective_cost(self) -> Decimal:
        return (self.quantity * self.packaging_material.unit_cost).quantize(Decimal('0.01'))


class ProductionOrder(models.Model):
    """
    Manufacturing work order tracking the complete production run in Vandiperiyar.
    Coordinates raw materials, cooking, packaging, cost computation, and finished goods creation.
    """
    STATUS_CHOICES = (
        ('planned', 'Planned'),
        ('approved', 'Approved / Materials Reserved'),
        ('in_progress', 'In Progress / Cooking & Frying'),
        ('quality_check', 'Quality Check / Laboratory Inspection'),
        ('completed', 'Completed & Released to Finished Goods'),
        ('cancelled', 'Cancelled'),
    )

    order_number = models.CharField(
        max_length=60,
        unique=True,
        db_index=True,
        default=generate_prd_order_number,
        editable=False
    )
    recipe = models.ForeignKey(
        Recipe,
        on_delete=models.PROTECT,
        related_name='production_orders'
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        related_name='production_orders'
    )
    variant = models.ForeignKey(
        'products.ProductVariant',
        on_delete=models.PROTECT,
        related_name='production_orders'
    )
    planned_quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Target number of finished packets to produce"
    )
    produced_quantity = models.PositiveIntegerField(
        default=0,
        help_text="Actual finished packets accepted after packaging"
    )
    rejected_quantity = models.PositiveIntegerField(
        default=0,
        help_text="Damaged or discarded packets during line run"
    )
    start_date = models.DateField(default=timezone.localdate)
    completion_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default='planned',
        db_index=True
    )
    raw_material_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    packaging_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    labor_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )
    overhead_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )
    total_production_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00')
    )
    cost_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00')
    )
    notes = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_production_orders'
    )
    production_batch = models.OneToOneField(
        'inventory.ProductionBatch',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='production_work_order',
        help_text="Phase 6 finished goods batch linked upon completion"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Production Order'
        verbose_name_plural = 'Production Orders'
        ordering = ['-start_date', '-created_at']

    def __str__(self):
        return f"{self.order_number} - {self.variant.sku} (Target: {self.planned_quantity}, Produced: {self.produced_quantity}) [{self.status}]"

    def recalculate_costs(self):
        rm_total = Decimal('0.00')
        for item in self.material_consumptions.all():
            rm_total += item.total_cost

        pkg_total = Decimal('0.00')
        for item in self.packaging_consumptions.all():
            pkg_total += item.total_cost

        self.raw_material_cost = rm_total
        self.packaging_cost = pkg_total
        self.total_production_cost = (
            rm_total + pkg_total + self.labor_cost + self.overhead_cost
        ).quantize(Decimal('0.01'))

        units = self.produced_quantity or self.planned_quantity or 1
        self.cost_per_unit = (self.total_production_cost / Decimal(units)).quantize(Decimal('0.01'))
        self.save(update_fields=[
            'raw_material_cost', 'packaging_cost', 'total_production_cost',
            'cost_per_unit', 'updated_at'
        ])


class ProductionMaterialConsumption(models.Model):
    """
    Actual raw materials consumed and wasted during a specific production run.
    """
    production_order = models.ForeignKey(
        ProductionOrder,
        on_delete=models.CASCADE,
        related_name='material_consumptions'
    )
    material = models.ForeignKey(
        RawMaterial,
        on_delete=models.PROTECT,
        related_name='production_consumptions'
    )
    planned_quantity = models.DecimalField(max_digits=12, decimal_places=3)
    actual_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal('0.000')
    )
    wastage_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal('0.000')
    )
    unit = models.CharField(max_length=10)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        verbose_name = 'Production Material Consumption'
        verbose_name_plural = 'Production Material Consumptions'

    def __str__(self):
        return f"{self.production_order.order_number} -> {self.material.name} (Actual: {self.actual_quantity} {self.unit})"

    def save(self, *args, **kwargs):
        total_qty = self.actual_quantity + self.wastage_quantity
        self.total_cost = (total_qty * self.unit_cost).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)


class ProductionPackagingConsumption(models.Model):
    """
    Actual packaging consumed and damaged during a production line run.
    """
    production_order = models.ForeignKey(
        ProductionOrder,
        on_delete=models.CASCADE,
        related_name='packaging_consumptions'
    )
    material = models.ForeignKey(
        RawMaterial,
        on_delete=models.PROTECT,
        related_name='production_packaging_consumptions'
    )
    planned_quantity = models.DecimalField(max_digits=12, decimal_places=3)
    actual_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal('0.000')
    )
    wastage_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal('0.000')
    )
    unit = models.CharField(max_length=10, default='pcs')
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        verbose_name = 'Production Packaging Consumption'
        verbose_name_plural = 'Production Packaging Consumptions'

    def __str__(self):
        return f"{self.production_order.order_number} -> {self.material.name} (Pouches/Boxes: {self.actual_quantity} {self.unit})"

    def save(self, *args, **kwargs):
        total_qty = self.actual_quantity + self.wastage_quantity
        self.total_cost = (total_qty * self.unit_cost).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)


class QualityInspection(models.Model):
    """
    Rigorous quality control inspection for Kerala snack batches manufactured in Vandiperiyar.
    Acts as the strict gatekeeper: only batches with 'passed' overall_result and 'released' status
    are added to finished-goods inventory and made available for customer purchase.
    """
    PARAMETER_STATUS = (
        ('pass', 'Pass / Meets Standards'),
        ('marginal', 'Marginal / Acceptable with Warning'),
        ('fail', 'Fail / Non-Compliant'),
    )

    OVERALL_RESULTS = (
        ('pending', 'Pending Evaluation'),
        ('passed', 'Passed All Standards'),
        ('failed', 'Failed Quality Standards'),
        ('quarantined', 'Quarantined for Secondary Testing'),
    )

    RELEASE_STATUS = (
        ('quarantined', 'Quarantined / Hold'),
        ('released', 'Released for Distribution & Sale'),
        ('rejected', 'Rejected & Discarded'),
    )

    inspection_number = models.CharField(
        max_length=60,
        unique=True,
        db_index=True,
        default=generate_qc_number,
        editable=False
    )
    production_order = models.ForeignKey(
        ProductionOrder,
        on_delete=models.PROTECT,
        related_name='inspections'
    )
    production_batch = models.ForeignKey(
        'inventory.ProductionBatch',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='quality_checks'
    )
    inspector = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quality_inspections'
    )
    inspection_date = models.DateTimeField(default=timezone.now)
    sample_size = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(1)],
        help_text="Number of packages sampled from production run"
    )
    appearance_status = models.CharField(
        max_length=15,
        choices=PARAMETER_STATUS,
        default='pass',
        help_text="Golden color, uniform slice thickness, no burnt spots"
    )
    taste_crispness_status = models.CharField(
        max_length=15,
        choices=PARAMETER_STATUS,
        default='pass',
        help_text="Signature crispness, fresh coconut oil aroma, salt level"
    )
    moisture_status = models.CharField(
        max_length=15,
        choices=PARAMETER_STATUS,
        default='pass',
        help_text="Moisture content under acceptable standard (< 3.0%)"
    )
    packaging_seal_status = models.CharField(
        max_length=15,
        choices=PARAMETER_STATUS,
        default='pass',
        help_text="Hermetic seal and nitrogen flush integrity, no leakage"
    )
    label_batch_verification = models.CharField(
        max_length=15,
        choices=PARAMETER_STATUS,
        default='pass',
        help_text="Legibility of Batch No, Mfg Date, Expiry Date, MRP"
    )
    overall_result = models.CharField(
        max_length=20,
        choices=OVERALL_RESULTS,
        default='pending',
        db_index=True
    )
    release_status = models.CharField(
        max_length=20,
        choices=RELEASE_STATUS,
        default='quarantined',
        db_index=True
    )
    defect_notes = models.TextField(blank=True, default='')
    corrective_actions = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Quality Inspection'
        verbose_name_plural = 'Quality Inspections'
        ordering = ['-inspection_date', '-created_at']

    def __str__(self):
        return f"{self.inspection_number} - Order {self.production_order.order_number}: {self.overall_result} ({self.release_status})"

