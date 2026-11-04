"""
URL configuration for OnFresh project.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Core system endpoints (health check)
    path('api/', include('apps.core.urls')),
    
    # Products & Categories endpoints (/api/products/, /api/categories/, /api/variants/)
    path('api/', include('apps.products.urls')),
    
    # Domain module endpoints (to be expanded in subsequent phases)
    # Authentication endpoints (/api/auth/register/, /api/auth/login/, etc.)
    path('api/auth/', include('apps.accounts.urls')),
    path('api/inventory/', include('apps.inventory.urls')),
    path('api/customers/', include('apps.customers.urls')),
    path('api/cart/', include('apps.orders.cart_urls')),
    path('api/orders/', include('apps.orders.urls')),
    path('api/analytics/', include('apps.analytics.urls')),
    path('api/manufacturing/', include('apps.manufacturing.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
