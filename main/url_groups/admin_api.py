"""JSON endpoints of the admin dashboard."""
from django.urls import path

from main import views

urlpatterns = [
    # Admin Dashboard API endpoints
    path('api/admin/users/', views.admin_api_users_list, name='api_admin_users_list'),
    path('api/admin/users/<int:user_id>/change-role/', views.admin_api_user_change_role, name='api_admin_user_change_role'),
    path('api/admin/users/<int:user_id>/toggle-active/', views.admin_api_user_toggle_active, name='api_admin_user_toggle_active'),
    path('api/admin/municipalities/', views.admin_api_municipalities_list, name='api_admin_municipalities_list'),
    path('api/admin/municipalities/<int:municipality_id>/action/', views.admin_api_municipality_action, name='api_admin_municipality_action'),
    path('api/admin/services/', views.admin_api_services_list, name='api_admin_services_list'),
    path('api/admin/services/create/', views.admin_api_service_create, name='api_admin_service_create'),
    path('api/admin/services/<int:service_id>/update/', views.admin_api_service_update, name='api_admin_service_update'),
    path('api/admin/services/<int:service_id>/delete/', views.admin_api_service_delete, name='api_admin_service_delete'),
    path('api/admin/services/<int:service_id>/toggle-active/', views.admin_api_service_toggle_active, name='api_admin_service_toggle_active'),
    path('api/admin/reports/chart-data/', views.admin_api_reports_chart_data, name='api_admin_reports_chart_data'),
    path('api/admin/reports/export-excel/', views.admin_api_reports_export_excel, name='api_admin_reports_export_excel'),
    path('api/admin/settings/', views.admin_api_system_settings, name='api_admin_system_settings'),
    path('api/admin/settings/update/', views.admin_api_update_system_settings, name='api_admin_update_system_settings'),
]
