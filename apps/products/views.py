from rest_framework import viewsets, filters, status
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import BasePermission, SAFE_METHODS, AllowAny
from django.db.models import Prefetch, Min
from .models import Category, Product, ProductVariant
from .serializers import (
    CategorySerializer,
    ProductListSerializer,
    ProductDetailSerializer,
    ProductAdminSerializer,
    ProductVariantSerializer,
    PriceCalculationRequestSerializer,
)


class IsAdminOrReadOnly(BasePermission):
    """
    Allow read-only requests for any user, but restrict
    create, update, and delete actions to admin/staff users.
    """
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_staff)


class CategoryViewSet(viewsets.ModelViewSet):
    """
    API endpoint for Categories.
    - Public: lists active categories
    - Admin: can list, create, update, deactivate
    """
    lookup_field = 'slug'
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = CategorySerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    def get_queryset(self):
        # Admin can view all categories; public users see only active categories
        if self.request.user and self.request.user.is_staff:
            return Category.objects.all()
        return Category.objects.filter(is_active=True)


class ProductViewSet(viewsets.ModelViewSet):
    """
    API endpoint for Products.
    - Public: lists active products belonging to active categories
    - Admin: can manage full product catalogue
    - Supports filtering by category slug, is_featured, search, and sorting
    """
    lookup_field = 'slug'
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description', 'short_description', 'ingredients']
    ordering_fields = ['created_at', 'name', 'min_price']
    ordering = ['-is_featured', '-created_at']

    def get_queryset(self):
        # Base prefetch for performance
        variants_prefetch = Prefetch(
            'variants',
            queryset=ProductVariant.objects.all().order_by('package_weight')
        )

        queryset = Product.objects.select_related('category').prefetch_related(variants_prefetch)

        # Non-staff users see only active products in active categories
        if not (self.request.user and self.request.user.is_staff):
            queryset = queryset.filter(is_active=True, category__is_active=True)

        # Filter by category slug
        category_slug = self.request.query_params.get('category')
        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)

        # Filter by customer segment if requested (retail or wholesale)
        segment = self.request.query_params.get('segment')
        if segment == 'retail':
            queryset = queryset.filter(variants__is_available_retail=True).distinct()
        elif segment == 'wholesale':
            queryset = queryset.filter(variants__is_available_wholesale=True).distinct()

        # Filter by is_featured
        is_featured = self.request.query_params.get('is_featured')
        if is_featured is not None:
            if is_featured.lower() in ('true', '1', 'yes'):
                queryset = queryset.filter(is_featured=True)
            elif is_featured.lower() in ('false', '0', 'no'):
                queryset = queryset.filter(is_featured=False)

        # Ordering by price annotation if requested
        sort_by = self.request.query_params.get('ordering')
        if sort_by in ('min_price', '-min_price', 'price', '-price'):
            queryset = queryset.annotate(annotated_min_price=Min('variants__price'))
            if sort_by.startswith('-'):
                queryset = queryset.order_by('-annotated_min_price')
            else:
                queryset = queryset.order_by('annotated_min_price')

        return queryset

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ProductDetailSerializer
        elif self.action in ('create', 'update', 'partial_update'):
            return ProductAdminSerializer
        return ProductListSerializer

    @action(detail=True, methods=['get'], permission_classes=[IsAdminOrReadOnly])
    def variants(self, request, slug=None):
        """
        Retrieve all packaging variants for this product.
        """
        product = self.get_object()
        if request.user and request.user.is_staff:
            variants = product.variants.all()
        else:
            variants = product.available_variants
        serializer = ProductVariantSerializer(variants, many=True)
        return Response(serializer.data)


class ProductVariantViewSet(viewsets.ModelViewSet):
    """
    Admin endpoint for creating, editing, and deleting packaging variants.
    """
    queryset = ProductVariant.objects.select_related('product').all()
    serializer_class = ProductVariantSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['sku', 'product__name']
    ordering_fields = ['package_weight', 'price', 'created_at']
    ordering = ['product', 'package_weight']

    def get_queryset(self):
        if self.request.user and self.request.user.is_staff:
            return self.queryset
        return self.queryset.filter(is_available=True, product__is_active=True)


class CalculatePricingView(APIView):
    """
    Authoritative backend pricing calculation engine.
    Never trusts client prices!
    Validates:
      1. Item and variant availability.
      2. Minimum order quantity (MOQ) for wholesale vs retail.
      3. Applies approved wholesale base pricing, volume-based quantity tiers,
         or custom negotiated pricing for approved business accounts.
      4. Returns itemized unit price, line totals, and overall subtotal.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PriceCalculationRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'status': 'error', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        items_data = serializer.validated_data['items']
        user = request.user if request.user.is_authenticated else None
        customer_profile = getattr(user, 'customer_profile', None) if user else None

        is_wholesale = bool(customer_profile and customer_profile.is_wholesale_approved)
        customer_segment = 'wholesale' if is_wholesale else 'retail'

        calculated_items = []
        subtotal = 0
        all_moq_met = True
        warnings = []

        variant_ids = [item['variant_id'] for item in items_data]
        variants_dict = {
            v.id: v for v in ProductVariant.objects.filter(id__in=variant_ids)
            .select_related('product')
            .prefetch_related('price_tiers', 'customer_special_prices')
        }

        for item in items_data:
            vid = item['variant_id']
            qty = item['quantity']
            variant = variants_dict.get(vid)

            if not variant:
                return Response(
                    {'status': 'error', 'message': f"Product variant ID {vid} not found."},
                    status=status.HTTP_404_NOT_FOUND
                )

            if not variant.is_available:
                return Response(
                    {'status': 'error', 'message': f"Variant {variant.sku} is currently unavailable."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Check segment availability
            if is_wholesale and not variant.is_available_wholesale:
                return Response(
                    {'status': 'error', 'message': f"Variant {variant.sku} is not available for wholesale ordering."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if not is_wholesale and not variant.is_available_retail:
                return Response(
                    {'status': 'error', 'message': f"Variant {variant.sku} is not available for retail purchase."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Check MOQ
            moq = variant.get_moq_for_customer(customer_profile)
            moq_satisfied = qty >= moq
            if not moq_satisfied:
                all_moq_met = False
                warnings.append(
                    f"{variant.product.name} ({variant.display_weight}): Wholesale minimum order quantity is {moq} units. Current: {qty}."
                )

            # Calculate unit price and rule applied
            unit_price = variant.get_effective_price(customer_profile=customer_profile, quantity=qty)
            
            # Determine rule label
            rule_applied = "Standard Retail Price"
            if is_wholesale:
                special = variant.customer_special_prices.filter(customer=customer_profile, is_active=True).first()
                if special:
                    rule_applied = "Custom Negotiated Wholesale Price"
                else:
                    tier = variant.price_tiers.filter(min_quantity__lte=qty).order_by('-min_quantity').first()
                    if tier:
                        rule_applied = f"Wholesale Volume Tier ({tier.min_quantity}+ units)"
                    else:
                        rule_applied = "Approved Wholesale Base Price"

            line_total = unit_price * qty
            subtotal += line_total

            calculated_items.append({
                'variant_id': variant.id,
                'sku': variant.sku,
                'product_name': variant.product.name,
                'package_weight': float(variant.package_weight),
                'package_unit': variant.package_unit,
                'display_weight': variant.display_weight,
                'quantity': qty,
                'moq': moq,
                'moq_satisfied': moq_satisfied,
                'retail_unit_price': float(variant.price),
                'effective_unit_price': float(unit_price),
                'rule_applied': rule_applied,
                'line_total': float(line_total),
            })

        return Response({
            'status': 'success',
            'customer_segment': customer_segment,
            'is_wholesale_approved': is_wholesale,
            'all_moq_met': all_moq_met,
            'warnings': warnings,
            'subtotal': float(subtotal),
            'currency': 'INR',
            'items': calculated_items,
        }, status=status.HTTP_200_OK)
