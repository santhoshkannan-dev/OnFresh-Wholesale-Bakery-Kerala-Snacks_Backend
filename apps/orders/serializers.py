from decimal import Decimal
from rest_framework import serializers
from apps.products.models import ProductVariant
from apps.customers.models import Address
from .models import Cart, CartItem, Order, OrderItem, OrderStatusHistory, Payment, Invoice
from .pricing import PricingService


class CartItemAddSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(default=1, min_value=1)


class CartItemUpdateSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)


class CartSyncItemSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1)


class CartSyncSerializer(serializers.Serializer):
    items = serializers.ListField(
        child=CartSyncItemSerializer(),
        allow_empty=True
    )


class CartItemResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    variant_id = serializers.IntegerField()
    sku = serializers.CharField()
    product_name = serializers.CharField()
    product_slug = serializers.CharField()
    image = serializers.CharField(allow_null=True)
    package_weight = serializers.DecimalField(max_digits=8, decimal_places=2)
    package_unit = serializers.CharField()
    display_weight = serializers.CharField()
    quantity = serializers.IntegerField()
    moq = serializers.IntegerField()
    moq_met = serializers.BooleanField()
    retail_unit_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    line_subtotal = serializers.DecimalField(max_digits=12, decimal_places=2)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2)
    line_discount = serializers.DecimalField(max_digits=10, decimal_places=2)
    pricing_rule_applied = serializers.CharField()
    errors = serializers.ListField(child=serializers.CharField())


class CartResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    items = serializers.ListField(child=CartItemResponseSerializer())
    items_count = serializers.IntegerField()
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    delivery_charge = serializers.DecimalField(max_digits=10, decimal_places=2)
    tax_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    free_delivery_threshold = serializers.DecimalField(max_digits=12, decimal_places=2)
    amount_for_free_delivery = serializers.DecimalField(max_digits=12, decimal_places=2)
    customer_segment = serializers.CharField()
    is_wholesale_approved = serializers.BooleanField()
    is_valid = serializers.BooleanField()
    errors = serializers.ListField(child=serializers.CharField())
    currency = serializers.CharField(default='INR')


class InlineAddressSerializer(serializers.Serializer):
    recipient_name = serializers.CharField(max_length=150)
    phone_number = serializers.CharField(max_length=20)
    address_line_1 = serializers.CharField(max_length=255)
    address_line_2 = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    city = serializers.CharField(max_length=100)
    district = serializers.CharField(max_length=100, default='Idukki')
    state = serializers.CharField(max_length=100, default='Kerala')
    pincode = serializers.CharField(max_length=10)


class CheckoutRequestSerializer(serializers.Serializer):
    shipping_address_id = serializers.IntegerField(required=False, allow_null=True)
    billing_address_id = serializers.IntegerField(required=False, allow_null=True)
    new_shipping_address = InlineAddressSerializer(required=False, allow_null=True)
    new_billing_address = InlineAddressSerializer(required=False, allow_null=True)
    same_as_shipping = serializers.BooleanField(default=True)
    payment_method = serializers.ChoiceField(
        choices=['cod', 'bank_transfer', 'online'],
        default='cod'
    )
    customer_notes = serializers.CharField(required=False, allow_blank=True, default='')

    def validate(self, attrs):
        # Shipping address check: either ID or new address must be supplied
        shipping_id = attrs.get('shipping_address_id')
        new_shipping = attrs.get('new_shipping_address')

        if not shipping_id and not new_shipping:
            raise serializers.ValidationError(
                "Either a saved shipping address or new shipping address details must be provided."
            )

        same_as_shipping = attrs.get('same_as_shipping', True)
        if not same_as_shipping:
            billing_id = attrs.get('billing_address_id')
            new_billing = attrs.get('new_billing_address')
            if not billing_id and not new_billing:
                raise serializers.ValidationError(
                    "Billing address must be specified when not identical to shipping address."
                )

        return attrs


class OrderItemSerializer(serializers.ModelSerializer):
    display_weight = serializers.ReadOnlyField()

    class Meta:
        model = OrderItem
        fields = [
            'id',
            'product_name',
            'sku',
            'package_weight',
            'package_unit',
            'display_weight',
            'quantity',
            'unit_price',
            'retail_price',
            'discount_amount',
            'line_total',
            'pricing_rule_applied',
        ]


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_email = serializers.SerializerMethodField()

    class Meta:
        model = OrderStatusHistory
        fields = [
            'id',
            'old_status',
            'new_status',
            'changed_by_email',
            'notes',
            'created_at',
        ]

    def get_changed_by_email(self, obj):
        return obj.changed_by.email if obj.changed_by else None


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            'id',
            'transaction_id',
            'idempotency_key',
            'payment_method',
            'amount',
            'status',
            'gateway_provider',
            'gateway_payload',
            'created_at',
        ]


class OrderListSerializer(serializers.ModelSerializer):
    customer_email = serializers.CharField(source='customer.email', read_only=True)
    order_status_display = serializers.CharField(source='get_order_status_display', read_only=True)
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    items_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            'id',
            'order_number',
            'customer_email',
            'customer_type',
            'order_status',
            'order_status_display',
            'payment_status',
            'payment_status_display',
            'payment_method',
            'payment_method_display',
            'total_amount',
            'items_count',
            'created_at',
        ]

    def get_items_count(self, obj):
        return sum(item.quantity for item in obj.items.all())


class OrderDetailSerializer(serializers.ModelSerializer):
    customer_email = serializers.CharField(source='customer.email', read_only=True)
    customer_name = serializers.SerializerMethodField()
    order_status_display = serializers.CharField(source='get_order_status_display', read_only=True)
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    can_cancel = serializers.SerializerMethodField()
    invoice_number = serializers.CharField(source='invoice.invoice_number', read_only=True, default=None)
    items = OrderItemSerializer(many=True, read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            'id',
            'order_number',
            'invoice_number',
            'customer_email',
            'customer_name',
            'customer_type',
            'order_status',
            'order_status_display',
            'payment_status',
            'payment_status_display',
            'payment_method',
            'payment_method_display',
            'shipping_address_snapshot',
            'billing_address_snapshot',
            'subtotal',
            'discount_amount',
            'delivery_charge',
            'tax_amount',
            'total_amount',
            'customer_notes',
            'admin_notes',
            'can_cancel',
            'items',
            'status_history',
            'payments',
            'created_at',
            'updated_at',
        ]

    def get_customer_name(self, obj):
        return obj.customer.get_full_name() or obj.customer.username

    def get_can_cancel(self, obj):
        return obj.can_cancel()


class AdminOrderStatusUpdateSerializer(serializers.Serializer):
    order_status = serializers.ChoiceField(
        choices=Order.ORDER_STATUS_CHOICES,
        required=False
    )
    payment_status = serializers.ChoiceField(
        choices=Order.PAYMENT_STATUS_CHOICES,
        required=False
    )
    admin_notes = serializers.CharField(required=False, allow_blank=True, default='')


class InvoiceListSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    customer_type_display = serializers.CharField(source='get_customer_type_display', read_only=True)

    class Meta:
        model = Invoice
        fields = [
            'id',
            'invoice_number',
            'order_number',
            'invoice_date',
            'status',
            'status_display',
            'customer_name',
            'customer_email',
            'customer_type',
            'customer_type_display',
            'business_name',
            'customer_gstin',
            'grand_total',
            'payment_status',
            'payment_method',
            'created_at',
        ]


class InvoiceDetailSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source='order.order_number', read_only=True)
    order_status = serializers.CharField(source='order.order_status', read_only=True)
    order_status_display = serializers.CharField(source='order.get_order_status_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    customer_type_display = serializers.CharField(source='get_customer_type_display', read_only=True)
    items = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            'id',
            'invoice_number',
            'order_number',
            'order_status',
            'order_status_display',
            'invoice_date',
            'status',
            'status_display',
            'company_name',
            'company_address',
            'company_gstin',
            'company_phone',
            'company_email',
            'customer_name',
            'customer_email',
            'customer_phone',
            'customer_type',
            'customer_type_display',
            'business_name',
            'customer_gstin',
            'billing_address',
            'shipping_address',
            'subtotal',
            'discount_amount',
            'tax_rate_percent',
            'cgst_amount',
            'sgst_amount',
            'igst_amount',
            'tax_amount',
            'delivery_charge',
            'grand_total',
            'payment_status',
            'payment_method',
            'payment_reference',
            'notes',
            'items',
            'created_at',
            'updated_at',
        ]

    def get_items(self, obj):
        return OrderItemSerializer(obj.order.items.all(), many=True).data


