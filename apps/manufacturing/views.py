from decimal import Decimal
from django.db.models import Q, Sum, F, Count
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.accounts.roles import (
    IsStaffUser,
    IsProductionStaff,
    IsPurchaseStaff,
    IsQualityStaff,
    IsInventoryStaff
)
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
    ProductionOrder,
    QualityInspection,
)
from .serializers import (
    RawMaterialCategorySerializer,
    RawMaterialSerializer,
    RawMaterialMovementSerializer,
    SupplierSerializer,
    SupplierMaterialSerializer,
    PurchaseOrderSerializer,
    PurchaseOrderCreateSerializer,
    SupplierPaymentSerializer,
    RecipeSerializer,
    RecipeCreateUpdateSerializer,
    ProductionOrderSerializer,
    QualityInspectionSerializer,
)
from .services import (
    RawMaterialService,
    PurchaseService,
    ProductionService,
    QualityService,
)


class RawMaterialCategoryViewSet(viewsets.ModelViewSet):
    queryset = RawMaterialCategory.objects.all().order_by('name')
    serializer_class = RawMaterialCategorySerializer
    permission_classes = [IsAuthenticated, IsStaffUser]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'description']


class RawMaterialViewSet(viewsets.ModelViewSet):
    queryset = RawMaterial.objects.select_related('category').all().order_by('category__name', 'name')
    serializer_class = RawMaterialSerializer
    permission_classes = [IsAuthenticated, IsInventoryStaff]
    filter_backends = [filters.SearchFilter]
    search_fields = ['material_code', 'name', 'storage_location', 'category__name']

    def get_queryset(self):
        qs = super().get_queryset()
        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(Q(category__slug=category) | Q(category__id=category))

        unit = self.request.query_params.get('unit')
        if unit:
            qs = qs.filter(unit_of_measure=unit)

        low_stock = self.request.query_params.get('low_stock')
        if low_stock and low_stock.lower() in ['true', '1', 'yes']:
            qs = qs.filter(current_stock__lte=F('minimum_stock_level'), current_stock__gt=0)

        out_of_stock = self.request.query_params.get('out_of_stock')
        if out_of_stock and out_of_stock.lower() in ['true', '1', 'yes']:
            qs = qs.filter(current_stock__lte=0)

        return qs

    @action(detail=True, methods=['post'])
    def adjust_stock(self, request, pk=None):
        """
        Record physical stock count audit adjustment.
        """
        material = self.get_object()
        new_quantity = request.data.get('new_quantity')
        notes = request.data.get('notes', 'Physical audit adjustment')

        if new_quantity is None:
            return Response(
                {'error': 'new_quantity is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            new_qty = Decimal(str(new_quantity))
            updated_mat = RawMaterialService.record_adjustment(
                material=material,
                new_quantity=new_qty,
                notes=notes,
                user=request.user
            )
            return Response(RawMaterialSerializer(updated_mat).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def movements(self, request, pk=None):
        material = self.get_object()
        movements = material.movements.all()[:100]
        serializer = RawMaterialMovementSerializer(movements, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        low_materials = RawMaterial.objects.filter(
            current_stock__lte=F('minimum_stock_level')
        ).order_by('current_stock')
        return Response(RawMaterialSerializer(low_materials, many=True).data)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        total_items = RawMaterial.objects.filter(is_active=True).count()
        low_stock_count = RawMaterial.objects.filter(
            is_active=True,
            current_stock__lte=F('minimum_stock_level'),
            current_stock__gt=0
        ).count()
        out_of_stock_count = RawMaterial.objects.filter(
            is_active=True,
            current_stock__lte=0
        ).count()

        total_value = sum(
            m.total_stock_value for m in RawMaterial.objects.filter(is_active=True)
        )

        return Response({
            'total_items': total_items,
            'low_stock_count': low_stock_count,
            'out_of_stock_count': out_of_stock_count,
            'total_valuation': float(total_value),
        })


class RawMaterialMovementListView(APIView):
    permission_classes = [IsAuthenticated, IsInventoryStaff]

    def get(self, request):
        movements = RawMaterialMovement.objects.select_related('material', 'created_by').all()

        material_id = request.query_params.get('material_id')
        if material_id:
            movements = movements.filter(material_id=material_id)

        movement_type = request.query_params.get('movement_type')
        if movement_type:
            movements = movements.filter(movement_type=movement_type)

        return Response(RawMaterialMovementSerializer(movements[:100], many=True).data)


class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.prefetch_related('supplied_materials__material').all().order_by('name')
    serializer_class = SupplierSerializer
    permission_classes = [IsAuthenticated, IsPurchaseStaff]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'supplier_code', 'contact_person', 'phone', 'email', 'gstin', 'city']

    @action(detail=True, methods=['post'])
    def assign_material(self, request, pk=None):
        supplier = self.get_object()
        material_id = request.data.get('material_id')
        quoted_price = request.data.get('quoted_price', 0)
        minimum_order_qty = request.data.get('minimum_order_qty', 1)
        supplier_material_code = request.data.get('supplier_material_code', '')
        is_preferred = request.data.get('is_preferred', False)

        if not material_id:
            return Response({'error': 'material_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        material = get_object_or_404(RawMaterial, id=material_id)
        supplier_mat, created = SupplierMaterial.objects.update_or_create(
            supplier=supplier,
            material=material,
            defaults={
                'quoted_price': Decimal(str(quoted_price)),
                'minimum_order_qty': Decimal(str(minimum_order_qty)),
                'supplier_material_code': supplier_material_code,
                'is_preferred': is_preferred,
            }
        )
        return Response(SupplierMaterialSerializer(supplier_mat).data)


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    queryset = PurchaseOrder.objects.select_related('supplier', 'created_by').prefetch_related('items__material', 'payments').all().order_by('-order_date', '-created_at')
    permission_classes = [IsAuthenticated, IsPurchaseStaff]
    filter_backends = [filters.SearchFilter]
    search_fields = ['po_number', 'supplier__name', 'vendor_invoice_number']

    def get_serializer_class(self):
        if self.action == 'create':
            return PurchaseOrderCreateSerializer
        return PurchaseOrderSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        supplier_id = self.request.query_params.get('supplier')
        if supplier_id:
            qs = qs.filter(supplier_id=supplier_id)
        return qs

    @action(detail=True, methods=['post'])
    def receive(self, request, pk=None):
        """
        Idempotent goods receipt: credits raw material stock and logs movements.
        """
        po = self.get_object()
        received_items = request.data.get('items', [])
        invoice_number = request.data.get('vendor_invoice_number', '')

        try:
            updated_po = PurchaseService.receive_purchase_order(
                purchase_order=po,
                received_items=received_items,
                vendor_invoice_number=invoice_number,
                user=request.user
            )
            return Response(PurchaseOrderSerializer(updated_po).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def record_payment(self, request, pk=None):
        po = self.get_object()
        amount = request.data.get('amount')
        payment_method = request.data.get('payment_method', 'bank_transfer')
        reference_number = request.data.get('reference_number', '')
        notes = request.data.get('notes', '')

        if not amount:
            return Response({'error': 'amount is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payment = PurchaseService.record_supplier_payment(
                purchase_order=po,
                amount=Decimal(str(amount)),
                payment_method=payment_method,
                reference_number=reference_number,
                notes=notes,
                user=request.user
            )
            return Response(SupplierPaymentSerializer(payment).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        po = self.get_object()
        if po.is_stock_added:
            return Response({'error': 'Cannot cancel PO after stock has already been received.'}, status=status.HTTP_400_BAD_REQUEST)
        po.status = 'cancelled'
        po.save(update_fields=['status', 'updated_at'])
        return Response(PurchaseOrderSerializer(po).data)


class RecipeViewSet(viewsets.ModelViewSet):
    queryset = Recipe.objects.select_related('product', 'variant').prefetch_related(
        'ingredients__material',
        'packaging_materials__packaging_material'
    ).all().order_by('product__name', '-version')
    permission_classes = [IsAuthenticated, IsProductionStaff]
    filter_backends = [filters.SearchFilter]
    search_fields = ['recipe_code', 'name', 'product__name', 'variant__sku']

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return RecipeCreateUpdateSerializer
        return RecipeSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        product_id = self.request.query_params.get('product')
        if product_id:
            qs = qs.filter(product_id=product_id)
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() in ['true', '1', 'yes'])
        return qs

    @action(detail=True, methods=['get'])
    def check_availability(self, request, pk=None):
        """
        Check ingredient and packaging inventory availability for a planned batch volume.
        """
        recipe = self.get_object()
        units = request.query_params.get('target_units') or recipe.target_variant_units or 100
        try:
            target_units = int(units)
            data = ProductionService.check_ingredient_availability(recipe, target_units)
            return Response(data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ProductionOrderViewSet(viewsets.ModelViewSet):
    queryset = ProductionOrder.objects.select_related(
        'recipe', 'product', 'variant', 'production_batch', 'created_by'
    ).prefetch_related(
        'material_consumptions__material',
        'packaging_consumptions__material',
        'inspections'
    ).all().order_by('-start_date', '-created_at')
    serializer_class = ProductionOrderSerializer
    permission_classes = [IsAuthenticated, IsProductionStaff]
    filter_backends = [filters.SearchFilter]
    search_fields = ['order_number', 'product__name', 'variant__sku', 'recipe__name']

    def get_queryset(self):
        qs = super().get_queryset()
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    def create(self, request, *args, **kwargs):
        recipe_id = request.data.get('recipe')
        planned_quantity = request.data.get('planned_quantity')
        start_date = request.data.get('start_date')
        notes = request.data.get('notes', '')

        if not recipe_id or not planned_quantity:
            return Response(
                {'error': 'recipe and planned_quantity are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        recipe = get_object_or_404(Recipe, id=recipe_id)
        try:
            order = ProductionService.create_production_order(
                recipe=recipe,
                planned_quantity=int(planned_quantity),
                start_date=start_date,
                notes=notes,
                user=request.user
            )
            return Response(ProductionOrderSerializer(order).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        order = self.get_object()
        if order.status != 'planned':
            return Response({'error': f'Order cannot be approved from status {order.status}.'}, status=status.HTTP_400_BAD_REQUEST)
        order.status = 'approved'
        order.save(update_fields=['status', 'updated_at'])
        return Response(ProductionOrderSerializer(order).data)

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        order = self.get_object()
        if order.status not in ['planned', 'approved']:
            return Response({'error': f'Order cannot be started from status {order.status}.'}, status=status.HTTP_400_BAD_REQUEST)
        order.status = 'in_progress'
        order.save(update_fields=['status', 'updated_at'])
        return Response(ProductionOrderSerializer(order).data)

    @action(detail=True, methods=['post'])
    def execute_run(self, request, pk=None):
        """
        Record actual cooking & packaging consumption, deduct raw inventory,
        calculate true costs, and move to QC inspection stage.
        """
        order = self.get_object()
        produced_quantity = request.data.get('produced_quantity')
        rejected_quantity = request.data.get('rejected_quantity', 0)
        actual_consumptions = request.data.get('material_consumptions', [])
        actual_packagings = request.data.get('packaging_consumptions', [])
        expiry_date = request.data.get('expiry_date')

        if not produced_quantity:
            return Response({'error': 'produced_quantity is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            updated_order, batch = ProductionService.execute_and_send_to_qc(
                production_order=order,
                produced_quantity=int(produced_quantity),
                rejected_quantity=int(rejected_quantity),
                actual_consumptions=actual_consumptions,
                actual_packagings=actual_packagings,
                expiry_date=expiry_date,
                user=request.user
            )
            return Response(ProductionOrderSerializer(updated_order).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        order = self.get_object()
        if order.status in ['completed', 'quality_check']:
            return Response({'error': 'Cannot cancel order after production execution.'}, status=status.HTTP_400_BAD_REQUEST)
        order.status = 'cancelled'
        order.save(update_fields=['status', 'updated_at'])
        return Response(ProductionOrderSerializer(order).data)


class QualityInspectionViewSet(viewsets.ModelViewSet):
    queryset = QualityInspection.objects.select_related(
        'production_order', 'production_batch', 'inspector'
    ).all().order_by('-inspection_date', '-created_at')
    serializer_class = QualityInspectionSerializer
    permission_classes = [IsAuthenticated, IsQualityStaff]
    filter_backends = [filters.SearchFilter]
    search_fields = ['inspection_number', 'production_order__order_number', 'production_batch__batch_number']

    @action(detail=False, methods=['post'])
    def inspect(self, request):
        """
        Perform quality inspection and release / quarantine batch.
        """
        order_id = request.data.get('production_order')
        sample_size = request.data.get('sample_size', 5)
        appearance_status = request.data.get('appearance_status', 'pass')
        taste_crispness_status = request.data.get('taste_crispness_status', 'pass')
        moisture_status = request.data.get('moisture_status', 'pass')
        packaging_seal_status = request.data.get('packaging_seal_status', 'pass')
        label_batch_verification = request.data.get('label_batch_verification', 'pass')
        overall_result = request.data.get('overall_result')
        defect_notes = request.data.get('defect_notes', '')
        corrective_actions = request.data.get('corrective_actions', '')

        if not order_id or not overall_result:
            return Response(
                {'error': 'production_order and overall_result are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        order = get_object_or_404(ProductionOrder, id=order_id)
        try:
            inspection = QualityService.process_inspection(
                production_order=order,
                sample_size=int(sample_size),
                appearance_status=appearance_status,
                taste_crispness_status=taste_crispness_status,
                moisture_status=moisture_status,
                packaging_seal_status=packaging_seal_status,
                label_batch_verification=label_batch_verification,
                overall_result=overall_result,
                defect_notes=defect_notes,
                corrective_actions=corrective_actions,
                inspector=request.user
            )
            return Response(QualityInspectionSerializer(inspection).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ManufacturingDashboardView(APIView):
    """
    Overview statistics for the Manufacturing & Production operations in Vandiperiyar.
    """
    permission_classes = [IsAuthenticated, IsStaffUser]

    def get(self, request):
        total_raw_materials = RawMaterial.objects.filter(is_active=True).count()
        low_stock_materials = RawMaterial.objects.filter(
            is_active=True,
            current_stock__lte=F('minimum_stock_level'),
            current_stock__gt=0
        ).count()
        out_of_stock_materials = RawMaterial.objects.filter(
            is_active=True,
            current_stock__lte=0
        ).count()
        total_valuation = sum(
            m.total_stock_value for m in RawMaterial.objects.filter(is_active=True)
        )

        active_production_orders = ProductionOrder.objects.filter(
            status__in=['planned', 'approved', 'in_progress', 'quality_check']
        ).count()
        completed_orders_count = ProductionOrder.objects.filter(status='completed').count()
        pending_qc_count = ProductionOrder.objects.filter(status='quality_check').count()

        pending_pos_count = PurchaseOrder.objects.filter(
            status__in=['draft', 'ordered', 'partially_received']
        ).count()

        recent_orders = ProductionOrder.objects.select_related(
            'product', 'variant', 'recipe'
        ).order_by('-created_at')[:6]

        low_stock_items = RawMaterial.objects.filter(
            current_stock__lte=F('minimum_stock_level')
        ).order_by('current_stock')[:6]

        recent_qc = QualityInspection.objects.select_related(
            'production_order', 'inspector'
        ).order_by('-inspection_date')[:6]

        return Response({
            'kpis': {
                'total_raw_materials': total_raw_materials,
                'low_stock_materials': low_stock_materials,
                'out_of_stock_materials': out_of_stock_materials,
                'total_raw_valuation': float(total_valuation),
                'active_production_orders': active_production_orders,
                'completed_orders_count': completed_orders_count,
                'pending_qc_count': pending_qc_count,
                'pending_purchase_orders': pending_pos_count,
            },
            'recent_production_orders': ProductionOrderSerializer(recent_orders, many=True).data,
            'low_stock_materials': RawMaterialSerializer(low_stock_items, many=True).data,
            'recent_quality_inspections': QualityInspectionSerializer(recent_qc, many=True).data,
        })

