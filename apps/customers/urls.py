from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CustomerProfileView,
    AddressViewSet,
    RequestWholesaleView,
    AdminWholesaleApplicationListView,
    AdminWholesaleDecisionView,
    AdminCustomerListView,
    AdminCustomerDetailView,
    AdminCustomerStatusToggleView,
)

app_name = 'customers'

router = DefaultRouter()
router.register(r'addresses', AddressViewSet, basename='address')

urlpatterns = [
    path('profile/', CustomerProfileView.as_view(), name='customer_profile'),
    path('request-wholesale/', RequestWholesaleView.as_view(), name='request_wholesale'),
    path('admin/applications/', AdminWholesaleApplicationListView.as_view(), name='admin_applications'),
    path('admin/applications/<int:pk>/decision/', AdminWholesaleDecisionView.as_view(), name='admin_application_decision'),
    path('admin/customers/', AdminCustomerListView.as_view(), name='admin_customer_list'),
    path('admin/customers/<int:pk>/', AdminCustomerDetailView.as_view(), name='admin_customer_detail'),
    path('admin/customers/<int:pk>/status/', AdminCustomerStatusToggleView.as_view(), name='admin_customer_status_toggle'),
    path('', include(router.urls)),
]
