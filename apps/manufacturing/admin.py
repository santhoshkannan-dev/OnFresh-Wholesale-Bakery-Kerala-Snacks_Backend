from django.contrib import admin
from .models import (
    RawMaterialCategory,
    RawMaterial,
    RawMaterialMovement,
    Supplier,
    SupplierMaterial,
    PurchaseOrder,
    PurchaseOrderItem,
    SupplierPayment,
    Recipe,
    RecipeIngredient,
    RecipePackaging,
    ProductionOrder,
    ProductionMaterialConsumption,
    ProductionPackagingConsumption,
    QualityInspection,
)


@admin.register(RawMaterialCategory)
class RawMaterialCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'is_active', 'created_at']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(RawMaterial)
class RawMaterialAdmin(admin.ModelAdmin):
    list_display = ['material_code', 'name', 'category', 'unit_of_measure', 'current_stock', 'minimum_stock_level', 'unit_cost', 'is_active']
    list_filter = ['category', 'unit_of_measure', 'is_active']
    search_fields = ['material_code', 'name']


@admin.register(RawMaterialMovement)
class RawMaterialMovementAdmin(admin.ModelAdmin):
    list_display = ['material', 'movement_type', 'quantity', 'unit', 'balance_after', 'reference_number', 'created_at']
    list_filter = ['movement_type']
    search_fields = ['material__name', 'reference_number']


class SupplierMaterialInline(admin.TabularInline):
    model = SupplierMaterial
    extra = 1


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['supplier_code', 'name', 'contact_person', 'phone', 'city', 'state', 'is_active']
    search_fields = ['supplier_code', 'name', 'phone', 'gstin']
    inlines = [SupplierMaterialInline]


class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 1


class SupplierPaymentInline(admin.TabularInline):
    model = SupplierPayment
    extra = 0


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ['po_number', 'supplier', 'order_date', 'status', 'total_amount', 'payment_status', 'is_stock_added']
    list_filter = ['status', 'payment_status', 'is_stock_added']
    search_fields = ['po_number', 'supplier__name']
    inlines = [PurchaseOrderItemInline, SupplierPaymentInline]


class RecipeIngredientInline(admin.TabularInline):
    model = RecipeIngredient
    extra = 1


class RecipePackagingInline(admin.TabularInline):
    model = RecipePackaging
    extra = 1


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ['recipe_code', 'name', 'product', 'version', 'batch_output_quantity', 'output_unit', 'is_active']
    list_filter = ['is_active', 'output_unit']
    search_fields = ['recipe_code', 'name', 'product__name']
    inlines = [RecipeIngredientInline, RecipePackagingInline]


class ProductionMaterialConsumptionInline(admin.TabularInline):
    model = ProductionMaterialConsumption
    extra = 0


class ProductionPackagingConsumptionInline(admin.TabularInline):
    model = ProductionPackagingConsumption
    extra = 0


@admin.register(ProductionOrder)
class ProductionOrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'product', 'variant', 'planned_quantity', 'produced_quantity', 'status', 'total_production_cost', 'cost_per_unit']
    list_filter = ['status']
    search_fields = ['order_number', 'product__name', 'variant__sku']
    inlines = [ProductionMaterialConsumptionInline, ProductionPackagingConsumptionInline]


@admin.register(QualityInspection)
class QualityInspectionAdmin(admin.ModelAdmin):
    list_display = ['inspection_number', 'production_order', 'overall_result', 'release_status', 'sample_size', 'inspection_date']
    list_filter = ['overall_result', 'release_status']
    search_fields = ['inspection_number', 'production_order__order_number']

