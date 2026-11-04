from rest_framework import serializers
from .models import Category, Product, ProductVariant, QuantityPriceTier, CustomerSpecialPrice


class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(source='active_product_count', read_only=True)

    class Meta:
        model = Category
        fields = [
            'id',
            'name',
            'slug',
            'description',
            'image',
            'is_active',
            'product_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class QuantityPriceTierSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuantityPriceTier
        fields = ['id', 'min_quantity', 'price_per_unit']


class ProductVariantSerializer(serializers.ModelSerializer):
    display_weight = serializers.CharField(read_only=True)
    retail_price = serializers.DecimalField(source='price', max_digits=10, decimal_places=2, read_only=True)
    effective_wholesale_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    price_tiers = QuantityPriceTierSerializer(many=True, read_only=True)

    class Meta:
        model = ProductVariant
        fields = [
            'id',
            'product',
            'sku',
            'package_weight',
            'package_unit',
            'display_weight',
            'price',
            'retail_price',
            'wholesale_price',
            'effective_wholesale_price',
            'minimum_order_quantity',
            'is_available',
            'is_available_retail',
            'is_available_wholesale',
            'price_tiers',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'display_weight',
            'retail_price',
            'effective_wholesale_price',
            'created_at',
            'updated_at',
        ]


class ProductVariantSummarySerializer(serializers.ModelSerializer):
    display_weight = serializers.CharField(read_only=True)
    retail_price = serializers.DecimalField(source='price', max_digits=10, decimal_places=2, read_only=True)
    effective_wholesale_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    price_tiers = QuantityPriceTierSerializer(many=True, read_only=True)

    class Meta:
        model = ProductVariant
        fields = [
            'id',
            'sku',
            'package_weight',
            'package_unit',
            'display_weight',
            'price',
            'retail_price',
            'wholesale_price',
            'effective_wholesale_price',
            'minimum_order_quantity',
            'is_available',
            'is_available_retail',
            'is_available_wholesale',
            'price_tiers',
        ]


class CategorySummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug']


class ProductListSerializer(serializers.ModelSerializer):
    category = CategorySummarySerializer(read_only=True)
    variants = ProductVariantSummarySerializer(source='available_variants', many=True, read_only=True)
    min_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    max_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    min_wholesale_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    max_wholesale_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Product
        fields = [
            'id',
            'name',
            'slug',
            'category',
            'short_description',
            'main_image',
            'is_active',
            'is_featured',
            'min_price',
            'max_price',
            'min_wholesale_price',
            'max_wholesale_price',
            'variants',
            'created_at',
        ]


class ProductDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    variants = ProductVariantSummarySerializer(source='available_variants', many=True, read_only=True)
    all_variants = ProductVariantSerializer(source='variants', many=True, read_only=True)
    min_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    max_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    min_wholesale_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    max_wholesale_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Product
        fields = [
            'id',
            'name',
            'slug',
            'category',
            'short_description',
            'description',
            'main_image',
            'ingredients',
            'shelf_life',
            'is_active',
            'is_featured',
            'min_price',
            'max_price',
            'min_wholesale_price',
            'max_wholesale_price',
            'variants',
            'all_variants',
            'created_at',
            'updated_at',
        ]


class ProductAdminSerializer(serializers.ModelSerializer):
    """
    Serializer used for administrative creation and editing of products.
    """
    class Meta:
        model = Product
        fields = [
            'id',
            'name',
            'slug',
            'category',
            'short_description',
            'description',
            'main_image',
            'ingredients',
            'shelf_life',
            'is_active',
            'is_featured',
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        category = attrs.get('category') or (self.instance.category if self.instance else None)
        is_active = attrs.get('is_active', self.instance.is_active if self.instance else True)
        if is_active and category and not category.is_active:
            raise serializers.ValidationError({
                'category': 'Cannot assign an active product to an inactive category.'
            })
        return attrs


class PricingItemRequestSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField(required=True)
    quantity = serializers.IntegerField(min_value=1, required=True)


class PriceCalculationRequestSerializer(serializers.Serializer):
    items = PricingItemRequestSerializer(many=True, required=True)
