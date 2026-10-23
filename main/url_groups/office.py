"""Office: letters, appointments and the administrative expert's desk."""
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
    path('messenger/', views.messenger_home, name='messenger'),
    path('messenger/list/', views.messenger_list, name='messenger_list'),
    path('messenger/poll/', views.messenger_poll, name='messenger_poll'),
    path('messenger/new/', views.messenger_new, name='messenger_new'),
    path('messenger/directory/', views.messenger_directory, name='messenger_directory'),
    path('messenger/thread/<str:key>/', views.messenger_thread, name='messenger_thread'),
    path('messenger/thread/<str:key>/send/', views.messenger_send, name='messenger_send'),
    path('my-municipality/', views.my_municipality, name='my_municipality'),
    path('my-municipality/switch/', views.switch_municipality, name='switch_municipality'),
    path('dashboard/clerk/', views.clerk_dashboard, name='clerk_dashboard'),
    path('dashboard/clerk/remind/<int:request_id>/', views.clerk_remind, name='clerk_remind'),
    path('dashboard/clerk/visit/<int:appointment_id>/', views.clerk_visit_action, name='clerk_visit_action'),
    path('dashboard/clerk/hours/', views.clerk_hours, name='clerk_hours'),
    path('dashboard/clerk/book/', views.clerk_book, name='clerk_book'),
]
