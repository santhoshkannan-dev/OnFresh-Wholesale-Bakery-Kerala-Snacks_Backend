from decimal import Decimal
from rest_framework import serializers
from apps.products.models import Product, ProductVariant
from apps.inventory.models import ProductionBatch
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


class RawMaterialCategorySerializer(serializers.ModelSerializer):
    materials_count = serializers.IntegerField(source='materials.count', read_only=True)

    class Meta:
        model = RawMaterialCategory
        fields = ['id', 'name', 'slug', 'description', 'is_active', 'materials_count', 'created_at']


class RawMaterialMovementSerializer(serializers.ModelSerializer):
    material_code = serializers.CharField(source='material.material_code', read_only=True)
    material_name = serializers.CharField(source='material.name', read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = RawMaterialMovement
        fields = [
            'id', 'material', 'material_code', 'material_name', 'movement_type',
            'quantity', 'unit', 'unit_cost', 'total_cost', 'balance_after',
            'reference_number', 'notes', 'created_by_name', 'created_at'
        ]

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.email
        return 'System'


class RawMaterialSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    is_out_of_stock = serializers.BooleanField(read_only=True)
    total_stock_value = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = RawMaterial
        fields = [
            'id', 'material_code', 'name', 'category', 'category_name',
            'unit_of_measure', 'current_stock', 'minimum_stock_level',
            'reorder_quantity', 'unit_cost', 'storage_location',
            'shelf_life_days', 'is_active', 'notes',
            'is_low_stock', 'is_out_of_stock', 'total_stock_value',
            'created_at', 'updated_at'
        ]


class SupplierMaterialSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source='material.name', read_only=True)
    material_code = serializers.CharField(source='material.material_code', read_only=True)
    unit_of_measure = serializers.CharField(source='material.unit_of_measure', read_only=True)

    class Meta:
        model = SupplierMaterial
        fields = [
            'id', 'supplier', 'material', 'material_name', 'material_code',
            'unit_of_measure', 'supplier_material_code', 'quoted_price',
            'minimum_order_qty', 'is_preferred'
        ]


class SupplierSerializer(serializers.ModelSerializer):
    supplied_materials = SupplierMaterialSerializer(many=True, read_only=True)
    total_orders = serializers.IntegerField(source='purchase_orders.count', read_only=True)

    class Meta:
        model = Supplier
        fields = [
            'id', 'supplier_code', 'name', 'contact_person', 'phone', 'email',
            'address_line1', 'address_line2', 'city', 'state', 'postal_code',
            'country', 'gstin', 'payment_terms', 'lead_time_days',
            'is_active', 'notes', 'supplied_materials', 'total_orders',
            'created_at', 'updated_at'
        ]


class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    material_code = serializers.CharField(source='material.material_code', read_only=True)
    material_name = serializers.CharField(source='material.name', read_only=True)
    unit_of_measure = serializers.CharField(source='material.unit_of_measure', read_only=True)

    class Meta:
        model = PurchaseOrderItem
        fields = [
            'id', 'purchase_order', 'material', 'material_code', 'material_name',
            'unit_of_measure', 'ordered_quantity', 'received_quantity',
            'unit_cost', 'tax_rate', 'total_cost'
        ]
        read_only_fields = ['total_cost']


class SupplierPaymentSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = SupplierPayment
        fields = [
            'id', 'purchase_order', 'payment_number', 'payment_date',
            'amount', 'payment_method', 'reference_number', 'notes',
            'created_by_name', 'created_at'
        ]
        read_only_fields = ['payment_number', 'created_at']

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.email
        return 'System'


class PurchaseOrderSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    supplier_phone = serializers.CharField(source='supplier.phone', read_only=True)
    supplier_gstin = serializers.CharField(source='supplier.gstin', read_only=True)
    items = PurchaseOrderItemSerializer(many=True, read_only=True)
    payments = SupplierPaymentSerializer(many=True, read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'po_number', 'supplier', 'supplier_name', 'supplier_phone', 'supplier_gstin',
            'order_date', 'expected_delivery_date', 'received_date', 'status',
            'subtotal', 'tax_amount', 'total_amount', 'is_stock_added',
            'payment_status', 'amount_paid', 'vendor_invoice_number',
            'notes', 'created_by_name', 'items', 'payments', 'created_at', 'updated_at'
        ]
        read_only_fields = ['po_number', 'subtotal', 'tax_amount', 'total_amount', 'is_stock_added', 'amount_paid']

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.email
        return 'System'


class PurchaseOrderCreateSerializer(serializers.ModelSerializer):
    items = serializers.ListField(child=serializers.DictField(), write_only=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            'supplier', 'order_date', 'expected_delivery_date',
            'notes', 'vendor_invoice_number', 'items'
        ]

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        user = self.context['request'].user if 'request' in self.context else None

        po = PurchaseOrder.objects.create(
            created_by=user,
            **validated_data
        )

        for item_data in items_data:
            material_id = item_data.get('material_id') or item_data.get('material')
            material = RawMaterial.objects.get(id=material_id)
            ordered_qty = Decimal(str(item_data.get('ordered_quantity', 1)))
            unit_cost = Decimal(str(item_data.get('unit_cost', material.unit_cost)))
            tax_rate = Decimal(str(item_data.get('tax_rate', 0)))

            PurchaseOrderItem.objects.create(
                purchase_order=po,
                material=material,
                ordered_quantity=ordered_qty,
                received_quantity=Decimal('0.000'),
                unit_cost=unit_cost,
                tax_rate=tax_rate
            )

        po.recalculate_totals()
        return po


class RecipeIngredientSerializer(serializers.ModelSerializer):
    material_code = serializers.CharField(source='material.material_code', read_only=True)
    material_name = serializers.CharField(source='material.name', read_only=True)
    unit_cost = serializers.DecimalField(source='material.unit_cost', max_digits=10, decimal_places=2, read_only=True)
    effective_quantity = serializers.DecimalField(max_digits=10, decimal_places=3, read_only=True)
    effective_cost = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = RecipeIngredient
        fields = [
            'id', 'recipe', 'material', 'material_code', 'material_name',
            'quantity', 'unit', 'wastage_percentage', 'unit_cost',
            'effective_quantity', 'effective_cost'
        ]


class RecipePackagingSerializer(serializers.ModelSerializer):
    material_code = serializers.CharField(source='packaging_material.material_code', read_only=True)
    material_name = serializers.CharField(source='packaging_material.name', read_only=True)
    unit_cost = serializers.DecimalField(source='packaging_material.unit_cost', max_digits=10, decimal_places=2, read_only=True)
    effective_cost = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = RecipePackaging
        fields = [
            'id', 'recipe', 'packaging_material', 'material_code', 'material_name',
            'quantity', 'unit', 'notes', 'unit_cost', 'effective_cost'
        ]


class RecipeSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    variant_sku = serializers.CharField(source='variant.sku', read_only=True, allow_null=True)
    variant_weight = serializers.CharField(source='variant.package_weight', read_only=True, allow_null=True)
    ingredients = RecipeIngredientSerializer(many=True, read_only=True)
    packaging_materials = RecipePackagingSerializer(many=True, read_only=True)
    estimated_raw_material_cost = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    estimated_packaging_cost = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    estimated_total_cost = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    estimated_cost_per_unit = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Recipe
        fields = [
            'id', 'recipe_code', 'name', 'product', 'product_name', 'variant',
            'variant_sku', 'variant_weight', 'version', 'is_active',
            'batch_output_quantity', 'output_unit', 'target_variant_units',
            'estimated_labor_cost', 'estimated_overhead_cost',
            'instructions', 'notes', 'ingredients', 'packaging_materials',
            'estimated_raw_material_cost', 'estimated_packaging_cost',
            'estimated_total_cost', 'estimated_cost_per_unit',
            'created_at', 'updated_at'
        ]


class RecipeCreateUpdateSerializer(serializers.ModelSerializer):
    ingredients = serializers.ListField(child=serializers.DictField(), write_only=True, required=False)
    packaging_materials = serializers.ListField(child=serializers.DictField(), write_only=True, required=False)

    class Meta:
        model = Recipe
        fields = [
            'product', 'variant', 'recipe_code', 'name', 'version', 'is_active',
            'batch_output_quantity', 'output_unit', 'target_variant_units',
            'estimated_labor_cost', 'estimated_overhead_cost',
            'instructions', 'notes', 'ingredients', 'packaging_materials'
        ]

    def create(self, validated_data):
        ingredients_data = validated_data.pop('ingredients', [])
        packaging_data = validated_data.pop('packaging_materials', [])

        recipe = Recipe.objects.create(**validated_data)

        for ing in ingredients_data:
            mat_id = ing.get('material_id') or ing.get('material')
            material = RawMaterial.objects.get(id=mat_id)
            RecipeIngredient.objects.create(
                recipe=recipe,
                material=material,
                quantity=Decimal(str(ing.get('quantity', 1))),
                unit=ing.get('unit', material.unit_of_measure),
                wastage_percentage=Decimal(str(ing.get('wastage_percentage', 0)))
            )

        for pkg in packaging_data:
            pkg_id = pkg.get('packaging_material_id') or pkg.get('packaging_material') or pkg.get('material_id')
            material = RawMaterial.objects.get(id=pkg_id)
            RecipePackaging.objects.create(
                recipe=recipe,
                packaging_material=material,
                quantity=Decimal(str(pkg.get('quantity', 1))),
                unit=pkg.get('unit', 'pcs'),
                notes=pkg.get('notes', '')
            )

        return recipe


class ProductionMaterialConsumptionSerializer(serializers.ModelSerializer):
    material_code = serializers.CharField(source='material.material_code', read_only=True)
    material_name = serializers.CharField(source='material.name', read_only=True)

    class Meta:
        model = ProductionMaterialConsumption
        fields = [
            'id', 'production_order', 'material', 'material_code', 'material_name',
            'planned_quantity', 'actual_quantity', 'wastage_quantity', 'unit',
            'unit_cost', 'total_cost'
        ]


class ProductionPackagingConsumptionSerializer(serializers.ModelSerializer):
    material_code = serializers.CharField(source='material.material_code', read_only=True)
    material_name = serializers.CharField(source='material.name', read_only=True)

    class Meta:
        model = ProductionPackagingConsumption
        fields = [
            'id', 'production_order', 'material', 'material_code', 'material_name',
            'planned_quantity', 'actual_quantity', 'wastage_quantity', 'unit',
            'unit_cost', 'total_cost'
        ]


class QualityInspectionSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source='production_order.order_number', read_only=True)
    batch_number = serializers.CharField(source='production_batch.batch_number', read_only=True, allow_null=True)
    inspector_name = serializers.SerializerMethodField()

    class Meta:
        model = QualityInspection
        fields = [
            'id', 'inspection_number', 'production_order', 'order_number',
            'production_batch', 'batch_number', 'inspector', 'inspector_name',
            'inspection_date', 'sample_size', 'appearance_status',
            'taste_crispness_status', 'moisture_status', 'packaging_seal_status',
            'label_batch_verification', 'overall_result', 'release_status',
            'defect_notes', 'corrective_actions', 'created_at', 'updated_at'
        ]
        read_only_fields = ['inspection_number', 'created_at']

    def get_inspector_name(self, obj):
        if obj.inspector:
            return obj.inspector.get_full_name() or obj.inspector.email
        return 'QC Staff'


class ProductionOrderSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    variant_sku = serializers.CharField(source='variant.sku', read_only=True)
    variant_weight = serializers.CharField(source='variant.package_weight', read_only=True)
    recipe_code = serializers.CharField(source='recipe.recipe_code', read_only=True)
    recipe_name = serializers.CharField(source='recipe.name', read_only=True)
    batch_number = serializers.CharField(source='production_batch.batch_number', read_only=True, allow_null=True)
    batch_status = serializers.CharField(source='production_batch.status', read_only=True, allow_null=True)
    material_consumptions = ProductionMaterialConsumptionSerializer(many=True, read_only=True)
    packaging_consumptions = ProductionPackagingConsumptionSerializer(many=True, read_only=True)
    inspections = QualityInspectionSerializer(many=True, read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ProductionOrder
        fields = [
            'id', 'order_number', 'recipe', 'recipe_code', 'recipe_name',
            'product', 'product_name', 'variant', 'variant_sku', 'variant_weight',
            'planned_quantity', 'produced_quantity', 'rejected_quantity',
            'start_date', 'completion_date', 'status',
            'raw_material_cost', 'packaging_cost', 'labor_cost', 'overhead_cost',
            'total_production_cost', 'cost_per_unit', 'notes',
            'created_by_name', 'production_batch', 'batch_number', 'batch_status',
            'material_consumptions', 'packaging_consumptions', 'inspections',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'order_number', 'raw_material_cost', 'packaging_cost',
            'total_production_cost', 'cost_per_unit', 'production_batch'
        ]

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.email
        return 'System'

