from django.urls import path
from .views import (
    RegisterView,
    LoginView,
    LogoutView,
    TokenRefreshView,
    MeView,
    AdminStaffListView,
    AdminStaffDetailView,
    AdminRoleListView,
)

app_name = 'accounts'

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('me/', MeView.as_view(), name='me'),
    path('admin/staff/', AdminStaffListView.as_view(), name='admin_staff_list'),
    path('admin/staff/<int:pk>/', AdminStaffDetailView.as_view(), name='admin_staff_detail'),
    path('admin/roles/', AdminRoleListView.as_view(), name='admin_roles'),
]
