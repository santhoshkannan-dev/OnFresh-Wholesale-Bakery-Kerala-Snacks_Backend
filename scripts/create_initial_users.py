"""
OnFresh Initial Users Provisioning Script.
Creates standard Admin and Customer accounts for testing and production operations.
"""

import os
import sys
from pathlib import Path

# Setup paths and Django settings
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from apps.customers.models import CustomerProfile
from apps.accounts.roles import ensure_staff_roles, ROLE_SUPER_ADMIN, ROLE_ADMIN

User = get_user_model()


def provision_users():
    print("Ensuring staff roles & groups...")
    ensure_staff_roles()

    # 1. Admin / Staff Superuser
    admin_email = "admin@onfresh.in"
    admin_password = "Admin@OnFresh2026"
    admin_user, created = User.objects.get_or_create(
        email__iexact=admin_email,
        defaults={
            "username": "admin",
            "email": admin_email,
            "first_name": "OnFresh",
            "last_name": "Administrator",
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
        }
    )
    if not created:
        admin_user.username = "admin"
        admin_user.email = admin_email
        admin_user.first_name = "OnFresh"
        admin_user.last_name = "Administrator"
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.is_active = True

    admin_user.set_password(admin_password)
    admin_user.save()

    # Assign Admin Groups
    super_admin_group = Group.objects.filter(name=ROLE_SUPER_ADMIN).first()
    admin_group = Group.objects.filter(name=ROLE_ADMIN).first()
    if super_admin_group:
        admin_user.groups.add(super_admin_group)
    if admin_group:
        admin_user.groups.add(admin_group)

    print(f"[{'CREATED' if created else 'UPDATED'}] Admin User:")
    print(f"  - Username: admin")
    print(f"  - Email:    {admin_email}")
    print(f"  - Password: {admin_password}")
    print(f"  - Staff:    {admin_user.is_staff}")
    print(f"  - Superuser:{admin_user.is_superuser}")

    # 2. Retail Customer (B2C)
    customer_email = "customer@onfresh.in"
    customer_password = "Customer@OnFresh2026"
    customer_user, created_c = User.objects.get_or_create(
        email__iexact=customer_email,
        defaults={
            "username": customer_email,
            "email": customer_email,
            "first_name": "Rahul",
            "last_name": "Nair",
            "is_staff": False,
            "is_superuser": False,
            "is_active": True,
        }
    )
    if not created_c:
        customer_user.username = customer_email
        customer_user.email = customer_email
        customer_user.first_name = "Rahul"
        customer_user.last_name = "Nair"
        customer_user.is_staff = False
        customer_user.is_superuser = False
        customer_user.is_active = True

    customer_user.set_password(customer_password)
    customer_user.save()

    # Link CustomerProfile for B2C Retail
    cust_profile, _ = CustomerProfile.objects.update_or_create(
        user=customer_user,
        defaults={
            "customer_type": "individual",
            "wholesale_status": "none",
            "contact_person": "Rahul Nair",
            "phone_number": "9876543210",
            "business_name": "",
        }
    )

    print(f"\n[{'CREATED' if created_c else 'UPDATED'}] Customer User (Retail B2C):")
    print(f"  - Username: {customer_user.username}")
    print(f"  - Email:    {customer_email}")
    print(f"  - Password: {customer_password}")
    print(f"  - Type:     {cust_profile.customer_type}")
    print(f"  - Phone:    {cust_profile.phone_number}")

    # 3. Wholesale Customer (B2B)
    wholesale_email = "wholesale@onfresh.in"
    wholesale_password = "Wholesale@OnFresh2026"
    wholesale_user, created_w = User.objects.get_or_create(
        email__iexact=wholesale_email,
        defaults={
            "username": wholesale_email,
            "email": wholesale_email,
            "first_name": "Thomas",
            "last_name": "Varghese",
            "is_staff": False,
            "is_superuser": False,
            "is_active": True,
        }
    )
    if not created_w:
        wholesale_user.username = wholesale_email
        wholesale_user.email = wholesale_email
        wholesale_user.first_name = "Thomas"
        wholesale_user.last_name = "Varghese"
        wholesale_user.is_staff = False
        wholesale_user.is_superuser = False
        wholesale_user.is_active = True

    wholesale_user.set_password(wholesale_password)
    wholesale_user.save()

    # Link CustomerProfile for B2B Wholesale
    ws_profile, _ = CustomerProfile.objects.update_or_create(
        user=wholesale_user,
        defaults={
            "customer_type": "business",
            "wholesale_status": "approved",
            "business_name": "High Range Supermarket",
            "business_type": "supermarket",
            "contact_person": "Thomas Varghese",
            "phone_number": "9447012345",
            "gstin": "32AAAAA0000A1Z5",
        }
    )

    print(f"\n[{'CREATED' if created_w else 'UPDATED'}] Wholesale User (B2B Approved):")
    print(f"  - Username: {wholesale_user.username}")
    print(f"  - Email:    {wholesale_email}")
    print(f"  - Password: {wholesale_password}")
    print(f"  - Business: {ws_profile.business_name} ({ws_profile.business_type})")
    print(f"  - Status:   {ws_profile.wholesale_status}")
    print(f"  - GSTIN:    {ws_profile.gstin}")


if __name__ == "__main__":
    provision_users()

