"""Village web-GIS: map page, JSON layers, plot archive, payments and locks."""
from django.urls import path

from main import views

urlpatterns = [
    # village web-GIS (technical expert of the village, admins)
    path('gis/<slug:slug>/', views.map_page, name='gis_map'),
    path('gis/<slug:slug>/data/', views.map_data, name='gis_data'),
    path('gis/<slug:slug>/buildings/', views.map_buildings, name='gis_buildings'),
    path('gis/<slug:slug>/easements/', views.map_easements, name='gis_easements'),
    path('gis/<slug:slug>/context/', views.map_context, name='gis_context'),
    path('gis/<slug:slug>/cad/', views.map_cad, name='gis_cad'),
    path('gis/<slug:slug>/parcels/<int:parcel_id>/', views.parcel_detail, name='gis_parcel'),
    path('gis/<slug:slug>/parcels/<int:parcel_id>/lock/', views.parcel_lock, name='gis_lock'),
    path('gis/<slug:slug>/parcels/<int:parcel_id>/locks/<int:lock_id>/release/', views.parcel_unlock, name='gis_unlock'),
    path('gis/<slug:slug>/parcels/<int:parcel_id>/archive/', views.parcel_archive_save, name='gis_archive_save'),
    path('gis/<slug:slug>/parcels/<int:parcel_id>/payments/', views.payment_add, name='gis_payment_add'),
    path('gis/<slug:slug>/parcels/<int:parcel_id>/payments/<int:payment_id>/delete/', views.payment_delete, name='gis_payment_delete'),
    # the citizen's property inquiry map (any signed-in citizen or staff member)
    path('inquiry/', views.inquiry_page, name='property_inquiry'),
    path('inquiry/<slug:slug>/', views.inquiry_page, name='property_inquiry_map'),
    path('inquiry/<slug:slug>/data/', views.inquiry_data, name='inquiry_data'),
    path('inquiry/<slug:slug>/search/', views.inquiry_search, name='inquiry_search'),
    path('inquiry/<slug:slug>/parcels/<int:parcel_id>/', views.inquiry_parcel, name='inquiry_parcel'),
]
