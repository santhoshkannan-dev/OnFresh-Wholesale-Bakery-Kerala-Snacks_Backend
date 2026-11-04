from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

from django.shortcuts import get_object_or_404
from django.db import transaction
from django.contrib.auth.models import Group
from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    UserSerializer,
    StaffMemberSerializer,
    StaffCreateUpdateSerializer,
)
from .roles import (
    ensure_staff_roles,
    ALL_ROLES,
    ROLE_DESCRIPTIONS,
    IsStaffUser,
    IsSuperAdminUser,
)

User = get_user_model()

ACCESS_COOKIE_NAME = getattr(settings, 'JWT_AUTH_COOKIE', 'onfresh_access_token')
REFRESH_COOKIE_NAME = getattr(settings, 'JWT_AUTH_REFRESH_COOKIE', 'onfresh_refresh_token')
COOKIE_SAMESITE = getattr(settings, 'JWT_AUTH_COOKIE_SAMESITE', 'Lax')
COOKIE_SECURE = not settings.DEBUG


def set_auth_cookies(response, access_token, refresh_token=None):
    """
    Sets secure HttpOnly cookies for JWT authentication.
    """
    # Access token cookie (valid for 1 hour)
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=str(access_token),
        max_age=3600,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path='/'
    )

    # Refresh token cookie (valid for 7 days)
    if refresh_token:
        response.set_cookie(
            key=REFRESH_COOKIE_NAME,
            value=str(refresh_token),
            max_age=7 * 24 * 3600,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite=COOKIE_SAMESITE,
            path='/'
        )
    return response


def clear_auth_cookies(response):
    """
    Clears authentication cookies on logout.
    """
    response.delete_cookie(ACCESS_COOKIE_NAME, path='/')
    response.delete_cookie(REFRESH_COOKIE_NAME, path='/')
    return response


class RegisterView(APIView):
    """
    Public customer registration endpoint.
    Creates a User and linked CustomerProfile with strictly customer permissions.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'status': 'error', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = serializer.save()
        refresh = RefreshToken.for_user(user)

        response = Response(
            {
                'status': 'success',
                'message': 'Registration successful. Welcome to OnFresh!',
                'user': UserSerializer(user).data
            },
            status=status.HTTP_201_CREATED
        )
        return set_auth_cookies(response, refresh.access_token, refresh)


class LoginView(APIView):
    """
    Customer & Staff login endpoint with email and password.
    Returns user details and sets secure HttpOnly cookies.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'status': 'error', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        email = serializer.validated_data['email']
        password = serializer.validated_data['password']

        user = User.objects.filter(email__iexact=email).first()
        if user is None or not user.check_password(password):
            return Response(
                {'status': 'error', 'detail': 'Invalid email or password.'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if not user.is_active:
            return Response(
                {'status': 'error', 'detail': 'This account has been deactivated.'},
                status=status.HTTP_403_FORBIDDEN
            )

        refresh = RefreshToken.for_user(user)
        response = Response(
            {
                'status': 'success',
                'message': 'Login successful.',
                'user': UserSerializer(user).data
            },
            status=status.HTTP_200_OK
        )
        return set_auth_cookies(response, refresh.access_token, refresh)


class LogoutView(APIView):
    """
    Logout endpoint. Clears HttpOnly authentication cookies.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        # Optional: blacklist refresh token if token blacklisting is enabled
        refresh_token = request.COOKIES.get(REFRESH_COOKIE_NAME) or request.data.get('refresh')
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                pass

        response = Response(
            {'status': 'success', 'message': 'Logged out successfully.'},
            status=status.HTTP_200_OK
        )
        return clear_auth_cookies(response)


class TokenRefreshView(APIView):
    """
    Refreshes the access token using the refresh token from cookie or body.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.COOKIES.get(REFRESH_COOKIE_NAME) or request.data.get('refresh')
        if not refresh_token:
            return Response(
                {'status': 'error', 'detail': 'Refresh token not found.'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        try:
            refresh = RefreshToken(refresh_token)
            new_access_token = refresh.access_token

            rotate_enabled = getattr(settings, 'SIMPLE_JWT', {}).get('ROTATE_REFRESH_TOKENS', False)
            if rotate_enabled:
                refresh.set_jti()
                refresh.set_exp()

            response = Response(
                {
                    'status': 'success',
                    'message': 'Token refreshed.',
                    'access': str(new_access_token),
                },
                status=status.HTTP_200_OK
            )
            return set_auth_cookies(response, new_access_token, refresh if rotate_enabled else None)
        except (TokenError, InvalidToken) as e:
            response = Response(
                {'status': 'error', 'detail': f'Invalid or expired refresh token: {str(e)}'},
                status=status.HTTP_401_UNAUTHORIZED
            )
            return clear_auth_cookies(response)


class MeView(APIView):
    """
    Returns the currently authenticated user's information and customer profile.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(
            {'status': 'success', 'user': serializer.data},
            status=status.HTTP_200_OK
        )


class AdminStaffListView(APIView):
    """
    Lists all staff members and creates new staff users with role assignments.
    """
    permission_classes = [IsStaffUser]

    def get(self, request):
        ensure_staff_roles()
        staff_users = User.objects.filter(is_staff=True).order_by('-date_joined')
        serializer = StaffMemberSerializer(staff_users, many=True)
        return Response({'status': 'success', 'staff': serializer.data})

    def post(self, request):
        if not (request.user.is_superuser or request.user.groups.filter(name__in=['Super Admin', 'Admin']).exists()):
            return Response({'status': 'error', 'detail': 'Only Super Admin or Admin can create staff.'}, status=status.HTTP_403_FORBIDDEN)

        serializer = StaffCreateUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({'status': 'error', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        email = data['email'].strip().lower()
        full_name = data['full_name'].strip()
        password = data.get('password') or 'OnFreshStaff@2026'

        if User.objects.filter(email=email).exists():
            return Response({'status': 'error', 'detail': 'User with this email already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        parts = full_name.split(' ', 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ''

        with transaction.atomic():
            user = User.objects.create_user(
                username=email,
                email=email,
                first_name=first_name,
                last_name=last_name,
                password=password,
                is_staff=True,
                is_active=data.get('is_active', True)
            )
            # Assign groups
            roles = data.get('roles', ['Admin'])
            for role_name in roles:
                group, _ = Group.objects.get_or_create(name=role_name)
                user.groups.add(group)

        return Response({
            'status': 'success',
            'message': f'Staff member {full_name} created successfully.',
            'staff': StaffMemberSerializer(user).data
        }, status=status.HTTP_201_CREATED)


class AdminStaffDetailView(APIView):
    """
    Retrieve, update roles, or toggle active status of a staff member.
    """
    permission_classes = [IsStaffUser]

    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk, is_staff=True)
        return Response({'status': 'success', 'staff': StaffMemberSerializer(user).data})

    def patch(self, request, pk):
        if not (request.user.is_superuser or request.user.groups.filter(name__in=['Super Admin', 'Admin']).exists()):
            return Response({'status': 'error', 'detail': 'Only Super Admin or Admin can modify staff.'}, status=status.HTTP_403_FORBIDDEN)

        user = get_object_or_404(User, pk=pk, is_staff=True)
        data = request.data

        # Prevent non-superusers from modifying superuser
        if user.is_superuser and not request.user.is_superuser:
            return Response({'status': 'error', 'detail': 'Cannot modify Super Admin accounts.'}, status=status.HTTP_403_FORBIDDEN)

        with transaction.atomic():
            if 'full_name' in data and data['full_name']:
                parts = data['full_name'].strip().split(' ', 1)
                user.first_name = parts[0]
                user.last_name = parts[1] if len(parts) > 1 else ''

            if 'is_active' in data:
                # Do not deactivate oneself
                if user.id == request.user.id and not data['is_active']:
                    return Response({'status': 'error', 'detail': 'You cannot deactivate your own account.'}, status=status.HTTP_400_BAD_REQUEST)
                user.is_active = bool(data['is_active'])

            if 'password' in data and data['password']:
                user.set_password(data['password'])

            if 'roles' in data and isinstance(data['roles'], list):
                user.groups.clear()
                for role_name in data['roles']:
                    group, _ = Group.objects.get_or_create(name=role_name)
                    user.groups.add(group)

            user.save()

        return Response({
            'status': 'success',
            'message': f'Staff member {user.get_full_name()} updated successfully.',
            'staff': StaffMemberSerializer(user).data
        })


class AdminRoleListView(APIView):
    """
    Returns available staff roles and their functional descriptions.
    """
    permission_classes = [IsStaffUser]

    def get(self, request):
        ensure_staff_roles()
        data = [
            {'name': role, 'description': ROLE_DESCRIPTIONS.get(role, '')}
            for role in ALL_ROLES
        ]
        return Response({'status': 'success', 'roles': data})


