from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CategoryViewSet, ProductViewSet, ProductVariantViewSet, CalculatePricingView

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'products', ProductViewSet, basename='product')
router.register(r'variants', ProductVariantViewSet, basename='variant')

urlpatterns = [
    path('products/calculate-pricing/', CalculatePricingView.as_view(), name='calculate_pricing'),
    path('', include(router.urls)),
]
