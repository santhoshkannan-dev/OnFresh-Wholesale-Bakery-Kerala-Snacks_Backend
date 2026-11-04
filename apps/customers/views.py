from django.db.models import Count, Sum, Max, Q
from rest_framework import status, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.exceptions import PermissionDenied, NotFound
from rest_framework.pagination import PageNumberPagination

from .models import CustomerProfile, Address
from .serializers import (
    CustomerProfileSerializer,
    CustomerProfileDetailSerializer,
    AddressSerializer,
    RequestWholesaleSerializer,
    AdminCustomerListSerializer,
)


def get_or_create_customer_profile(user):
    """
    Helper to get or initialize a CustomerProfile for the authenticated user.
    """
    profile = getattr(user, 'customer_profile', None)
    if profile is None:
        full_name = user.get_full_name() or user.username
        profile = CustomerProfile.objects.create(
            user=user,
            customer_type='individual',
            wholesale_status='none',
            business_name='',
            business_type='retail_shop',
            contact_person=full_name,
            phone_number='9876543210',
            gstin=''
        )
    return profile


class CustomerProfileView(APIView):
    """
    Retrieve or update the authenticated customer's own business profile.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = get_or_create_customer_profile(request.user)
        serializer = CustomerProfileDetailSerializer(profile)
        return Response(
            {'status': 'success', 'profile': serializer.data},
            status=status.HTTP_200_OK
        )

    def patch(self, request):
        profile = get_or_create_customer_profile(request.user)
        
        # If full_name is provided, update user's first_name and last_name
        full_name = request.data.get('full_name')
        if full_name and isinstance(full_name, str):
            parts = full_name.strip().split(' ', 1)
            request.user.first_name = parts[0]
            request.user.last_name = parts[1] if len(parts) > 1 else ''
            request.user.save(update_fields=['first_name', 'last_name'])

        serializer = CustomerProfileSerializer(profile, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(
                {'status': 'error', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer.save()
        detail_serializer = CustomerProfileDetailSerializer(profile)
        return Response(
            {
                'status': 'success',
                'message': 'Profile updated successfully.',
                'profile': detail_serializer.data
            },
            status=status.HTTP_200_OK
        )


class RequestWholesaleView(APIView):
    """
    Submit or re-submit a request for wholesale business access.
    Sets status to 'pending' awaiting administrator approval.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        profile = get_or_create_customer_profile(request.user)
        serializer = RequestWholesaleSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'status': 'error', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        data = serializer.validated_data
        profile.customer_type = 'business'
        profile.wholesale_status = 'pending'
        profile.rejection_reason = ''
        profile.business_name = data['business_name'].strip()
        profile.business_type = data['business_type']
        profile.phone_number = data['phone_number'].strip()
        if data.get('contact_person'):
            profile.contact_person = data['contact_person'].strip()
        if data.get('gstin'):
            profile.gstin = data['gstin'].strip()
        profile.save()

        detail_serializer = CustomerProfileDetailSerializer(profile)
        return Response(
            {
                'status': 'success',
                'message': 'Wholesale access request submitted. Your request is pending review by OnFresh administrators.',
                'profile': detail_serializer.data,
            },
            status=status.HTTP_200_OK
        )


class AdminWholesaleApplicationListView(APIView):
    """
    Staff / Admin endpoint to list wholesale applications (pending, approved, rejected).
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        status_filter = request.query_params.get('status')
        qs = CustomerProfile.objects.filter(customer_type='business').select_related('user')
        if status_filter:
            qs = qs.filter(wholesale_status=status_filter)
        serializer = CustomerProfileSerializer(qs, many=True)
        return Response({'status': 'success', 'applications': serializer.data}, status=status.HTTP_200_OK)


class AdminWholesaleDecisionView(APIView):
    """
    Staff / Admin endpoint to approve or reject a customer's wholesale application.
    """
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            profile = CustomerProfile.objects.get(pk=pk)
        except CustomerProfile.DoesNotExist:
            return Response(
                {'status': 'error', 'detail': 'Customer profile not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        action = request.data.get('action')
        if action == 'approve':
            profile.customer_type = 'business'
            profile.wholesale_status = 'approved'
            profile.rejection_reason = ''
            profile.save()
            return Response(
                {
                    'status': 'success',
                    'message': f'Approved wholesale access for {profile.business_name}.',
                    'profile': CustomerProfileSerializer(profile).data,
                },
                status=status.HTTP_200_OK
            )
        elif action == 'reject':
            reason = request.data.get('reason', '').strip()
            profile.wholesale_status = 'rejected'
            profile.rejection_reason = reason or 'Business credentials could not be verified.'
            profile.save()
            return Response(
                {
                    'status': 'success',
                    'message': f'Rejected wholesale access for {profile.business_name}.',
                    'profile': CustomerProfileSerializer(profile).data,
                },
                status=status.HTTP_200_OK
            )
        else:
            return Response(
                {'status': 'error', 'detail': "Invalid action. Must be 'approve' or 'reject'."},
                status=status.HTTP_400_BAD_REQUEST
            )


class AddressViewSet(viewsets.ModelViewSet):
    """
    CRUD ViewSet for the authenticated customer's own addresses.
    Customers can never see, modify, or delete another customer's addresses.
    """
    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        profile = get_or_create_customer_profile(self.request.user)
        return Address.objects.filter(customer=profile).order_by('-is_default', '-created_at')

    def perform_create(self, serializer):
        profile = get_or_create_customer_profile(self.request.user)
        serializer.save(customer=profile)

    def perform_update(self, serializer):
        # Strict ownership check
        profile = get_or_create_customer_profile(self.request.user)
        if serializer.instance.customer_id != profile.id:
            raise PermissionDenied('You do not have permission to modify this address.')
        serializer.save()

    def perform_destroy(self, instance):
        # Strict ownership check
        profile = get_or_create_customer_profile(self.request.user)
        if instance.customer_id != profile.id:
            raise PermissionDenied('You do not have permission to delete this address.')
        instance.delete()


class AdminCustomerListView(APIView):
    """
    Staff / Admin endpoint to list, search, and filter all customers (B2C & B2B).
    Provides aggregated metrics such as total orders and lifetime spend.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        qs = CustomerProfile.objects.select_related('user').annotate(
            orders_count=Count('user__orders', distinct=True),
            total_spent=Sum(
                'user__orders__total_amount',
                filter=~Q(user__orders__order_status='cancelled'),
                distinct=True
            ),
            last_order_date=Max('user__orders__created_at')
        ).order_by('-created_at')

        # Filters
        customer_type = request.query_params.get('customer_type')
        if customer_type:
            qs = qs.filter(customer_type=customer_type)

        wholesale_status = request.query_params.get('wholesale_status')
        if wholesale_status:
            qs = qs.filter(wholesale_status=wholesale_status)

        is_active = request.query_params.get('is_active')
        if is_active is not None and is_active != '':
            qs = qs.filter(user__is_active=(is_active.lower() in ['true', '1']))

        search = request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(user__email__icontains=search) |
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(business_name__icontains=search) |
                Q(phone_number__icontains=search) |
                Q(gstin__icontains=search)
            )

        paginator = PageNumberPagination()
        paginator.page_size = 20
        page = paginator.paginate_queryset(qs, request)
        serializer = AdminCustomerListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class AdminCustomerDetailView(APIView):
    """
    Staff / Admin endpoint to retrieve complete customer information,
    addresses, and summary statistics.
    """
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        try:
            profile = CustomerProfile.objects.select_related('user').prefetch_related('addresses').annotate(
                orders_count=Count('user__orders', distinct=True),
                total_spent=Sum(
                    'user__orders__total_amount',
                    filter=~Q(user__orders__order_status='cancelled'),
                    distinct=True
                ),
                last_order_date=Max('user__orders__created_at')
            ).get(pk=pk)
        except CustomerProfile.DoesNotExist:
            return Response({'status': 'error', 'detail': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)

        data = AdminCustomerListSerializer(profile).data
        data['addresses'] = AddressSerializer(profile.addresses.all(), many=True).data
        return Response({'status': 'success', 'customer': data})


class AdminCustomerStatusToggleView(APIView):
    """
    Staff / Admin endpoint to activate or deactivate a customer account.
    """
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            profile = CustomerProfile.objects.select_related('user').get(pk=pk)
        except CustomerProfile.DoesNotExist:
            return Response({'status': 'error', 'detail': 'Customer not found.'}, status=status.HTTP_404_NOT_FOUND)

        is_active = request.data.get('is_active')
        if is_active is None:
            # Toggle current state
            profile.user.is_active = not profile.user.is_active
        else:
            if isinstance(is_active, str):
                profile.user.is_active = is_active.strip().lower() in ['true', '1', 'yes']
            else:
                profile.user.is_active = bool(is_active)

        profile.user.save(update_fields=['is_active'])

        return Response({
            'status': 'success',
            'message': f"Customer {profile.user.email} is now {'active' if profile.user.is_active else 'inactive'}.",
            'is_active': profile.user.is_active
        })


