from django.contrib import admin
from .models import CustomerProfile, Address


class AddressInline(admin.StackedInline):
    model = Address
    extra = 0
    fields = [
        'address_type',
        'recipient_name',
        'phone_number',
        'address_line_1',
        'address_line_2',
        'city',
        'district',
        'state',
        'pincode',
        'is_default',
    ]


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = [
        'customer_display',
        'user_email',
        'customer_type',
        'wholesale_status',
        'is_wholesale_approved_display',
        'phone_number',
        'business_type',
        'gstin',
        'account_status',
        'address_count',
        'created_at',
    ]
    list_filter = [
        'customer_type',
        'wholesale_status',
        'business_type',
        'user__is_active',
        'created_at',
    ]
    search_fields = [
        'business_name',
        'contact_person',
        'user__email',
        'user__username',
        'phone_number',
        'gstin'
    ]
    readonly_fields = ['created_at', 'updated_at']
    inlines = [AddressInline]
    actions = [
        'approve_wholesale',
        'reject_wholesale',
        'reset_to_pending',
        'activate_customers',
        'deactivate_customers',
    ]

    fieldsets = [
        ('User Association', {
            'fields': ['user']
        }),
        ('Customer Classification & Wholesale Status', {
            'fields': ['customer_type', 'wholesale_status', 'rejection_reason']
        }),
        ('Business Information (B2B)', {
            'fields': ['business_name', 'business_type', 'gstin']
        }),
        ('Contact Information', {
            'fields': ['contact_person', 'phone_number']
        }),
        ('Audit Timestamps', {
            'fields': ['created_at', 'updated_at'],
            'classes': ['collapse']
        }),
    ]

    @admin.display(description='Customer / Business')
    def customer_display(self, obj):
        if obj.customer_type == 'business' and obj.business_name:
            return f"🏢 {obj.business_name} ({obj.contact_person or obj.user.get_full_name()})"
        return f"👤 {obj.user.get_full_name() or obj.user.username} [Retail]"

    @admin.display(description='User Email', ordering='user__email')
    def user_email(self, obj):
        return obj.user.email

    @admin.display(description='Wholesale Approved', boolean=True)
    def is_wholesale_approved_display(self, obj):
        return obj.is_wholesale_approved

    @admin.display(description='Account Status', boolean=True, ordering='user__is_active')
    def account_status(self, obj):
        return obj.user.is_active

    @admin.display(description='Saved Addresses')
    def address_count(self, obj):
        return obj.addresses.count()

    @admin.action(description='✓ Approve selected wholesale business accounts')
    def approve_wholesale(self, request, queryset):
        count = queryset.update(wholesale_status='approved', customer_type='business')
        self.message_user(request, f"Approved wholesale access for {count} business customer(s).")

    @admin.action(description='✗ Reject selected wholesale business accounts')
    def reject_wholesale(self, request, queryset):
        count = queryset.update(wholesale_status='rejected')
        self.message_user(request, f"Rejected wholesale access for {count} account(s).")

    @admin.action(description='↻ Reset wholesale status to Pending Approval')
    def reset_to_pending(self, request, queryset):
        count = queryset.update(wholesale_status='pending')
        self.message_user(request, f"Reset wholesale status to pending for {count} account(s).")

    @admin.action(description='Activate selected customer accounts')
    def activate_customers(self, request, queryset):
        user_ids = queryset.values_list('user_id', flat=True)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.objects.filter(id__in=user_ids).update(is_active=True)
        self.message_user(request, f"Activated {len(user_ids)} customer account(s).")

    @admin.action(description='Deactivate selected customer accounts')
    def deactivate_customers(self, request, queryset):
        user_ids = queryset.values_list('user_id', flat=True)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.objects.filter(id__in=user_ids).update(is_active=False)
        self.message_user(request, f"Deactivated {len(user_ids)} customer account(s).")


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = [
        'recipient_name',
        'customer_business',
        'address_type',
        'city',
        'district',
        'state',
        'pincode',
        'is_default',
        'created_at',
    ]
    list_filter = ['address_type', 'is_default', 'district', 'state']
    search_fields = [
        'recipient_name',
        'phone_number',
        'address_line_1',
        'city',
        'pincode',
        'customer__business_name',
        'customer__contact_person'
    ]
    readonly_fields = ['created_at', 'updated_at']

    @admin.display(description='Customer Business', ordering='customer__business_name')
    def customer_business(self, obj):
        return obj.customer.business_name

