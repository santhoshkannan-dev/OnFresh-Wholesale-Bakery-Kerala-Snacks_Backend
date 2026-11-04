from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RawMaterialCategoryViewSet,
    RawMaterialViewSet,
    RawMaterialMovementListView,
    SupplierViewSet,
    PurchaseOrderViewSet,
    RecipeViewSet,
    ProductionOrderViewSet,
    QualityInspectionViewSet,
    ManufacturingDashboardView,
)

router = DefaultRouter()
router.register(r'categories', RawMaterialCategoryViewSet, basename='manufacturing-category')
router.register(r'raw-materials', RawMaterialViewSet, basename='raw-material')
router.register(r'suppliers', SupplierViewSet, basename='supplier')
router.register(r'purchases', PurchaseOrderViewSet, basename='purchase-order')
router.register(r'recipes', RecipeViewSet, basename='recipe')
router.register(r'production-orders', ProductionOrderViewSet, basename='production-order')
router.register(r'quality-inspections', QualityInspectionViewSet, basename='quality-inspection')

urlpatterns = [
    path('dashboard/', ManufacturingDashboardView.as_view(), name='manufacturing-dashboard'),
    path('movements/', RawMaterialMovementListView.as_view(), name='raw-material-movements'),
    path('', include(router.urls)),
]

