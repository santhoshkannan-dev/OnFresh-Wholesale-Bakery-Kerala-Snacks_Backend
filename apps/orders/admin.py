from django.contrib import admin
from django.utils.html import format_html
from .models import Cart, CartItem, Order, OrderItem, OrderStatusHistory, Payment


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    fields = ('variant', 'quantity', 'created_at')
    readonly_fields = ('created_at',)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('user', 'total_items_count', 'updated_at')
    search_fields = ('user__email', 'user__username')
    inlines = [CartItemInline]
    readonly_fields = ('created_at', 'updated_at')


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = (
        'product_name',
        'sku',
        'package_weight',
        'package_unit',
        'quantity',
        'retail_price',
        'unit_price',
        'discount_amount',
        'line_total',
        'pricing_rule_applied'
    )
    readonly_fields = (
        'product_name',
        'sku',
        'package_weight',
        'package_unit',
        'quantity',
        'retail_price',
        'unit_price',
        'discount_amount',
        'line_total',
        'pricing_rule_applied'
    )
    can_delete = False


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    fields = ('old_status', 'new_status', 'changed_by', 'notes', 'created_at')
    readonly_fields = ('old_status', 'new_status', 'changed_by', 'notes', 'created_at')
    can_delete = False


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    fields = ('transaction_id', 'payment_method', 'amount', 'status', 'gateway_provider', 'created_at')
    readonly_fields = ('transaction_id', 'created_at')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'order_number',
        'customer_email_display',
        'customer_type_badge',
        'order_status_badge',
        'payment_status_badge',
        'payment_method',
        'formatted_total',
        'created_at',
    )
    list_filter = (
        'order_status',
        'payment_status',
        'customer_type',
        'payment_method',
        'created_at',
    )
    search_fields = (
        'order_number',
        'customer__email',
        'customer__username',
        'shipping_address_snapshot__recipient_name',
        'shipping_address_snapshot__phone_number',
    )
    readonly_fields = (
        'order_number',
        'customer',
        'customer_profile',
        'customer_type',
        'subtotal',
        'discount_amount',
        'delivery_charge',
        'tax_amount',
        'total_amount',
        'created_at',
        'updated_at',
    )
    inlines = [OrderItemInline, PaymentInline, OrderStatusHistoryInline]
    actions = [
        'mark_confirmed',
        'mark_processing',
        'mark_ready_for_dispatch',
        'mark_dispatched',
        'mark_delivered',
        'mark_cancelled',
        'mark_payment_paid',
    ]

    fieldsets = (
        ('Order Identification', {
            'fields': ('order_number', 'customer', 'customer_profile', 'customer_type', 'created_at', 'updated_at')
        }),
        ('Status & Lifecycle', {
            'fields': ('order_status', 'payment_status', 'payment_method', 'customer_notes', 'admin_notes')
        }),
        ('Financial Totals (INR ₹)', {
            'fields': ('subtotal', 'discount_amount', 'delivery_charge', 'tax_amount', 'total_amount')
        }),
        ('Address Snapshots', {
            'fields': ('shipping_address_snapshot', 'billing_address_snapshot'),
            'classes': ('collapse',),
        }),
    )

    def customer_email_display(self, obj):
        return obj.customer.email
    customer_email_display.short_description = 'Customer Email'

    def formatted_total(self, obj):
        return f"₹{obj.total_amount:,.2f}"
    formatted_total.short_description = 'Total (₹)'

    def customer_type_badge(self, obj):
        if obj.customer_type == 'business':
            return format_html(
                '<span style="background-color: #1E3A8A; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;">Wholesale B2B</span>'
            )
        return format_html(
            '<span style="background-color: #065F46; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;">Retail B2C</span>'
        )
    customer_type_badge.short_description = 'Segment'

    def order_status_badge(self, obj):
        color_map = {
            'pending': '#D97706',
            'confirmed': '#2563EB',
            'processing': '#7C3AED',
            'ready_for_dispatch': '#0D9488',
            'dispatched': '#4338CA',
            'delivered': '#16A34A',
            'cancelled': '#DC2626',
        }
        color = color_map.get(obj.order_status, '#6B7280')
        return format_html(
            f'<span style="background-color: {color}; color: white; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;">{obj.get_order_status_display()}</span>'
        )
    order_status_badge.short_description = 'Order Status'

    def payment_status_badge(self, obj):
        color_map = {
            'pending': '#D97706',
            'partially_paid': '#2563EB',
            'paid': '#16A34A',
            'failed': '#DC2626',
            'refunded': '#6B7280',
        }
        color = color_map.get(obj.payment_status, '#6B7280')
        return format_html(
            f'<span style="background-color: {color}; color: white; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: bold;">{obj.get_payment_status_display()}</span>'
        )
    payment_status_badge.short_description = 'Payment Status'

    def save_model(self, request, obj, form, change):
        if change and 'order_status' in form.changed_data:
            old_order = Order.objects.get(pk=obj.pk)
            old_status = old_order.order_status
            new_status = obj.order_status
            OrderStatusHistory.objects.create(
                order=obj,
                old_status=old_status,
                new_status=new_status,
                changed_by=request.user,
                notes=f"Status changed via Django Admin to {new_status}."
            )
        super().save_model(request, obj, form, change)

    # Bulk status transition actions
    def mark_confirmed(self, request, queryset):
        for order in queryset:
            if order.can_transition_to('confirmed'):
                order.transition_to('confirmed', changed_by=request.user, notes='Bulk confirmation by staff.')
        self.message_user(request, "Selected orders processed for Confirmation.")
    mark_confirmed.short_description = "Status: Mark selected as Confirmed"

    def mark_processing(self, request, queryset):
        for order in queryset:
            if order.can_transition_to('processing'):
                order.transition_to('processing', changed_by=request.user, notes='Moved to production.')
        self.message_user(request, "Selected orders processed for Production/Processing.")
    mark_processing.short_description = "Status: Mark selected as Processing"

    def mark_ready_for_dispatch(self, request, queryset):
        for order in queryset:
            if order.can_transition_to('ready_for_dispatch'):
                order.transition_to('ready_for_dispatch', changed_by=request.user, notes='Packed and ready for dispatch.')
        self.message_user(request, "Selected orders marked Ready for Dispatch.")
    mark_ready_for_dispatch.short_description = "Status: Mark selected as Ready for Dispatch"

    def mark_dispatched(self, request, queryset):
        for order in queryset:
            if order.can_transition_to('dispatched'):
                order.transition_to('dispatched', changed_by=request.user, notes='Dispatched via logistics partner.')
        self.message_user(request, "Selected orders marked Dispatched.")
    mark_dispatched.short_description = "Status: Mark selected as Dispatched"

    def mark_delivered(self, request, queryset):
        for order in queryset:
            if order.can_transition_to('delivered'):
                order.transition_to('delivered', changed_by=request.user, notes='Delivered successfully.')
                if order.payment_method == 'cod' and order.payment_status != 'paid':
                    order.payment_status = 'paid'
                    order.save(update_fields=['payment_status', 'updated_at'])
        self.message_user(request, "Selected orders marked Delivered.")
    mark_delivered.short_description = "Status: Mark selected as Delivered"

    def mark_cancelled(self, request, queryset):
        for order in queryset:
            if order.can_cancel():
                order.transition_to('cancelled', changed_by=request.user, notes='Cancelled by admin action.')
        self.message_user(request, "Eligible orders cancelled.")
    mark_cancelled.short_description = "Status: Mark selected as Cancelled"

    def mark_payment_paid(self, request, queryset):
        updated = queryset.update(payment_status='paid')
        self.message_user(request, f"{updated} order(s) marked as Payment Paid.")
    mark_payment_paid.short_description = "Payment: Mark selected as Paid"


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'order', 'payment_method', 'amount', 'status', 'gateway_provider', 'created_at')
    list_filter = ('status', 'payment_method', 'gateway_provider')
    search_fields = ('transaction_id', 'order__order_number', 'order__customer__email')
    readonly_fields = ('created_at', 'updated_at')

