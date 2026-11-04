from rest_framework import serializers
from apps.products.models import ProductVariant, Product
from .models import StockItem, ProductionBatch, StockMovement


class StockItemSerializer(serializers.ModelSerializer):
    variant_id = serializers.IntegerField(source='variant.id', read_only=True)
    sku = serializers.CharField(source='variant.sku', read_only=True)
    product_name = serializers.CharField(source='variant.product.name', read_only=True)
    product_slug = serializers.CharField(source='variant.product.slug', read_only=True)
    category_name = serializers.CharField(source='variant.product.category.name', read_only=True)
    package_weight = serializers.DecimalField(source='variant.package_weight', max_digits=8, decimal_places=2, read_only=True)
    package_unit = serializers.CharField(source='variant.package_unit', read_only=True)
    display_weight = serializers.CharField(source='variant.display_weight', read_only=True)
    available_to_sell = serializers.IntegerField(read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    is_out_of_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = StockItem
        fields = [
            'id',
            'variant_id',
            'sku',
            'product_name',
            'product_slug',
            'category_name',
            'package_weight',
            'package_unit',
            'display_weight',
            'quantity_on_hand',
            'reserved_quantity',
            'available_to_sell',
            'low_stock_threshold',
            'is_low_stock',
            'is_out_of_stock',
            'last_reorder_date',
            'updated_at',
        ]


class StockInRequestSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1)
    movement_type = serializers.ChoiceField(
        choices=['production_in', 'purchase_in', 'customer_return'],
        default='production_in'
    )
    batch_id = serializers.IntegerField(required=False, allow_null=True)
    reference_number = serializers.CharField(required=False, allow_blank=True, default='')
    reason = serializers.CharField(required=False, allow_blank=True, default='')


class StockOutRequestSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1)
    movement_type = serializers.ChoiceField(
        choices=['damage', 'expiry', 'adjustment'],
        default='damage'
    )
    batch_id = serializers.IntegerField(required=False, allow_null=True)
    reference_number = serializers.CharField(required=False, allow_blank=True, default='')
    reason = serializers.CharField(required=False, allow_blank=True, default='')


class StockAdjustmentSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField(min_value=1)
    new_quantity_on_hand = serializers.IntegerField(min_value=0)
    reason = serializers.CharField(required=True, min_length=3)


class ProductionBatchSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(source='product.id', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    variant_id = serializers.IntegerField(source='variant.id', read_only=True)
    variant_sku = serializers.CharField(source='variant.sku', read_only=True)
    package_weight = serializers.DecimalField(source='variant.package_weight', max_digits=8, decimal_places=2, read_only=True)
    package_unit = serializers.CharField(source='variant.package_unit', read_only=True)
    display_weight = serializers.CharField(source='variant.display_weight', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    days_until_expiry = serializers.IntegerField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    is_expiring_soon = serializers.SerializerMethodField()
    created_by_email = serializers.CharField(source='created_by.email', read_only=True)

    class Meta:
        model = ProductionBatch
        fields = [
            'id',
            'batch_number',
            'product_id',
            'product_name',
            'variant_id',
            'variant_sku',
            'package_weight',
            'package_unit',
            'display_weight',
            'production_date',
            'expiry_date',
            'manufactured_quantity',
            'remaining_quantity',
            'status',
            'status_display',
            'days_until_expiry',
            'is_expired',
            'is_expiring_soon',
            'is_stock_added',
            'manufacturing_notes',
            'created_by_email',
            'created_at',
            'updated_at',
        ]

    def get_is_expiring_soon(self, obj):
        return obj.is_expiring_soon(warning_days=30)


class ProductionBatchCreateSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField(min_value=1)
    production_date = serializers.DateField()
    expiry_date = serializers.DateField()
    manufactured_quantity = serializers.IntegerField(min_value=1)
    manufacturing_notes = serializers.CharField(required=False, allow_blank=True, default='')
    auto_complete = serializers.BooleanField(default=False)

    def validate(self, attrs):
        if attrs['expiry_date'] <= attrs['production_date']:
            raise serializers.ValidationError({'expiry_date': 'Expiry date must be after production date.'})
        return attrs


class StockMovementSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source='variant.sku', read_only=True)
    product_name = serializers.CharField(source='variant.product.name', read_only=True)
    display_weight = serializers.CharField(source='variant.display_weight', read_only=True)
    batch_number = serializers.CharField(source='batch.batch_number', read_only=True)
    movement_type_display = serializers.CharField(source='get_movement_type_display', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            'id',
            'variant_id',
            'sku',
            'product_name',
            'display_weight',
            'batch_number',
            'movement_type',
            'movement_type_display',
            'quantity',
            'reference_number',
            'reason',
            'balance_after',
            'user_email',
            'created_at',
        ]

