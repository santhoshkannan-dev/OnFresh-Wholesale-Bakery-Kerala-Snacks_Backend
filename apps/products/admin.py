from django.contrib import admin
from .models import Category, Product, ProductVariant, QuantityPriceTier, CustomerSpecialPrice


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'is_active', 'product_count_display', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['created_at', 'updated_at']

    @admin.display(description='Active Products')
    def product_count_display(self, obj):
        return obj.active_product_count


class QuantityPriceTierInline(admin.TabularInline):
    model = QuantityPriceTier
    extra = 1
    fields = ['min_quantity', 'price_per_unit']


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = [
        'sku',
        'package_weight',
        'package_unit',
        'price',
        'wholesale_price',
        'minimum_order_quantity',
        'is_available_retail',
        'is_available_wholesale',
        'is_available',
    ]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'category',
        'is_active',
        'is_featured',
        'variant_count',
        'retail_price_range',
        'wholesale_price_range',
        'created_at',
    ]
    list_filter = ['is_active', 'is_featured', 'category']
    search_fields = ['name', 'description', 'short_description', 'ingredients']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['created_at', 'updated_at']
    inlines = [ProductVariantInline]
    fieldsets = [
        ('Basic Information', {
            'fields': ['name', 'slug', 'category', 'short_description', 'description']
        }),
        ('Imagery & Specifications', {
            'fields': ['main_image', 'ingredients', 'shelf_life']
        }),
        ('Visibility & Publishing', {
            'fields': ['is_active', 'is_featured', 'created_at', 'updated_at']
        }),
    ]

    @admin.display(description='Variants')
    def variant_count(self, obj):
        return obj.variants.count()

    @admin.display(description='Retail Price Range (₹)')
    def retail_price_range(self, obj):
        min_p = obj.min_price
        max_p = obj.max_price
        if min_p and max_p:
            if min_p == max_p:
                return f"₹{min_p}"
            return f"₹{min_p} – ₹{max_p}"
        return "No variants configured"

    @admin.display(description='Wholesale Price Range (₹)')
    def wholesale_price_range(self, obj):
        min_p = obj.min_wholesale_price
        max_p = obj.max_wholesale_price
        if min_p and max_p:
            if min_p == max_p:
                return f"₹{min_p}"
            return f"₹{min_p} – ₹{max_p}"
        return "No variants configured"


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = [
        'sku',
        'product',
        'display_package_size',
        'retail_price_inr',
        'wholesale_price_inr',
        'minimum_order_quantity',
        'is_available_retail',
        'is_available_wholesale',
        'is_available',
        'created_at',
    ]
    list_filter = [
        'is_available',
        'is_available_retail',
        'is_available_wholesale',
        'package_unit',
        'product__category'
    ]
    search_fields = ['sku', 'product__name']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [QuantityPriceTierInline]

    @admin.display(description='Package Size')
    def display_package_size(self, obj):
        return obj.display_weight

    @admin.display(description='Retail Price (₹)')
    def retail_price_inr(self, obj):
        return f"₹{obj.price}"

    @admin.display(description='Wholesale Price (₹)')
    def wholesale_price_inr(self, obj):
        return f"₹{obj.wholesale_price}" if obj.wholesale_price else f"₹{obj.price} (Standard)"


@admin.register(QuantityPriceTier)
class QuantityPriceTierAdmin(admin.ModelAdmin):
    list_display = ['variant', 'min_quantity', 'price_per_unit', 'created_at']
    list_filter = ['variant__product__category']
    search_fields = ['variant__sku', 'variant__product__name']


@admin.register(CustomerSpecialPrice)
class CustomerSpecialPriceAdmin(admin.ModelAdmin):
    list_display = ['customer', 'variant', 'special_price', 'is_active', 'created_at']
    list_filter = ['is_active', 'variant__product__category']
    search_fields = ['customer__business_name', 'customer__user__email', 'variant__sku']
