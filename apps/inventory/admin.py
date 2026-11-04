from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import StockItem, ProductionBatch, StockMovement
from .services import InventoryService


@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = (
        'sku_display',
        'product_name_display',
        'display_weight',
        'quantity_on_hand',
        'reserved_quantity',
        'available_to_sell_display',
        'stock_status_badge',
        'updated_at',
    )
    list_filter = ('variant__product__category', 'updated_at')
    search_fields = ('variant__sku', 'variant__product__name')
    readonly_fields = ('created_at', 'updated_at')

    def sku_display(self, obj):
        return obj.variant.sku
    sku_display.short_description = 'SKU'

    def product_name_display(self, obj):
        return obj.variant.product.name
    product_name_display.short_description = 'Product'

    def display_weight(self, obj):
        return obj.variant.display_weight
    display_weight.short_description = 'Weight'

    def available_to_sell_display(self, obj):
        return obj.available_to_sell
    available_to_sell_display.short_description = 'Available to Sell'

    def stock_status_badge(self, obj):
        if obj.is_out_of_stock:
            return format_html(
                '<span style="background-color: #DC2626; color: white; padding: 2px 7px; border-radius: 4px; font-weight: bold; font-size: 11px;">OUT OF STOCK</span>'
            )
        elif obj.is_low_stock:
            return format_html(
                '<span style="background-color: #D97706; color: white; padding: 2px 7px; border-radius: 4px; font-weight: bold; font-size: 11px;">LOW STOCK</span>'
            )
        return format_html(
            '<span style="background-color: #16A34A; color: white; padding: 2px 7px; border-radius: 4px; font-weight: bold; font-size: 11px;">IN STOCK</span>'
        )
    stock_status_badge.short_description = 'Status'


@admin.register(ProductionBatch)
class ProductionBatchAdmin(admin.ModelAdmin):
    list_display = (
        'batch_number',
        'variant_sku_display',
        'manufactured_quantity',
        'remaining_quantity',
        'production_date',
        'expiry_date',
        'expiry_status_badge',
        'status_badge',
        'is_stock_added',
    )
    list_filter = ('status', 'is_stock_added', 'production_date', 'expiry_date')
    search_fields = ('batch_number', 'variant__sku', 'product__name')
    readonly_fields = ('batch_number', 'is_stock_added', 'created_at', 'updated_at')
    actions = ['complete_selected_batches']

    def variant_sku_display(self, obj):
        return f"{obj.variant.product.name} ({obj.variant.display_weight})"
    variant_sku_display.short_description = 'Product Variant'

    def status_badge(self, obj):
        color_map = {
            'in_production': '#2563EB',
            'completed': '#16A34A',
            'quarantined': '#D97706',
            'exhausted': '#6B7280',
            'recalled': '#DC2626',
        }
        color = color_map.get(obj.status, '#6B7280')
        return format_html(
            f'<span style="background-color: {color}; color: white; padding: 2px 7px; border-radius: 4px; font-weight: bold; font-size: 11px;">{obj.get_status_display()}</span>'
        )
    status_badge.short_description = 'Batch Status'

    def expiry_status_badge(self, obj):
        if obj.is_expired:
            return format_html(
                '<span style="background-color: #DC2626; color: white; padding: 2px 7px; border-radius: 4px; font-weight: bold; font-size: 11px;">EXPIRED</span>'
            )
        elif obj.is_expiring_soon(30):
            return format_html(
                f'<span style="background-color: #D97706; color: white; padding: 2px 7px; border-radius: 4px; font-weight: bold; font-size: 11px;">Expires in {obj.days_until_expiry}d</span>'
            )
        return format_html(
            f'<span style="background-color: #059669; color: white; padding: 2px 7px; border-radius: 4px; font-weight: bold; font-size: 11px;">{obj.days_until_expiry} days</span>'
        )
    expiry_status_badge.short_description = 'Shelf Life'

    def complete_selected_batches(self, request, queryset):
        count = 0
        for batch in queryset:
            if not batch.is_stock_added:
                InventoryService.complete_production_batch(batch, user=request.user)
                count += 1
        self.message_user(request, f"{count} production batch(es) completed and added to inventory.")
    complete_selected_batches.short_description = "Complete selected batches and add stock"


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        'created_at',
        'movement_type_badge',
        'sku_display',
        'quantity',
        'balance_after',
        'reference_number',
        'user_email',
    )
    list_filter = ('movement_type', 'created_at')
    search_fields = ('variant__sku', 'reference_number', 'reason', 'user__email')
    readonly_fields = (
        'variant',
        'batch',
        'movement_type',
        'quantity',
        'reference_number',
        'reason',
        'balance_after',
        'user',
        'created_at',
    )

    def sku_display(self, obj):
        return f"{obj.variant.sku} ({obj.variant.display_weight})"
    sku_display.short_description = 'Variant'

    def user_email(self, obj):
        return obj.user.email if obj.user else 'System'
    user_email.short_description = 'Operator'

    def movement_type_badge(self, obj):
        color_map = {
            'production_in': '#16A34A',
            'purchase_in': '#059669',
            'order_reservation': '#D97706',
            'reservation_release': '#2563EB',
            'order_dispatch': '#4338CA',
            'customer_return': '#0D9488',
            'damage': '#DC2626',
            'expiry': '#991B1B',
            'adjustment': '#7C3AED',
        }
        color = color_map.get(obj.movement_type, '#6B7280')
        return format_html(
            f'<span style="background-color: {color}; color: white; padding: 2px 7px; border-radius: 4px; font-weight: bold; font-size: 11px;">{obj.get_movement_type_display()}</span>'
        )
    movement_type_badge.short_description = 'Movement'

