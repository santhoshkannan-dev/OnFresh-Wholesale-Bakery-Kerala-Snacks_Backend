from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from apps.customers.models import CustomerProfile, validate_phone, validate_gstin
from apps.customers.serializers import CustomerProfileSerializer
from apps.accounts.roles import (
    get_user_roles,
    get_user_primary_role,
    ALL_ROLES,
    ROLE_SUPER_ADMIN,
)

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    role = serializers.SerializerMethodField()
    staff_roles = serializers.SerializerMethodField()
    primary_role = serializers.SerializerMethodField()
    profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'full_name',
            'role',
            'staff_roles',
            'primary_role',
            'is_staff',
            'is_superuser',
            'is_active',
            'date_joined',
            'profile',
        ]
        read_only_fields = [
            'id', 'email', 'full_name', 'role', 'staff_roles', 'primary_role',
            'is_staff', 'is_superuser', 'is_active', 'date_joined', 'profile'
        ]

    def get_role(self, obj):
        if obj.is_superuser:
            return 'admin'
        if obj.is_staff:
            return 'staff'
        return 'customer'

    def get_staff_roles(self, obj):
        return get_user_roles(obj)

    def get_primary_role(self, obj):
        return get_user_primary_role(obj)

    def get_profile(self, obj):
        if hasattr(obj, 'customer_profile'):
            return CustomerProfileSerializer(obj.customer_profile).data
        return None


class StaffMemberSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    roles = serializers.SerializerMethodField()
    primary_role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'username',
            'first_name',
            'last_name',
            'full_name',
            'is_active',
            'is_staff',
            'is_superuser',
            'roles',
            'primary_role',
            'date_joined',
            'last_login',
        ]

    def get_roles(self, obj):
        return get_user_roles(obj)

    def get_primary_role(self, obj):
        return get_user_primary_role(obj)


class StaffCreateUpdateSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    full_name = serializers.CharField(max_length=150, required=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    roles = serializers.ListField(
        child=serializers.ChoiceField(choices=ALL_ROLES),
        required=False,
        default=list
    )
    is_active = serializers.BooleanField(required=False, default=True)


class RegisterSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150, required=True)
    email = serializers.EmailField(required=True)
    mobile_number = serializers.CharField(max_length=20, required=True)
    customer_type = serializers.ChoiceField(
        choices=CustomerProfile.CUSTOMER_TYPE_CHOICES,
        default='individual',
        required=False
    )
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        min_length=8
    )
    password_confirmation = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        min_length=8
    )

    # Optional business profile fields for B2B
    business_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    business_type = serializers.ChoiceField(
        choices=CustomerProfile.BUSINESS_TYPE_CHOICES,
        default='retail_shop',
        required=False
    )
    gstin = serializers.CharField(max_length=15, required=False, allow_blank=True)

    def validate_email(self, value):
        cleaned = value.strip().lower()
        if User.objects.filter(email__iexact=cleaned).exists():
            raise serializers.ValidationError('An account with this email address already exists.')
        return cleaned

    def validate_mobile_number(self, value):
        validate_phone(value)
        return value.strip()

    def validate_gstin(self, value):
        if value:
            validate_gstin(value)
            return value.strip().upper()
        return ''

    def validate(self, attrs):
        password = attrs.get('password')
        password_confirmation = attrs.get('password_confirmation')
        customer_type = attrs.get('customer_type', 'individual')
        business_name = attrs.get('business_name', '').strip()

        if password != password_confirmation:
            raise serializers.ValidationError({
                'password_confirmation': 'Passwords do not match.'
            })

        if customer_type == 'business' and not business_name:
            raise serializers.ValidationError({
                'business_name': 'Business name is required when registering a wholesale business account.'
            })

        # Run Django password strength validators
        try:
            validate_password(password)
        except DjangoValidationError as e:
            raise serializers.ValidationError({'password': list(e.messages)})

        return attrs

    def create(self, validated_data):
        full_name = validated_data['full_name'].strip()
        email = validated_data['email'].strip().lower()
        password = validated_data['password']
        mobile_number = validated_data['mobile_number']
        customer_type = validated_data.get('customer_type', 'individual')
        business_name = validated_data.get('business_name', '').strip()
        business_type = validated_data.get('business_type', 'retail_shop')
        gstin = validated_data.get('gstin', '')

        # Wholesale approval starts as 'pending' for businesses, 'none' for individuals
        wholesale_status = 'pending' if customer_type == 'business' else 'none'
        if customer_type == 'individual' and not business_name:
            business_name = ''

        # Split full name into first and last name for Django User model
        name_parts = full_name.split(' ', 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ''

        with transaction.atomic():
            # Strictly enforce customer privileges: is_staff=False, is_superuser=False
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                is_staff=False,
                is_superuser=False,
                is_active=True
            )

            CustomerProfile.objects.create(
                user=user,
                customer_type=customer_type,
                wholesale_status=wholesale_status,
                business_name=business_name,
                business_type=business_type if customer_type == 'business' else 'retail_shop',
                contact_person=full_name,
                phone_number=mobile_number,
                gstin=gstin
            )

        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )

    def validate_email(self, value):
        return value.strip().lower()

