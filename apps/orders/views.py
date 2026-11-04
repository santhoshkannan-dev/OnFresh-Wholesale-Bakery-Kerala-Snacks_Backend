from decimal import Decimal
from django.db import models, transaction
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.pagination import PageNumberPagination
from apps.products.models import ProductVariant
from apps.customers.models import CustomerProfile, Address
from .models import Cart, CartItem, Order, OrderItem, OrderStatusHistory, Payment, Invoice
from .pricing import PricingService
from .payments import get_payment_gateway
from .invoice_service import InvoiceService
from .serializers import (
    CartItemAddSerializer,
    CartItemUpdateSerializer,
    CartSyncSerializer,
    CheckoutRequestSerializer,
    OrderListSerializer,
    OrderDetailSerializer,
    AdminOrderStatusUpdateSerializer,
    InvoiceListSerializer,
    InvoiceDetailSerializer,
)


def build_cart_response(cart: Cart, customer_profile=None):
    """
    Helper to calculate authoritative pricing for a Cart instance and build the response dict.
    """
    cart_items = list(cart.items.select_related('variant__product').all())
    items_data = [{'variant_id': item.variant_id, 'quantity': item.quantity} for item in cart_items]

    pricing = PricingService.calculate_cart_pricing(items_data, customer_profile)

    # Attach database CartItem id and slug to the pricing evaluated items
    item_map = {item.variant_id: item.id for item in cart_items}
    for item in pricing['items']:
        item['id'] = item_map.get(item['variant_id'])
        item['product_slug'] = item['variant'].product.slug
        # serialize decimals for json response
        item['retail_unit_price'] = float(item['retail_unit_price'])
        item['unit_price'] = float(item['unit_price'])
        item['line_subtotal'] = float(item['line_subtotal'])
        item['line_total'] = float(item['line_total'])
        item['line_discount'] = float(item['line_discount'])
        item['package_weight'] = float(item['package_weight'])
        # pop variant model instance
        item.pop('variant', None)

    return {
        'id': cart.id,
        'items': pricing['items'],
        'items_count': pricing['items_count'],
        'subtotal': float(pricing['subtotal']),
        'discount_amount': float(pricing['discount_amount']),
        'delivery_charge': float(pricing['delivery_charge']),
        'tax_amount': float(pricing['tax_amount']),
        'total_amount': float(pricing['total_amount']),
        'free_delivery_threshold': float(pricing['free_delivery_threshold']),
        'amount_for_free_delivery': float(pricing['amount_for_free_delivery']),
        'customer_segment': pricing['customer_segment'],
        'is_wholesale_approved': pricing['is_wholesale_approved'],
        'is_valid': pricing['is_valid'],
        'errors': pricing['errors'],
        'currency': 'INR',
    }


class CartView(APIView):
    """
    Unified Shopping Cart endpoint for authenticated customers.
    GET: Retrieves current cart with backend-calculated prices, tiers, and delivery fees.
    DELETE: Clears all items in the cart.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        profile = getattr(request.user, 'customer_profile', None)
        return Response(build_cart_response(cart, profile))

    def delete(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        cart.clear()
        profile = getattr(request.user, 'customer_profile', None)
        return Response(build_cart_response(cart, profile))


class CartItemAddView(APIView):
    """
    Adds a product variant to the customer's cart or increments quantity.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CartItemAddSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'status': 'error', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        variant_id = serializer.validated_data['variant_id']
        quantity = serializer.validated_data['quantity']

        variant = get_object_or_404(ProductVariant, id=variant_id)
        profile = getattr(request.user, 'customer_profile', None)

        if not variant.is_available:
            return Response(
                {'status': 'error', 'message': f"{variant.product.name} ({variant.display_weight}) is unavailable."},
                status=status.HTTP_400_BAD_REQUEST
            )

        is_wholesale = bool(profile and profile.is_wholesale_approved)
        if is_wholesale and not variant.is_available_wholesale:
            return Response(
                {'status': 'error', 'message': f"{variant.sku} is not available for wholesale orders."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not is_wholesale and not variant.is_available_retail:
            return Response(
                {'status': 'error', 'message': f"{variant.sku} is not available for retail purchase."},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            cart, _ = Cart.objects.get_or_create(user=request.user)
            item, created = CartItem.objects.get_or_create(
                cart=cart,
                variant=variant,
                defaults={'quantity': quantity}
            )
            if not created:
                item.quantity += quantity
                item.save(update_fields=['quantity', 'updated_at'])

        return Response(build_cart_response(cart, profile), status=status.HTTP_200_OK)


class CartItemDetailView(APIView):
    """
    Updates quantity or removes a specific item from the cart.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, item_id):
        serializer = CartItemUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'status': 'error', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        cart, _ = Cart.objects.get_or_create(user=request.user)
        item = get_object_or_404(CartItem, id=item_id, cart=cart)

        new_quantity = serializer.validated_data['quantity']
        item.quantity = new_quantity
        item.save(update_fields=['quantity', 'updated_at'])

        profile = getattr(request.user, 'customer_profile', None)
        return Response(build_cart_response(cart, profile))

    def delete(self, request, item_id):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        item = get_object_or_404(CartItem, id=item_id, cart=cart)
        item.delete()

        profile = getattr(request.user, 'customer_profile', None)
        return Response(build_cart_response(cart, profile))


class CartSyncView(APIView):
    """
    Merges temporary guest cart items into the authenticated customer's persistent cart upon login.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CartSyncSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'status': 'error', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        items_data = serializer.validated_data['items']
        cart, _ = Cart.objects.get_or_create(user=request.user)
        profile = getattr(request.user, 'customer_profile', None)

        with transaction.atomic():
            for entry in items_data:
                variant_id = entry['variant_id']
                qty = entry['quantity']
                variant = ProductVariant.objects.filter(id=variant_id, is_available=True).first()
                if not variant:
                    continue

                item, created = CartItem.objects.get_or_create(
                    cart=cart,
                    variant=variant,
                    defaults={'quantity': qty}
                )
                if not created:
                    # Increment or take higher quantity
                    item.quantity = max(item.quantity, qty)
                    item.save(update_fields=['quantity', 'updated_at'])

        return Response(build_cart_response(cart, profile))


class CheckoutView(APIView):
    """
    Validates cart, checks addresses ownership, creates Order and OrderItems with snapshots,
    initializes payment, and clears the cart atomically.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CheckoutRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'status': 'error', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        profile = getattr(request.user, 'customer_profile', None)
        if not profile:
            # Ensure profile exists
            profile, _ = CustomerProfile.objects.get_or_create(
                user=request.user,
                defaults={'customer_type': 'individual', 'wholesale_status': 'none'}
            )

        cart, _ = Cart.objects.get_or_create(user=request.user)
        cart_items = list(cart.items.select_related('variant__product').all())

        if not cart_items:
            return Response(
                {'status': 'error', 'message': 'Cannot checkout with an empty cart.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 1. Resolve and validate Shipping Address
        shipping_snapshot = {}
        if data.get('shipping_address_id'):
            addr = Address.objects.filter(id=data['shipping_address_id'], customer=profile).first()
            if not addr:
                return Response(
                    {'status': 'error', 'message': 'Selected shipping address does not belong to your account.'},
                    status=status.HTTP_403_FORBIDDEN
                )
            shipping_snapshot = {
                'recipient_name': addr.recipient_name,
                'phone_number': addr.phone_number,
                'address_line_1': addr.address_line_1,
                'address_line_2': addr.address_line_2,
                'city': addr.city,
                'district': addr.district,
                'state': addr.state,
                'pincode': addr.pincode,
            }
        elif data.get('new_shipping_address'):
            new_s = data['new_shipping_address']
            shipping_snapshot = {
                'recipient_name': new_s['recipient_name'],
                'phone_number': new_s['phone_number'],
                'address_line_1': new_s['address_line_1'],
                'address_line_2': new_s.get('address_line_2', ''),
                'city': new_s['city'],
                'district': new_s.get('district', 'Idukki'),
                'state': new_s.get('state', 'Kerala'),
                'pincode': new_s['pincode'],
            }
            # Save to customer address book
            Address.objects.create(
                customer=profile,
                address_type='shipping',
                **shipping_snapshot
            )

        # 2. Resolve and validate Billing Address
        if data.get('same_as_shipping', True):
            billing_snapshot = dict(shipping_snapshot)
        elif data.get('billing_address_id'):
            b_addr = Address.objects.filter(id=data['billing_address_id'], customer=profile).first()
            if not b_addr:
                return Response(
                    {'status': 'error', 'message': 'Selected billing address does not belong to your account.'},
                    status=status.HTTP_403_FORBIDDEN
                )
            billing_snapshot = {
                'recipient_name': b_addr.recipient_name,
                'phone_number': b_addr.phone_number,
                'address_line_1': b_addr.address_line_1,
                'address_line_2': b_addr.address_line_2,
                'city': b_addr.city,
                'district': b_addr.district,
                'state': b_addr.state,
                'pincode': b_addr.pincode,
            }
        elif data.get('new_billing_address'):
            new_b = data['new_billing_address']
            billing_snapshot = {
                'recipient_name': new_b['recipient_name'],
                'phone_number': new_b['phone_number'],
                'address_line_1': new_b['address_line_1'],
                'address_line_2': new_b.get('address_line_2', ''),
                'city': new_b['city'],
                'district': new_b.get('district', 'Idukki'),
                'state': new_b.get('state', 'Kerala'),
                'pincode': new_b['pincode'],
            }
            Address.objects.create(
                customer=profile,
                address_type='billing',
                **billing_snapshot
            )
        else:
            billing_snapshot = dict(shipping_snapshot)

        # 3. Authoritatively recalculate pricing
        items_payload = [{'variant_id': item.variant_id, 'quantity': item.quantity} for item in cart_items]
        pricing = PricingService.calculate_cart_pricing(items_payload, profile)

        if not pricing['is_valid']:
            return Response(
                {
                    'status': 'error',
                    'message': 'Some cart items could not be validated. Please review your cart before checking out.',
                    'errors': pricing['errors']
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # 4. Atomic order creation
        with transaction.atomic():
            order = Order.objects.create(
                customer=request.user,
                customer_profile=profile,
                customer_type=profile.customer_type,
                order_status='pending',
                payment_status='pending',
                payment_method=data['payment_method'],
                shipping_address_snapshot=shipping_snapshot,
                billing_address_snapshot=billing_snapshot,
                subtotal=pricing['subtotal'],
                discount_amount=pricing['discount_amount'],
                delivery_charge=pricing['delivery_charge'],
                tax_amount=pricing['tax_amount'],
                total_amount=pricing['total_amount'],
                customer_notes=data.get('customer_notes', ''),
            )

            # Create OrderItems with snapshot values
            for eval_item in pricing['items']:
                variant = eval_item['variant']
                OrderItem.objects.create(
                    order=order,
                    variant=variant,
                    product_name=variant.product.name,
                    sku=variant.sku,
                    package_weight=variant.package_weight,
                    package_unit=variant.package_unit,
                    quantity=eval_item['quantity'],
                    unit_price=eval_item['unit_price'],
                    retail_price=eval_item['retail_unit_price'],
                    discount_amount=eval_item['line_discount'],
                    line_total=eval_item['line_total'],
                    pricing_rule_applied=eval_item['pricing_rule_applied']
                )

            # Record initial order status history
            OrderStatusHistory.objects.create(
                order=order,
                old_status='',
                new_status='pending',
                changed_by=request.user,
                notes='Order created via checkout.'
            )

            # Initialize payment with selected provider
            gateway = get_payment_gateway(data['payment_method'])
            payment_info = gateway.initiate_payment(order)

            # Clear cart upon successful order placement
            cart.clear()

        detail_serializer = OrderDetailSerializer(order)
        return Response({
            'status': 'success',
            'message': f'Order {order.order_number} placed successfully.',
            'order': detail_serializer.data,
            'payment_instructions': payment_info,
        }, status=status.HTTP_201_CREATED)


class OrderListView(generics.ListAPIView):
    """
    List orders for the authenticated customer. Strictly isolates other customers' orders.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = OrderListSerializer

    def get_queryset(self):
        return Order.objects.filter(customer=self.request.user).prefetch_related('items').order_by('-created_at')


class OrderDetailView(APIView):
    """
    Retrieve full details for an order by order_number.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, order_number):
        queryset = Order.objects.prefetch_related(
            'items__variant__product',
            'status_history__changed_by',
            'payments'
        )
        if request.user.is_staff:
            order = get_object_or_404(queryset, order_number=order_number)
        else:
            order = get_object_or_404(queryset, order_number=order_number, customer=request.user)

        serializer = OrderDetailSerializer(order)
        return Response(serializer.data)


class OrderCancelView(APIView):
    """
    Allows a customer to cancel their order if it is still in pending or confirmed status.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, order_number):
        order = get_object_or_404(Order, order_number=order_number, customer=request.user)

        if not order.can_cancel():
            return Response(
                {
                    'status': 'error',
                    'message': f"Order {order.order_number} is in '{order.get_order_status_display()}' status and cannot be cancelled."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        reason = request.data.get('reason', 'Customer requested cancellation.')
        with transaction.atomic():
            order.transition_to('cancelled', changed_by=request.user, notes=reason)

        return Response({
            'status': 'success',
            'message': f"Order {order.order_number} has been cancelled.",
            'order_status': order.order_status,
        })


class PaymentInitiateView(APIView):
    """
    Initiate or re-initiate payment for an order.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, order_number):
        order = get_object_or_404(Order, order_number=order_number, customer=request.user)
        method = request.data.get('payment_method', order.payment_method)
        idempotency_key = request.data.get('idempotency_key')

        gateway = get_payment_gateway(method)
        info = gateway.initiate_payment(order, idempotency_key=idempotency_key)
        return Response(info)


class PaymentVerifyView(APIView):
    """
    Verify payment gateway response or record UTR for bank transfer.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, order_number):
        order = get_object_or_404(Order, order_number=order_number, customer=request.user)
        gateway = get_payment_gateway(order.payment_method)
        success, message, data = gateway.verify_payment(order, request.data)

        if success:
            return Response({
                'status': 'success',
                'message': message,
                'order_status': order.order_status,
                'payment_status': order.payment_status,
                'data': data
            })
        return Response({
            'status': 'error',
            'message': message,
            'data': data
        }, status=status.HTTP_400_BAD_REQUEST)


class AdminOrderListView(generics.ListAPIView):
    """
    Staff / Admin endpoint to list, search, and filter all customer orders.
    """
    permission_classes = [IsAdminUser]
    serializer_class = OrderListSerializer

    def get_queryset(self):
        qs = Order.objects.select_related('customer').prefetch_related('items').order_by('-created_at')

        status_param = self.request.query_params.get('order_status')
        payment_param = self.request.query_params.get('payment_status')
        type_param = self.request.query_params.get('customer_type')
        search = self.request.query_params.get('search')

        if status_param:
            qs = qs.filter(order_status=status_param)
        if payment_param:
            qs = qs.filter(payment_status=payment_param)
        if type_param:
            qs = qs.filter(customer_type=type_param)
        if search:
            qs = qs.filter(
                models.Q(order_number__icontains=search) |
                models.Q(customer__email__icontains=search) |
                models.Q(shipping_address_snapshot__recipient_name__icontains=search) |
                models.Q(shipping_address_snapshot__phone_number__icontains=search)
            )

        return qs


class AdminOrderStatusUpdateView(APIView):
    """
    Staff / Admin endpoint to update order status, payment status, and record transition notes.
    """
    permission_classes = [IsAdminUser]

    def patch(self, request, order_number):
        order = get_object_or_404(Order, order_number=order_number)
        serializer = AdminOrderStatusUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'status': 'error', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        admin_notes = data.get('admin_notes', '')

        with transaction.atomic():
            if 'order_status' in data:
                new_status = data['order_status']
                if new_status != order.order_status:
                    order.transition_to(new_status, changed_by=request.user, notes=admin_notes)

            if 'payment_status' in data:
                order.payment_status = data['payment_status']
                order.save(update_fields=['payment_status', 'updated_at'])

            if admin_notes:
                order.admin_notes = admin_notes
                order.save(update_fields=['admin_notes', 'updated_at'])

        detail = OrderDetailSerializer(order)
        return Response({
            'status': 'success',
            'message': f"Order {order.order_number} status updated successfully.",
            'order': detail.data
        })


class OrderInvoiceView(APIView):
    """
    Retrieve or create the invoice for an order.
    Customers can access their own invoices; staff can access any.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, order_number):
        if request.user.is_staff:
            order = get_object_or_404(Order, order_number=order_number)
        else:
            order = get_object_or_404(Order, order_number=order_number, customer=request.user)

        invoice = InvoiceService.get_or_create_invoice_for_order(order)
        serializer = InvoiceDetailSerializer(invoice)
        return Response({'status': 'success', 'invoice': serializer.data})


class OrderInvoicePDFView(APIView):
    """
    Generates and downloads the official Tax Invoice PDF for an order.
    Customers can download their own invoices; staff can download any.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, order_number):
        if request.user.is_staff:
            order = get_object_or_404(Order, order_number=order_number)
        else:
            order = get_object_or_404(Order, order_number=order_number, customer=request.user)

        invoice = InvoiceService.get_or_create_invoice_for_order(order)
        pdf_bytes = InvoiceService.generate_pdf(invoice)

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        filename = f"{invoice.invoice_number}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class AdminInvoiceListView(APIView):
    """
    Staff / Admin endpoint to list, search, and filter all generated tax invoices.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        qs = Invoice.objects.select_related('order', 'order__customer').order_by('-created_at')

        status_param = request.query_params.get('status')
        payment_param = request.query_params.get('payment_status')
        type_param = request.query_params.get('customer_type')
        search = request.query_params.get('search')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')

        if status_param:
            qs = qs.filter(status=status_param)
        if payment_param:
            qs = qs.filter(payment_status=payment_param)
        if type_param:
            qs = qs.filter(customer_type=type_param)
        if date_from:
            qs = qs.filter(invoice_date__gte=date_from)
        if date_to:
            qs = qs.filter(invoice_date__lte=date_to)
        if search:
            qs = qs.filter(
                models.Q(invoice_number__icontains=search) |
                models.Q(order__order_number__icontains=search) |
                models.Q(customer_name__icontains=search) |
                models.Q(customer_email__icontains=search) |
                models.Q(business_name__icontains=search) |
                models.Q(customer_gstin__icontains=search)
            )

        paginator = PageNumberPagination()
        paginator.page_size = 20
        page = paginator.paginate_queryset(qs, request)
        serializer = InvoiceListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class AdminInvoiceDetailView(APIView):
    """
    Staff / Admin endpoint to retrieve single invoice details by invoice_number.
    """
    permission_classes = [IsAdminUser]

    def get(self, request, invoice_number):
        invoice = get_object_or_404(Invoice.objects.select_related('order'), invoice_number=invoice_number)
        serializer = InvoiceDetailSerializer(invoice)
        return Response({'status': 'success', 'invoice': serializer.data})


class AdminInvoicePDFDownloadView(APIView):
    """
    Staff / Admin endpoint to download invoice PDF by invoice_number.
    """
    permission_classes = [IsAdminUser]

    def get(self, request, invoice_number):
        invoice = get_object_or_404(Invoice.objects.select_related('order'), invoice_number=invoice_number)
        pdf_bytes = InvoiceService.generate_pdf(invoice)

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        filename = f"{invoice.invoice_number}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

