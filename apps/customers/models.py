import re
from django.db import models, transaction
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

User = get_user_model()

# Indian GSTIN regex: 15 alphanumeric characters
GSTIN_REGEX = re.compile(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$')
# Mobile number regex: 10-digit Indian format, optionally with +91 or 0
PHONE_REGEX = re.compile(r'^(\+91[\-\s]?)?[0]?[6-9]\d{9}$')


def validate_gstin(value):
    if value:
        cleaned = value.strip().upper()
        if not GSTIN_REGEX.match(cleaned):
            raise ValidationError(
                'Invalid GSTIN format. Expected 15-character alphanumeric format (e.g. 32AAAAA0000A1Z5).'
            )


def validate_phone(value):
    if value:
        cleaned = re.sub(r'[\s\-]', '', value.strip())
        if not PHONE_REGEX.match(cleaned):
            raise ValidationError(
                'Invalid mobile number. Enter a valid 10-digit Indian phone number.'
            )


class CustomerProfile(models.Model):
    """
    Unified Customer Profile linked to Django User.
    Supports both B2C (individual retail) and B2B (wholesale business) customers.
    """
    CUSTOMER_TYPE_CHOICES = (
        ('individual', 'Individual (Retail Customer)'),
        ('business', 'Business (Wholesale Customer)'),
    )

    WHOLESALE_STATUS_CHOICES = (
        ('none', 'Not Requested'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    BUSINESS_TYPE_CHOICES = (
        ('retail_shop', 'Retail Shop / Kirana'),
        ('supermarket', 'Supermarket'),
        ('bakery', 'Bakery'),
        ('distributor', 'Wholesale Distributor'),
        ('restaurant', 'Restaurant / Tea Shop / Cafe'),
        ('other', 'Other Business'),
    )

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='customer_profile'
    )
    customer_type = models.CharField(
        max_length=20,
        choices=CUSTOMER_TYPE_CHOICES,
        default='individual',
        db_index=True,
        help_text="Customer segment: individual retail or wholesale business"
    )
    wholesale_status = models.CharField(
        max_length=20,
        choices=WHOLESALE_STATUS_CHOICES,
        default='none',
        db_index=True,
        help_text="Wholesale approval state for business customers"
    )
    rejection_reason = models.TextField(
        blank=True,
        default='',
        help_text="Administrator note if wholesale request was rejected"
    )
    business_name = models.CharField(max_length=200, blank=True, default='', db_index=True)
    business_type = models.CharField(
        max_length=30,
        choices=BUSINESS_TYPE_CHOICES,
        blank=True,
        default='retail_shop'
    )
    contact_person = models.CharField(max_length=150, blank=True, default='')
    phone_number = models.CharField(max_length=20, validators=[validate_phone])
    gstin = models.CharField(
        max_length=15,
        blank=True,
        default='',
        validators=[validate_gstin],
        help_text="Optional 15-character Indian GSTIN"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Customer Profile'
        verbose_name_plural = 'Customer Profiles'
        ordering = ['-created_at']

    def __str__(self):
        if self.customer_type == 'business' and self.business_name:
            return f"{self.business_name} ({self.user.email}) - {self.get_wholesale_status_display()}"
        return f"{self.user.get_full_name() or self.user.username} ({self.user.email}) [Retail]"

    @property
    def is_wholesale_approved(self):
        return self.customer_type == 'business' and self.wholesale_status == 'approved'

    def clean(self):
        super().clean()
        if self.gstin:
            self.gstin = self.gstin.strip().upper()
        if self.business_name:
            self.business_name = self.business_name.strip()
        if self.contact_person:
            self.contact_person = self.contact_person.strip()
        if self.customer_type == 'business' and not self.business_name:
            raise ValidationError({'business_name': 'Business name is required for wholesale business accounts.'})


class Address(models.Model):
    """
    Commercial delivery and billing addresses for wholesale customers.
    """
    ADDRESS_TYPE_CHOICES = (
        ('billing', 'Billing Address'),
        ('shipping', 'Shipping Address'),
    )

    customer = models.ForeignKey(
        CustomerProfile,
        on_delete=models.CASCADE,
        related_name='addresses'
    )
    address_type = models.CharField(
        max_length=20,
        choices=ADDRESS_TYPE_CHOICES,
        default='shipping'
    )
    recipient_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=20, validators=[validate_phone])
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True, default='')
    city = models.CharField(max_length=100)
    district = models.CharField(max_length=100, default='Idukki')
    state = models.CharField(max_length=100, default='Kerala')
    pincode = models.CharField(max_length=10)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Address'
        verbose_name_plural = 'Addresses'
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        return f"{self.recipient_name} - {self.city}, {self.district} ({self.get_address_type_display()})"

    def save(self, *args, **kwargs):
        with transaction.atomic():
            # If marked as default, unset other default addresses for the same customer and address_type
            if self.is_default:
                Address.objects.filter(
                    customer=self.customer,
                    address_type=self.address_type,
                    is_default=True
                ).exclude(pk=self.pk).update(is_default=False)
            else:
                # If this is the customer's first address of this type, make it default automatically
                if not Address.objects.filter(customer=self.customer, address_type=self.address_type).exclude(pk=self.pk).exists():
                    self.is_default = True
            super().save(*args, **kwargs)
