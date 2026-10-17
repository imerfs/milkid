from django.urls import path
from django.contrib.auth import views as auth_views
from . import views, api_views, geo_cascade
from .url_groups import accounting, admin_api, gis, office

app_name = 'main'

urlpatterns = [
    # nginx auth_request target guarding /media/ (private uploads need a logged-in session)
    path('_media-auth/', views.media_auth, name='media_auth'),
    # Main pages
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),

    # Authentication
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('register/', views.register_choice, name='register'),
    path('register/citizen/', views.register, name='register_citizen'),
    path('register/staff-info/', views.staff_registration_info, name='staff_registration_info'),
    path('logout/', views.logout_view, name='logout'),
    path('login/email/', views.login_code_request, name='login_code_request'),
    path('login/email/verify/', views.login_code_verify, name='login_code_verify'),
    path('support/', views.support, name='support'),
    path('2fa/verify/', views.two_factor_verify, name='two_factor_verify'),
    path('pending-verification/', views.pending_verification, name='pending_verification'),
    path('access-blocked/', views.access_blocked, name='access_blocked'),

    # Dashboards
    path('dashboard/', views.dashboard, name='dashboard'),
    path('dashboard/user/', views.user_dashboard, name='user_dashboard'),
    path('dashboard/staff/', views.staff_dashboard, name='staff_dashboard'),
    path('dashboard/admin/', views.admin_dashboard, name='admin_dashboard'),
    path('dashboard/admin/monitoring/', views.admin_monitoring, name='admin_monitoring'),
    path('dashboard/admin/server/', views.admin_server, name='admin_server'),
    path('dashboard/admin/server/backup/', views.admin_server_backup, name='admin_server_backup'),
    path('dashboard/admin/server/backup/<str:name>/download/', views.admin_server_backup_download, name='admin_server_backup_download'),
    path('dashboard/admin/server/backup/<str:name>/delete/', views.admin_server_backup_delete, name='admin_server_backup_delete'),
    path('dashboard/admin/server/ips/block/', views.admin_server_ip_block, name='admin_server_ip_block'),
    path('dashboard/admin/server/ips/<int:block_id>/unblock/', views.admin_server_ip_unblock, name='admin_server_ip_unblock'),
    path('dashboard/admin/server/database/', views.admin_server_db_maintain, name='admin_server_db_maintain'),
    path('dashboard/admin/server/files/upload/', views.admin_server_file_upload, name='admin_server_file_upload'),
    path('dashboard/admin/mail/', views.admin_mail, name='admin_mail'),
    path('dashboard/admin/mail/send/', views.admin_mail_send, name='admin_mail_send'),
    path('dashboard/admin/mail/action/', views.admin_mail_action, name='admin_mail_action'),
    path('dashboard/admin/mail/fetch/', views.admin_mail_fetch, name='admin_mail_fetch'),
    path('dashboard/admin/server/sms/save/', views.admin_sms_save, name='admin_sms_save'),
    path('dashboard/admin/server/sms/test/', views.admin_sms_test, name='admin_sms_test'),
    path('dashboard/admin/server/email/test/', views.admin_server_email_test, name='admin_server_email_test'),
    path('dashboard/admin/server/cache/clear/', views.admin_server_cache_clear, name='admin_server_cache_clear'),
    path('dashboard/admin/server/files/', views.admin_server_files, name='admin_server_files'),
    path('dashboard/admin/server/files/action/', views.admin_server_file_action, name='admin_server_file_action'),
    path('dashboard/admin/server/redirects/add/', views.admin_server_redirect_add, name='admin_server_redirect_add'),
    path('dashboard/admin/server/redirects/<int:redirect_id>/delete/', views.admin_server_redirect_delete, name='admin_server_redirect_delete'),
    path('dashboard/admin/server/2fa/start/', views.admin_two_factor_start, name='admin_two_factor_start'),
    path('dashboard/admin/server/2fa/confirm/', views.admin_two_factor_confirm, name='admin_two_factor_confirm'),
    path('dashboard/admin/server/2fa/disable/', views.admin_two_factor_disable, name='admin_two_factor_disable'),
    path('dashboard/admin/server/files/download/', views.admin_server_file_download, name='admin_server_file_download'),
    path('dashboard/admin/server/files/delete/', views.admin_server_file_delete, name='admin_server_file_delete'),
    path('dashboard/admin/monitoring/letters/<int:letter_id>/', views.admin_monitoring_letter, name='admin_monitoring_letter'),
    path('dashboard/admin/monitoring/chats/<int:conversation_id>/', views.admin_monitoring_chat, name='admin_monitoring_chat'),
    path('dashboard/council/', views.council_dashboard, name='council_dashboard'),
    path('dashboard/dehyari/', views.dehyari_dashboard, name='dehyari_dashboard'),
    path('dashboard/dehyari/panel/<str:tab>/', views.mayor_panel, name='mayor_panel'),
    path('dashboard/dehyari-expert/', views.dehyari_expert_dashboard, name='dehyari_expert_dashboard'),
    *gis.urlpatterns,
    path('dashboard/engineer/', views.dehyari_expert_dashboard, name='engineer_dashboard'),
    path('dashboard/inspector/', views.inspector_dashboard, name='inspector_dashboard'),
    path('dashboard/accountant/', views.accountant_dashboard, name='accountant_dashboard'),
    path('dashboard/owner/', views.owner_dashboard, name='owner_dashboard'),

    # Dehyari Expert APIs
    path('api/expert/requests/<int:request_id>/details/', views.api_expert_request_details, name='api_expert_request_details'),
    path('api/expert/requests/<int:request_id>/forward/', views.api_expert_forward_request, name='api_expert_forward_request'),
    path('api/expert/requests/<int:request_id>/approve/', views.api_expert_approve_direct, name='api_expert_approve_direct'),
    path('api/expert/requests/<int:request_id>/request-documents/', views.api_expert_request_documents, name='api_expert_request_documents'),
    path('api/expert/requests/<int:request_id>/reject/', views.api_expert_reject_request, name='api_expert_reject_request'),
    path('api/expert/requests/<int:request_id>/add-report/', views.api_expert_add_technical_report, name='api_expert_add_technical_report'),
    
    # Council Dashboard Actions
    path('council/voting/', views.council_voting_list, name='council_voting_list'),
    path('council/voting/<int:request_id>/submit/', views.council_submit_vote, name='council_submit_vote'),
    path('council/polls/new/', views.council_poll_create, name='council_poll_create'),
    path('council/polls/<int:poll_id>/vote/', views.council_poll_vote, name='council_poll_vote'),
    path('council/polls/<int:poll_id>/close/', views.council_poll_close, name='council_poll_close'),
    path('council/meetings/save/', views.council_meeting_save, name='council_meeting_save'),
    path('council/meetings/<int:meeting_id>/cancel/', views.council_meeting_cancel, name='council_meeting_cancel'),
    path('council/messages/new/', views.council_message_new, name='council_message_new'),
    path('council/messages/<int:conversation_id>/reply/', views.council_message_reply, name='council_message_reply'),
    path('council/settings/save/', views.council_settings_save, name='council_settings_save'),
    path('council/review/', views.council_review_requests, name='council_review_requests'),
    path('council/request/<int:request_id>/', views.council_request_detail, name='council_request_detail'),
    path('council/request/<int:request_id>/comment/', views.council_add_comment, name='council_add_comment'),
    path('council/financial/', views.council_financial_reports, name='council_financial_reports'),
    
    # Mayor/Dehyari Dashboard Actions
    *accounting.urlpatterns,
    *office.urlpatterns,
    path('password/change/', views.password_change, name='password_change'),
    path('mayor/roles/', views.role_grants, name='role_grants'),
    path('mayor/roles/grant/', views.role_grant, name='role_grant'),
    path('mayor/roles/create/', views.role_create_account, name='role_create_account'),
    path('mayor/roles/<int:user_id>/revoke/', views.role_revoke, name='role_revoke'),
    path('mayor/staff/', views.mayor_staff_list, name='mayor_staff_list'),
    path('mayor/staff/add/', views.mayor_staff_add, name='mayor_staff_add'),
    path('mayor/staff/<int:staff_id>/edit/', views.mayor_staff_edit, name='mayor_staff_edit'),
    path('mayor/staff/<int:staff_id>/delete/', views.mayor_staff_delete, name='mayor_staff_delete'),
    path('mayor/requests/', views.mayor_requests_list, name='mayor_requests_list'),
    path('mayor/requests/<int:request_id>/approve/', views.mayor_request_approve, name='mayor_request_approve'),
    path('mayor/requests/<int:request_id>/reject/', views.mayor_request_reject, name='mayor_request_reject'),
    path('mayor/requests/<int:request_id>/assign/', views.mayor_request_assign, name='mayor_request_assign'),
    path('mayor/violations/', views.mayor_violations_list, name='mayor_violations_list'),
    path('mayor/violations/create/', views.mayor_violation_create, name='mayor_violation_create'),
    path('mayor/violations/<int:violation_id>/update/', views.mayor_violation_update, name='mayor_violation_update'),
    path('mayor/announcements/', views.mayor_announcements_list, name='mayor_announcements_list'),
    path('mayor/announcements/create/', views.mayor_announcement_create, name='mayor_announcement_create'),
    
    # User Dashboard Actions
    path('dashboard/submit-request/', views.dashboard_submit_request, name='dashboard_submit_request'),
    path('dashboard/track-requests/', views.dashboard_track_requests, name='dashboard_track_requests'),
    path('dashboard/request/<int:request_id>/', views.dashboard_request_detail, name='dashboard_request_detail'),
    path('dashboard/upload-document/', views.dashboard_upload_document, name='dashboard_upload_document'),
    path('dashboard/delete-document/<int:document_id>/', views.dashboard_delete_document, name='dashboard_delete_document'),
    path('dashboard/download-document/<int:document_id>/', views.dashboard_download_document, name='dashboard_download_document'),
    path('dashboard/payments/', views.dashboard_payments, name='dashboard_payments'),
    path('dashboard/messages/', views.dashboard_messages, name='dashboard_messages'),

    # Service Requests
    path('requests/', views.my_requests, name='my_requests'),
    path('requests/create/', views.create_request, name='create_request'),
    path('requests/<int:request_id>/', views.request_detail, name='request_detail'),

    # Staff functions
    path('manage-requests/', views.manage_requests, name='manage_requests'),
    path('update-request-status/<int:request_id>/', views.update_request_status, name='update_request_status'),
    path('manage-users/', views.manage_users, name='manage_users'),
    path('manage-users/<int:user_id>/', views.admin_user_detail, name='admin_user_detail'),
    path('manage-property-ads/', views.manage_property_ads, name='manage_property_ads'),
    path('api/admin/property-ads/<int:ad_id>/approve/', views.api_approve_property_ad, name='api_admin_approve_property_ad'),
    path('api/admin/property-ads/<int:ad_id>/reject/', views.api_reject_property_ad, name='api_admin_reject_property_ad'),
    path('api/admin/property-ads/<int:ad_id>/delete/', views.api_delete_property_ad, name='api_admin_delete_property_ad'),
    path('api/admin/property-ads/<int:ad_id>/detail/', views.api_get_property_ad_detail, name='api_admin_property_ad_detail'),
    path('api/admin/property-edits/<int:edit_id>/approve/', views.api_approve_ad_edit, name='api_admin_approve_ad_edit'),
    path('api/admin/property-edits/<int:edit_id>/reject/', views.api_reject_ad_edit, name='api_admin_reject_ad_edit'),
    path('api/admin/users/<int:user_id>/toggle-access/', views.api_toggle_user_access, name='api_admin_toggle_user_access'),
    path('api/admin/users/<int:user_id>/delete/', views.api_delete_user, name='api_admin_delete_user'),
    path('api/admin/users/monitoring-stats/', views.api_users_monitoring_stats, name='api_admin_users_monitoring_stats'),
    
    # Technical Staff - Inspections
    path('technical/inspections/', views.inspection_list, name='inspection_list'),
    path('technical/inspections/<int:inspection_id>/', views.inspection_detail, name='inspection_detail'),
    path('technical/inspections/create/<int:request_id>/', views.create_inspection, name='create_inspection'),
    
    # Technical Staff - Violations
    path('technical/violations/', views.violation_list, name='violation_list'),
    path('technical/violations/<int:violation_id>/', views.violation_detail, name='violation_detail'),
    
    # Technical Staff - Reports
    path('technical/reports/', views.technical_report_list, name='technical_report_list'),
    path('technical/reports/create/', views.technical_report_create, name='technical_report_create'),
    path('technical/reports/<int:report_id>/', views.technical_report_detail, name='technical_report_detail'),
    path('technical/reports/export/', views.technical_report_export, name='technical_report_export'),
    
    # Technical Staff - Request Assignment
    path('technical/assign-request/<int:request_id>/', views.assign_request_to_engineer, name='assign_request_to_engineer'),

    # Profile and notifications
    path('profile/', views.user_profile, name='user_profile'),
    path('profile/update/', views.update_profile, name='update_profile'),
    path('notifications/', views.notifications, name='notifications'),

    # Services
    path('services/', views.services_catalog, name='services_catalog'),
    
    # Service Form Routes (specific routes must come before generic slug pattern)
    path('services/building-permit/', views.building_permit_form, name='building_permit_form'),
    path('services/building-permit/step1/', views.building_permit_form, name='building_permit_step1'),
    path('services/building-permit/step2/', views.building_permit_step2, name='building_permit_step2'),
    path('services/building-permit/step3/', views.building_permit_step3, name='building_permit_step3'),
    path('services/building-permit/step4/', views.building_permit_step4, name='building_permit_step4'),
    path('services/building-permit/step5/', views.building_permit_step5, name='building_permit_step5'),
    path('services/building-permit/step6/', views.building_permit_step6, name='building_permit_step6'),
    path('services/building-permit/step7/', views.building_permit_step7, name='building_permit_step7'),
    path('services/building-permit/step8/', views.building_permit_step8, name='building_permit_step8'),
    path('services/building-permit/step9/', views.building_permit_step9, name='building_permit_step9'),
    path('services/construction-without-permit/', views.without_permit_form, name='without_permit_form'),
    path('services/construction-without-permit/step1/', views.without_permit_form, name='without_permit_step1'),
    path('services/construction-without-permit/step2/', views.without_permit_step2, name='without_permit_step2'),
    path('services/construction-without-permit/step3/', views.without_permit_step3, name='without_permit_step3'),
    path('services/construction-without-permit/step4/', views.without_permit_step4, name='without_permit_step4'),
    path('services/construction-without-permit/step5/', views.without_permit_step5, name='without_permit_step5'),
    path('services/construction-without-permit/step6/', views.without_permit_step6, name='without_permit_step6'),
    path('services/property-deed-issuance/', views.property_deed_form, name='property_deed_form'),
    path('services/property-deed-issuance/step1/', views.property_deed_form, name='property_deed_step1'),
    path('services/property-deed/step1/', views.property_deed_form, name='property_deed_step1_alt'),
    path('services/property-deed-issuance/step2/', views.property_deed_step2, name='property_deed_step2'),
    path('services/property-deed-issuance/step3/', views.property_deed_step3, name='property_deed_step3'),
    path('services/property-deed-issuance/step4/', views.property_deed_step4, name='property_deed_step4'),
    path('services/land-use-change/', views.land_use_change_form, name='land_use_change_form'),
    path('services/land-use-change/step2/', views.land_use_change_step2, name='land_use_change_step2'),
    path('services/land-use-change/step3/', views.land_use_change_step3, name='land_use_change_step3'),
    path('services/join-development-plan/', views.hadi_plan_form, name='hadi_plan_form'),
    path('services/join-development-plan/step2/', views.hadi_plan_step2, name='hadi_plan_step2'),
    path('services/join-development-plan/step3/', views.hadi_plan_step3, name='hadi_plan_step3'),
    path('services/residence-confirmation/', views.residence_confirmation_form, name='residence_confirmation_form'),
    path('services/residence-confirmation/step1/', views.residence_confirmation_form, name='residence_confirmation_step1'),
    path('services/residence-confirmation/step2/', views.residence_confirmation_step2, name='residence_confirmation_step2'),
    path('services/residence-confirmation/step3/', views.residence_confirmation_step3, name='residence_confirmation_step3'),
    path('services/property-advertisement/', views.property_advertisement_form, name='property_advertisement_form'),
    path('services/property-advertisement/step2/', views.property_advertisement_step2, name='property_advertisement_step2'),
    
    # Generic service patterns (must come after specific routes)
    path('services/<slug:slug>/', views.service_detail, name='service_detail'),
    path('services/<slug:slug>/wizard/<int:step>/', views.service_wizard, name='service_wizard'),
    
    # Property Advertisements
    path('my-property-ads/', views.my_property_ads, name='my_property_ads'),
    path('edit-property-ad/<int:ad_id>/', views.edit_property_ad, name='edit_property_ad'),
    path('view-property-ad/<int:ad_id>/', views.view_property_ad, name='view_property_ad'),

    # Municipality Registration
    path('register-municipality/', views.register_municipality, name='register_municipality'),
    path('municipality/<int:municipality_id>/decree/', views.municipality_decree, name='municipality_decree'),
    path('municipality/<int:municipality_id>/decree/view/', views.municipality_decree_view, name='municipality_decree_view'),
    path('manage-municipalities/', views.manage_municipalities, name='manage_municipalities'),
    path('municipality-history/', views.municipality_history, name='municipality_history'),
    
    # AJAX Geographic APIs
    path('geo/options/', geo_cascade.geo_options, name='geo_options'),
    path('api/get-counties/', views.get_counties, name='get_counties'),
    path('api/get-districts/', views.get_districts, name='get_districts'),
    path('api/get-settlements/', views.get_settlements, name='get_settlements'),
    # Geographic APIs for service forms
    path('api/counties/<int:province_id>/', views.api_get_counties, name='api_get_counties'),
    path('api/districts/<int:county_id>/', views.api_get_districts, name='api_get_districts'),
    path('api/city-villages/<int:district_id>/', views.api_get_city_villages, name='api_get_city_villages'),
    
    # Property Marketplace
    path('properties/', views.property_marketplace, name='property_marketplace'),
    path('property-listings/', views.property_listings, name='property_listings'),
    path('properties/<int:property_id>/', views.property_detail, name='property_detail'),
    path('properties/register/', views.register_property, name='register_property'),

    # Construction Permits
    path('construction-permit/', views.construction_permit_request, name='construction_permit_request'),

    # AI & Analytics
    path('ai-fraud-detection/', views.ai_fraud_detection, name='ai_fraud_detection'),
    path('analytics/', views.analytics_dashboard, name='analytics_dashboard'),

    # Payments and Debts
    path('payments/', views.payments_debts, name='payments_debts'),
    path('payments/pay/<int:property_id>/', views.process_payment, name='process_payment'),

    # New Municipal Services
    path('announcements/', views.announcements, name='announcements'),
    path('manage-announcements/', views.manage_announcements, name='manage_announcements'),
    path('report-violation/', views.report_violation, name='report_violation'),
    path('my-violations/', views.my_violations, name='my_violations'),
    path('suggestions/', views.suggestions, name='suggestions'),
    path('my-suggestions/', views.my_suggestions, name='my_suggestions'),
    path('event-permits/', views.event_permits, name='event_permits'),
    path('my-event-permits/', views.my_event_permits, name='my_event_permits'),
    path('local-businesses/', views.local_businesses, name='local_businesses'),
    path('faq/', views.faq_center, name='faq_center'),
    
    # AutoCAD File Processing
    path('autocad/upload/', views.autocad_upload, name='autocad_upload'),
    path('autocad/result/<int:pk>/', views.autocad_result, name='autocad_result'),
    path('autocad/history/', views.autocad_history, name='autocad_history'),

    # API endpoints
    path('api/provinces/', api_views.get_provinces, name='api_provinces'),
    path('api/provinces/<int:province_id>/counties/', api_views.get_counties, name='api_counties'),
    path('api/counties/<int:county_id>/districts/', api_views.get_districts, name='api_districts'),
    path('api/districts/<int:district_id>/dehestans/', api_views.get_dehestans, name='api_dehestans'),
    path('api/counties/<str:county_id>/villages/', api_views.get_villages, name='api_villages'),
    path('api/properties/search/', api_views.search_properties, name='api_property_search'),
    path('api/properties/<int:property_id>/', api_views.get_property_detail, name='api_property_detail'),
    
    # Geographic Data API endpoints (new cascading dropdown APIs)
    path('api/geo/provinces/', views.api_get_provinces, name='api_geo_provinces'),
    path('api/geo/counties/', views.api_get_counties, name='api_geo_counties'),
    path('api/geo/districts/', views.api_get_districts, name='api_geo_districts'),
    path('api/geo/dehestans/', views.api_get_dehestans, name='api_geo_dehestans'),
    path('api/geo/cities-villages/', views.api_get_city_villages, name='api_geo_cities_villages'),
    path('api/geo/request-city-village/', views.api_request_city_village, name='api_geo_request_city_village'),
    
    # Notification System API
    path('api/notifications/', views.api_notifications_list, name='api_notifications_list'),
    path('api/notifications/<int:notification_id>/mark-read/', views.api_notification_mark_read, name='api_notification_mark_read'),
    path('api/notifications/mark-all-read/', views.api_notifications_mark_all_read, name='api_notifications_mark_all_read'),
    path('api/notifications/<int:notification_id>/delete/', views.api_notification_delete, name='api_notification_delete'),
    
    # Messaging System
    path('messaging/', views.messaging_dashboard, name='messaging_dashboard'),
    path('messaging/conversations/', views.conversation_list, name='conversation_list'),
    path('messaging/conversations/<int:conversation_id>/', views.conversation_detail, name='conversation_detail'),
    path('messaging/start/', views.start_conversation, name='start_conversation'),
    path('messaging/announcements/', views.announcement_list, name='announcement_list'),
    path('messaging/announcements/<int:announcement_id>/', views.announcement_detail, name='announcement_detail'),
    path('messaging/announcements/create/', views.create_announcement, name='create_announcement'),
    path('messaging/announcements/<int:announcement_id>/edit/', views.announcement_edit, name='announcement_edit'),
    path('messaging/announcements/<int:announcement_id>/delete/', views.announcement_delete, name='announcement_delete'),
    path('messaging/conversations/<int:conversation_id>/mute/', views.conversation_mute, name='conversation_mute'),
    path('messaging/conversations/<int:conversation_id>/archive/', views.conversation_archive, name='conversation_archive'),
    path('messaging/conversations/<int:conversation_id>/leave/', views.conversation_leave, name='conversation_leave'),
    path('messaging/conversations/<int:conversation_id>/export/', views.conversation_export, name='conversation_export'),
    
    # Messaging System API
    path('api/messages/', views.api_messages_list, name='api_messages_list'),
    path('api/messages/<int:conversation_id>/', views.api_conversation_messages, name='api_conversation_messages'),
    path('api/messages/send/', views.api_message_send, name='api_message_send'),
    path('api/messages/<int:conversation_id>/reply/', views.api_conversation_reply, name='api_conversation_reply'),
    path('api/messages/<int:message_id>/mark-read/', views.api_message_mark_read, name='api_message_mark_read'),
    path('api/messages/unread-count/', views.api_unread_count, name='api_unread_count'),
    path('api/messages/send-quick/', views.api_send_quick_message, name='api_send_quick_message'),
    
    # Payment API endpoints
    path('api/payments/<int:payment_id>/approve/', views.approve_payment, name='api_approve_payment'),
    path('api/payments/<int:payment_id>/reject/', views.reject_payment, name='api_reject_payment'),
    path('api/payments/export-excel/', views.export_transactions_excel, name='api_export_transactions_excel'),
    
    *admin_api.urlpatterns,
]