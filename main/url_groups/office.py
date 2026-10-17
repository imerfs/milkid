"""Office: letters and appointments."""
from django.urls import path

from main import views

urlpatterns = [
    path('letters/', views.letters_inbox, name='letters_inbox'),
    path('letters/sent/', views.letters_sent, name='letters_sent'),
    path('letters/drafts/', views.letters_drafts, name='letters_drafts'),
    path('letters/archive/', views.letters_archive, name='letters_archive'),
    path('letters/compose/', views.letter_compose, name='letter_compose'),
    path('letters/attachments/<int:attachment_id>/', views.letter_attachment, name='letter_attachment'),
    path('letters/<int:letter_id>/', views.letter_detail, name='letter_detail'),
    path('letters/<int:letter_id>/reply/', views.letter_reply, name='letter_reply'),
    path('letters/<int:letter_id>/send/', views.letter_send, name='letter_send'),
    path('letters/<int:letter_id>/archive/', views.letter_archive, name='letter_archive'),
    path('appointments/', views.appointments, name='appointments'),
    path('appointments/providers/', views.appointment_providers, name='appointment_providers'),
    path('appointments/providers/<int:provider_id>/', views.appointment_book, name='appointment_book'),
    path('appointments/<int:appointment_id>/action/', views.appointment_action, name='appointment_action'),
    path('appointments/hours/', views.availability, name='availability'),
]
