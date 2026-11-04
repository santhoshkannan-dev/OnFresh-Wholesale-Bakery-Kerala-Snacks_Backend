from django.db import models
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from apps.products.models import ProductVariant
from .models import StockItem, ProductionBatch, StockMovement
from .services import InventoryService
from .serializers import (
    StockItemSerializer,
    StockInRequestSerializer,
    StockOutRequestSerializer,
    StockAdjustmentSerializer,
    ProductionBatchSerializer,
    ProductionBatchCreateSerializer,
    StockMovementSerializer,
)


class StockItemListView(generics.ListAPIView):
    """
    List inventory status for all product packaging variants.
    Supports filtering by low_stock, out_of_stock, category, and search query.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = StockItemSerializer

    def get_queryset(self):
        # Automatically provision StockItem records for any variants that do not yet have one
        existing_variant_ids = set(StockItem.objects.values_list('variant_id', flat=True))
        all_variants = ProductVariant.objects.exclude(id__in=existing_variant_ids)
        for var in all_variants:
            StockItem.objects.create(variant=var, quantity_on_hand=0, reserved_quantity=0, low_stock_threshold=20)

        qs = StockItem.objects.select_related('variant__product__category').all()

        search = self.request.query_params.get('search')
        low_stock = self.request.query_params.get('low_stock')
        out_of_stock = self.request.query_params.get('out_of_stock')
        category_slug = self.request.query_params.get('category')

        if search:
            qs = qs.filter(
                models.Q(variant__sku__icontains=search) |
                models.Q(variant__product__name__icontains=search)
            )

        if category_slug:
            qs = qs.filter(variant__product__category__slug=category_slug)

        if low_stock == 'true':
            # available_to_sell <= low_stock_threshold and available_to_sell > 0
            qs = [s for s in qs if s.is_low_stock]
            return qs

        if out_of_stock == 'true':
            qs = [s for s in qs if s.is_out_of_stock]
            return qs

        return qs


class StockItemDetailView(APIView):
    """
    Retrieve inventory detail, active batches, and recent stock movements for a variant.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, variant_id):
        variant = get_object_or_404(ProductVariant.objects.select_related('product'), id=variant_id)
        stock = InventoryService.get_or_create_stock_item(variant)

        stock_data = StockItemSerializer(stock).data
        batches = ProductionBatch.objects.filter(variant=variant, remaining_quantity__gt=0).order_by('expiry_date')
        movements = StockMovement.objects.filter(variant=variant).order_by('-created_at')[:10]

        return Response({
            'stock': stock_data,
            'active_batches': ProductionBatchSerializer(batches, many=True).data,
            'recent_movements': StockMovementSerializer(movements, many=True).data,
        })


class StockInView(APIView):
    """
    Record incoming stock from kitchen production or external supply.
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = StockInRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'status': 'error', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        variant = get_object_or_404(ProductVariant, id=data['variant_id'])
        batch = None
        if data.get('batch_id'):
            batch = ProductionBatch.objects.filter(id=data['batch_id']).first()

        stock = InventoryService.record_stock_in(
            variant=variant,
            quantity=data['quantity'],
            movement_type=data.get('movement_type', 'production_in'),
            batch=batch,
            reference=data.get('reference_number', ''),
            reason=data.get('reason', ''),
            user=request.user
        )

        return Response({
            'status': 'success',
            'message': f"Added {data['quantity']} units to {variant.sku}.",
            'stock': StockItemSerializer(stock).data
        }, status=status.HTTP_200_OK)


class StockOutView(APIView):
    """
    Record stock deduction due to damage, expiry, or manual write-off.
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = StockOutRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'status': 'error', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        variant = get_object_or_404(ProductVariant, id=data['variant_id'])
        batch = None
        if data.get('batch_id'):
            batch = ProductionBatch.objects.filter(id=data['batch_id']).first()

        try:
            stock = InventoryService.record_stock_out(
                variant=variant,
                quantity=data['quantity'],
                movement_type=data.get('movement_type', 'damage'),
                batch=batch,
                reference=data.get('reference_number', ''),
                reason=data.get('reason', ''),
                user=request.user
            )
            return Response({
                'status': 'success',
                'message': f"Removed {data['quantity']} units from {variant.sku}.",
                'stock': StockItemSerializer(stock).data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class StockAdjustmentView(APIView):
    """
    Adjust inventory count to match physical count during warehouse audits.
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = StockAdjustmentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'status': 'error', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        variant = get_object_or_404(ProductVariant, id=data['variant_id'])

        try:
            stock = InventoryService.record_stock_adjustment(
                variant=variant,
                new_quantity_on_hand=data['new_quantity_on_hand'],
                reason=data['reason'],
                user=request.user
            )
            return Response({
                'status': 'success',
                'message': f"Adjusted stock for {variant.sku} to {data['new_quantity_on_hand']} units.",
                'stock': StockItemSerializer(stock).data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class StockMovementListView(generics.ListAPIView):
    """
    Audit log of all stock movements and inventory ledger transactions.
    """
    permission_classes = [IsAdminUser]
    serializer_class = StockMovementSerializer

    def get_queryset(self):
        qs = StockMovement.objects.select_related('variant__product', 'batch', 'user').all()

        m_type = self.request.query_params.get('movement_type')
        variant_id = self.request.query_params.get('variant_id')
        ref = self.request.query_params.get('reference')

        if m_type:
            qs = qs.filter(movement_type=m_type)
        if variant_id:
            qs = qs.filter(variant_id=variant_id)
        if ref:
            qs = qs.filter(reference_number__icontains=ref)

        return qs


class ProductionBatchListCreateView(APIView):
    """
    List and create production batches for bakery snacks manufacturing.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = ProductionBatch.objects.select_related('product', 'variant', 'created_by').all()

        status_param = request.query_params.get('status')
        variant_id = request.query_params.get('variant_id')
        expiring_soon = request.query_params.get('expiring_soon')
        expired = request.query_params.get('expired')

        if status_param:
            qs = qs.filter(status=status_param)
        if variant_id:
            qs = qs.filter(variant_id=variant_id)

        if expired == 'true':
            qs = [b for b in qs if b.is_expired]
        elif expiring_soon == 'true':
            qs = [b for b in qs if b.is_expiring_soon(30)]

        serializer = ProductionBatchSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request):
        if not request.user.is_staff:
            return Response({'status': 'error', 'message': 'Staff authorization required.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = ProductionBatchCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'status': 'error', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        variant = get_object_or_404(ProductVariant.objects.select_related('product'), id=data['variant_id'])

        batch = ProductionBatch.objects.create(
            product=variant.product,
            variant=variant,
            production_date=data['production_date'],
            expiry_date=data['expiry_date'],
            manufactured_quantity=data['manufactured_quantity'],
            remaining_quantity=0,
            status='in_production',
            manufacturing_notes=data.get('manufacturing_notes', ''),
            created_by=request.user
        )

        if data.get('auto_complete', False):
            batch = InventoryService.complete_production_batch(batch, user=request.user)

        return Response(ProductionBatchSerializer(batch).data, status=status.HTTP_201_CREATED)


class ProductionBatchDetailView(APIView):
    """
    Retrieve single production batch by batch number.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, batch_number):
        batch = get_object_or_404(
            ProductionBatch.objects.select_related('product', 'variant', 'created_by'),
            batch_number=batch_number
        )
        return Response(ProductionBatchSerializer(batch).data)


class ProductionBatchCompleteView(APIView):
    """
    Mark a production batch completed and add manufactured quantities to inventory.
    """
    permission_classes = [IsAdminUser]

    def post(self, request, batch_number):
        batch = get_object_or_404(ProductionBatch, batch_number=batch_number)
        batch = InventoryService.complete_production_batch(batch, user=request.user)
        return Response({
            'status': 'success',
            'message': f"Batch {batch.batch_number} completed and {batch.manufactured_quantity} units added to stock.",
            'batch': ProductionBatchSerializer(batch).data
        })


class ExpiryReportView(APIView):
    """
    Report showing batches expiring soon (within 30 days) and expired batches.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        warning_days = int(request.query_params.get('warning_days', 30))
        all_active_batches = ProductionBatch.objects.select_related('product', 'variant').filter(
            remaining_quantity__gt=0
        ).order_by('expiry_date')

        expired = [b for b in all_active_batches if b.is_expired]
        expiring_soon = [b for b in all_active_batches if b.is_expiring_soon(warning_days)]

        return Response({
            'warning_threshold_days': warning_days,
            'expiring_soon_count': len(expiring_soon),
            'expired_count': len(expired),
            'expiring_soon_batches': ProductionBatchSerializer(expiring_soon, many=True).data,
            'expired_batches': ProductionBatchSerializer(expired, many=True).data,
        })


class InventoryReportSummaryView(APIView):
    """
    Comprehensive reporting endpoint for executive inventory overview.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        stock_items = list(StockItem.objects.select_related('variant__product').all())
        batches = list(ProductionBatch.objects.filter(remaining_quantity__gt=0))

        total_skus = len(stock_items)
        total_units_on_hand = sum(s.quantity_on_hand for s in stock_items)
        total_reserved_units = sum(s.reserved_quantity for s in stock_items)
        total_available_units = sum(s.available_to_sell for s in stock_items)
        low_stock_count = sum(1 for s in stock_items if s.is_low_stock)
        out_of_stock_count = sum(1 for s in stock_items if s.is_out_of_stock)

        expiring_batches_count = sum(1 for b in batches if b.is_expiring_soon(30))
        expired_batches_count = sum(1 for b in batches if b.is_expired)

        # Recent 30 days movements
        thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
        recent_in = StockMovement.objects.filter(
            movement_type__in=['production_in', 'purchase_in', 'customer_return'],
            created_at__gte=thirty_days_ago
        ).aggregate(total=models.Sum('quantity'))['total'] or 0

        recent_out = StockMovement.objects.filter(
            movement_type__in=['order_dispatch', 'damage', 'expiry'],
            created_at__gte=thirty_days_ago
        ).aggregate(total=models.Sum('quantity'))['total'] or 0

        return Response({
            'total_skus': total_skus,
            'total_units_on_hand': total_units_on_hand,
            'total_reserved_units': total_reserved_units,
            'total_available_units': total_available_units,
            'low_stock_count': low_stock_count,
            'out_of_stock_count': out_of_stock_count,
            'expiring_batches_count': expiring_batches_count,
            'expired_batches_count': expired_batches_count,
            'last_30_days_stock_in': recent_in,
            'last_30_days_stock_out': recent_out,
        })

