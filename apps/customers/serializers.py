from rest_framework import serializers
from .models import CustomerProfile, Address, validate_gstin, validate_phone


class AddressSerializer(serializers.ModelSerializer):
    address_type_display = serializers.CharField(source='get_address_type_display', read_only=True)

    class Meta:
        model = Address
        fields = [
            'id',
            'address_type',
            'address_type_display',
            'recipient_name',
            'phone_number',
            'address_line_1',
            'address_line_2',
            'city',
            'district',
            'state',
            'pincode',
            'is_default',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'address_type_display', 'created_at', 'updated_at']

    def validate_phone_number(self, value):
        validate_phone(value)
        return value.strip()

    def validate_pincode(self, value):
        cleaned = value.strip()
        if not cleaned.isdigit() or len(cleaned) != 6:
            raise serializers.ValidationError('Enter a valid 6-digit Indian PIN code.')
        return cleaned


class CustomerProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)
    full_name = serializers.CharField(source='user.get_full_name', read_only=True)
    role = serializers.SerializerMethodField()
    customer_type_display = serializers.CharField(source='get_customer_type_display', read_only=True)
    wholesale_status_display = serializers.CharField(source='get_wholesale_status_display', read_only=True)
    is_wholesale_approved = serializers.BooleanField(read_only=True)
    business_type_display = serializers.CharField(source='get_business_type_display', read_only=True)

    class Meta:
        model = CustomerProfile
        fields = [
            'id',
            'email',
            'full_name',
            'role',
            'customer_type',
            'customer_type_display',
            'wholesale_status',
            'wholesale_status_display',
            'is_wholesale_approved',
            'rejection_reason',
            'business_name',
            'business_type',
            'business_type_display',
            'contact_person',
            'phone_number',
            'gstin',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'email',
            'full_name',
            'role',
            'customer_type_display',
            'wholesale_status_display',
            'is_wholesale_approved',
            'business_type_display',
            'created_at',
            'updated_at',
        ]

    def get_role(self, obj):
        if obj.user.is_superuser:
            return 'admin'
        if obj.user.is_staff:
            return 'staff'
        return 'customer'

    def validate_gstin(self, value):
        if value:
            validate_gstin(value)
            return value.strip().upper()
        return ''

    def validate_phone_number(self, value):
        validate_phone(value)
        return value.strip()


class RequestWholesaleSerializer(serializers.Serializer):
    business_name = serializers.CharField(max_length=200, required=True)
    business_type = serializers.ChoiceField(
        choices=CustomerProfile.BUSINESS_TYPE_CHOICES,
        default='retail_shop'
    )
    contact_person = serializers.CharField(max_length=150, required=False, allow_blank=True)
    phone_number = serializers.CharField(max_length=20, required=True)
    gstin = serializers.CharField(max_length=15, required=False, allow_blank=True)

    def validate_gstin(self, value):
        if value:
            validate_gstin(value)
            return value.strip().upper()
        return ''

    def validate_phone_number(self, value):
        validate_phone(value)
        return value.strip()


class CustomerProfileDetailSerializer(CustomerProfileSerializer):
    addresses = AddressSerializer(many=True, read_only=True)

    class Meta(CustomerProfileSerializer.Meta):
        fields = CustomerProfileSerializer.Meta.fields + ['addresses']


class AdminCustomerListSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    full_name = serializers.CharField(source='user.get_full_name', read_only=True)
    is_active = serializers.BooleanField(source='user.is_active', read_only=True)
    date_joined = serializers.DateTimeField(source='user.date_joined', read_only=True)
    customer_type_display = serializers.CharField(source='get_customer_type_display', read_only=True)
    wholesale_status_display = serializers.CharField(source='get_wholesale_status_display', read_only=True)
    business_type_display = serializers.CharField(source='get_business_type_display', read_only=True)
    orders_count = serializers.IntegerField(read_only=True, default=0)
    total_spent = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, default=0)
    last_order_date = serializers.DateTimeField(read_only=True, default=None)

    class Meta:
        model = CustomerProfile
        fields = [
            'id',
            'user_id',
            'email',
            'full_name',
            'customer_type',
            'customer_type_display',
            'wholesale_status',
            'wholesale_status_display',
            'business_name',
            'business_type',
            'business_type_display',
            'contact_person',
            'phone_number',
            'gstin',
            'is_active',
            'date_joined',
            'orders_count',
            'total_spent',
            'last_order_date',
            'created_at',
        ]


