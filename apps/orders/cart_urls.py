from django.urls import path
from .views import (
    CartView,
    CartItemAddView,
    CartItemDetailView,
    CartSyncView,
)

app_name = 'cart'

urlpatterns = [
    path('', CartView.as_view(), name='cart-summary'),
    path('items/', CartItemAddView.as_view(), name='cart-item-add'),
    path('items/<int:item_id>/', CartItemDetailView.as_view(), name='cart-item-detail'),
    path('clear/', CartView.as_view(), name='cart-clear'),
    path('sync/', CartSyncView.as_view(), name='cart-sync'),
]

