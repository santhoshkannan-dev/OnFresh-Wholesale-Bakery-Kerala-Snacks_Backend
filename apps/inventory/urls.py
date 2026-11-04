from django.urls import path
from .views import (
    StockItemListView,
    StockItemDetailView,
    StockInView,
    StockOutView,
    StockAdjustmentView,
    StockMovementListView,
    ProductionBatchListCreateView,
    ProductionBatchDetailView,
    ProductionBatchCompleteView,
    ExpiryReportView,
    InventoryReportSummaryView,
)

app_name = 'inventory'

urlpatterns = [
    path('', StockItemListView.as_view(), name='stock-list'),
    path('stock-in/', StockInView.as_view(), name='stock-in'),
    path('stock-out/', StockOutView.as_view(), name='stock-out'),
    path('adjust/', StockAdjustmentView.as_view(), name='stock-adjust'),
    path('movements/', StockMovementListView.as_view(), name='stock-movements'),
    path('batches/', ProductionBatchListCreateView.as_view(), name='batch-list-create'),
    path('batches/<str:batch_number>/', ProductionBatchDetailView.as_view(), name='batch-detail'),
    path('batches/<str:batch_number>/complete/', ProductionBatchCompleteView.as_view(), name='batch-complete'),
    path('expiry/', ExpiryReportView.as_view(), name='expiry-report'),
    path('reports/summary/', InventoryReportSummaryView.as_view(), name='reports-summary'),
    path('<int:variant_id>/', StockItemDetailView.as_view(), name='stock-detail'),
]
