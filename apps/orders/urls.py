from django.urls import path, include
from .views import (
    CheckoutView,
    OrderListView,
    OrderDetailView,
    OrderCancelView,
    PaymentInitiateView,
    PaymentVerifyView,
    AdminOrderListView,
    AdminOrderStatusUpdateView,
    OrderInvoiceView,
    OrderInvoicePDFView,
    AdminInvoiceListView,
    AdminInvoiceDetailView,
    AdminInvoicePDFDownloadView,
)

app_name = 'orders'

urlpatterns = [
    # Cart alias under orders
    path('cart/', include('apps.orders.cart_urls')),

    # Checkout
    path('checkout/', CheckoutView.as_view(), name='checkout'),

    # Admin endpoints (placed before <str:order_number> to avoid collision)
    path('admin/orders/', AdminOrderListView.as_view(), name='admin-order-list'),
    path('admin/orders/<str:order_number>/status/', AdminOrderStatusUpdateView.as_view(), name='admin-order-status-update'),
    path('admin/invoices/', AdminInvoiceListView.as_view(), name='admin-invoice-list'),
    path('admin/invoices/<str:invoice_number>/', AdminInvoiceDetailView.as_view(), name='admin-invoice-detail'),
    path('admin/invoices/<str:invoice_number>/pdf/', AdminInvoicePDFDownloadView.as_view(), name='admin-invoice-pdf'),

    # Customer orders
    path('', OrderListView.as_view(), name='order-list'),
    path('<str:order_number>/', OrderDetailView.as_view(), name='order-detail'),
    path('<str:order_number>/cancel/', OrderCancelView.as_view(), name='order-cancel'),
    path('<str:order_number>/payment/initiate/', PaymentInitiateView.as_view(), name='order-payment-initiate'),
    path('<str:order_number>/payment/verify/', PaymentVerifyView.as_view(), name='order-payment-verify'),
    path('<str:order_number>/invoice/', OrderInvoiceView.as_view(), name='order-invoice'),
    path('<str:order_number>/invoice/pdf/', OrderInvoicePDFView.as_view(), name='order-invoice-pdf'),
]
