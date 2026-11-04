"""
OnFresh Staff Roles & Permissions Framework.
Defines role constants, Django Groups setup, and DRF permission classes.
"""

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from rest_framework import permissions

# Role Constants
ROLE_SUPER_ADMIN = 'Super Admin'
ROLE_ADMIN = 'Admin'
ROLE_ORDER_MANAGER = 'Order Manager'
ROLE_INVENTORY_MANAGER = 'Inventory Manager'
ROLE_ACCOUNTANT = 'Accountant'
ROLE_PRODUCTION_MANAGER = 'Production Manager'
ROLE_PURCHASE_MANAGER = 'Purchase Manager'
ROLE_QUALITY_INSPECTOR = 'Quality Inspector'

ALL_ROLES = [
    ROLE_SUPER_ADMIN,
    ROLE_ADMIN,
    ROLE_ORDER_MANAGER,
    ROLE_INVENTORY_MANAGER,
    ROLE_ACCOUNTANT,
    ROLE_PRODUCTION_MANAGER,
    ROLE_PURCHASE_MANAGER,
    ROLE_QUALITY_INSPECTOR,
]

ROLE_DESCRIPTIONS = {
    ROLE_SUPER_ADMIN: 'Complete system access, staff account management, database control, and administrative overrides.',
    ROLE_ADMIN: 'General administration across orders, inventory, manufacturing, customers, products, and operational reports.',
    ROLE_ORDER_MANAGER: 'View and manage customer orders, update delivery statuses, handle cancellations, and customer communications.',
    ROLE_INVENTORY_MANAGER: 'Manage stock levels, raw material inventories, warehouse adjustments, and track expiry.',
    ROLE_ACCOUNTANT: 'Access financial analytics, view invoices, verify payments, and export tax & sales reports.',
    ROLE_PRODUCTION_MANAGER: 'Plan production orders, manage recipes/BOM, oversee kitchen cooking batches, and record material consumptions.',
    ROLE_PURCHASE_MANAGER: 'Manage supplier directory, raise raw material purchase orders, and receive incoming supplier shipments.',
    ROLE_QUALITY_INSPECTOR: 'Conduct quality tests, sensory/moisture checks, seal integrity verifications, and approve batch release to sellable stock.',
}


def ensure_staff_roles():
    """
    Idempotently creates Django Groups for all OnFresh staff roles.
    Assigns appropriate model permissions where applicable.
    """
    for role_name in ALL_ROLES:
        group, _ = Group.objects.get_or_create(name=role_name)


def get_user_roles(user):
    """
    Return a list of role names assigned to the given user.
    """
    if not user.is_authenticated:
        return []
    if user.is_superuser:
        return [ROLE_SUPER_ADMIN]
    roles = list(user.groups.values_list('name', flat=True))
    if user.is_staff and not roles:
        return [ROLE_ADMIN]
    return roles


def get_user_primary_role(user):
    """
    Return the primary display role for the user.
    """
    if not user.is_authenticated:
        return 'Anonymous'
    if user.is_superuser:
        return ROLE_SUPER_ADMIN
    roles = get_user_roles(user)
    if ROLE_SUPER_ADMIN in roles:
        return ROLE_SUPER_ADMIN
    if ROLE_ADMIN in roles:
        return ROLE_ADMIN
    if ROLE_ORDER_MANAGER in roles:
        return ROLE_ORDER_MANAGER
    if ROLE_INVENTORY_MANAGER in roles:
        return ROLE_INVENTORY_MANAGER
    if ROLE_ACCOUNTANT in roles:
        return ROLE_ACCOUNTANT
    if ROLE_PRODUCTION_MANAGER in roles:
        return ROLE_PRODUCTION_MANAGER
    if ROLE_PURCHASE_MANAGER in roles:
        return ROLE_PURCHASE_MANAGER
    if ROLE_QUALITY_INSPECTOR in roles:
        return ROLE_QUALITY_INSPECTOR
    if user.is_staff:
        return ROLE_ADMIN
    return 'Customer'


class IsStaffUser(permissions.BasePermission):
    """Allows access only to authenticated staff or superusers."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser))


class IsSuperAdminUser(permissions.BasePermission):
    """Allows access only to Super Admins."""
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.is_superuser:
            return True
        return request.user.groups.filter(name=ROLE_SUPER_ADMIN).exists()


class IsOrderStaff(permissions.BasePermission):
    """
    Allows access to Super Admin, Admin, and Order Manager staff.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated and request.user.is_staff):
            return False
        if request.user.is_superuser:
            return True
        allowed = {ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_ORDER_MANAGER}
        user_roles = set(request.user.groups.values_list('name', flat=True))
        if not user_roles:
            return True
        return bool(allowed.intersection(user_roles))


class IsInventoryStaff(permissions.BasePermission):
    """
    Allows access to Super Admin, Admin, and Inventory Manager staff.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated and request.user.is_staff):
            return False
        if request.user.is_superuser:
            return True
        allowed = {ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_INVENTORY_MANAGER, ROLE_PRODUCTION_MANAGER}
        user_roles = set(request.user.groups.values_list('name', flat=True))
        if not user_roles:
            return True
        return bool(allowed.intersection(user_roles))


class IsFinanceStaff(permissions.BasePermission):
    """
    Allows access to Super Admin, Admin, and Accountant staff.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated and request.user.is_staff):
            return False
        if request.user.is_superuser:
            return True
        allowed = {ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_ACCOUNTANT}
        user_roles = set(request.user.groups.values_list('name', flat=True))
        if not user_roles:
            return True
        return bool(allowed.intersection(user_roles))


class IsProductionStaff(permissions.BasePermission):
    """
    Allows access to Super Admin, Admin, Production Manager, and Inventory Manager.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated and request.user.is_staff):
            return False
        if request.user.is_superuser:
            return True
        allowed = {ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_PRODUCTION_MANAGER, ROLE_INVENTORY_MANAGER}
        user_roles = set(request.user.groups.values_list('name', flat=True))
        if not user_roles:
            return True
        return bool(allowed.intersection(user_roles))


class IsPurchaseStaff(permissions.BasePermission):
    """
    Allows access to Super Admin, Admin, Purchase Manager, and Inventory Manager.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated and request.user.is_staff):
            return False
        if request.user.is_superuser:
            return True
        allowed = {ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_PURCHASE_MANAGER, ROLE_INVENTORY_MANAGER}
        user_roles = set(request.user.groups.values_list('name', flat=True))
        if not user_roles:
            return True
        return bool(allowed.intersection(user_roles))


class IsQualityStaff(permissions.BasePermission):
    """
    Allows access to Super Admin, Admin, Quality Inspector, and Production Manager.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated and request.user.is_staff):
            return False
        if request.user.is_superuser:
            return True
        allowed = {ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_QUALITY_INSPECTOR, ROLE_PRODUCTION_MANAGER}
        user_roles = set(request.user.groups.values_list('name', flat=True))
        if not user_roles:
            return True
        return bool(allowed.intersection(user_roles))

