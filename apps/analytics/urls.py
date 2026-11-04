from django.urls import path
from .views import (
    DashboardSummaryView,
    SalesAnalyticsView,
    B2BvsB2CComparisonView,
    ProductAnalyticsView,
    ReportExportView,
)

app_name = 'analytics'

urlpatterns = [
    path('dashboard/', DashboardSummaryView.as_view(), name='dashboard-summary'),
    path('sales/', SalesAnalyticsView.as_view(), name='sales-analytics'),
    path('b2b-b2c/', B2BvsB2CComparisonView.as_view(), name='b2b-b2c-comparison'),
    path('products/', ProductAnalyticsView.as_view(), name='product-analytics'),
    path('export/', ReportExportView.as_view(), name='report-export'),
]

