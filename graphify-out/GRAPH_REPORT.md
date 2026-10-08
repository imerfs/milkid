# Graph Report - melkID  (2026-10-08)

## Corpus Check
- 224 files · ~247,735 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 14 file(s) not represented in the graph (top: .css 11, .example 1, (none) 1)

## Summary
- 1608 nodes · 3670 edges · 112 communities (51 shown, 61 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 426 edges (avg confidence: 0.94)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Tests and URL config
- Sample conversations seed
- Service wizard and forms
- AutoCAD, Payment, Property data
- Modern interactions JS
- Accessibility JS
- Geographic data import
- Keyboard shortcuts JS
- Advanced search
- Sample geography seed
- User creation scripts
- Council and access policy
- Onboarding tutorial JS
- Registration forms
- Notifications and admin dashboard
- UserProfile and roles
- Breadcrumb navigation JS
- ModernUI JS
- Voice UI JS
- Search and DXF deps
- Forms module
- Services seed data
- Django admin
- Request lifecycle
- ServiceRequest model
- Gesture navigation JS
- Geography API
- Municipality and violations
- PWA manifest
- Admin API endpoints
- Expert (engineer) views
- Validators
- Property advertisements
- Council and inspections
- Migrations (early)
- Jalali template tags
- DB optimize command
- Migrations (mid)
- AI prompt and roadmap docs
- Municipality approval docs
- Core models doc
- Geographic cascade JS
- Sample messages seed
- Settings and seed_demo
- Dev tooling and deps docs
- Middleware and DB tuning
- Migrations (late)
- Property search
- Jalali datepicker JS
- Custom users seed
- Jalali widgets
- Reports
- Mayor request actions
- Geographic selector JS
- Checklist and error handling
- Services and FAQ seed
- Improvements doc
- Municipality registration form
- Request documents
- Jalali date input
- Jalali datetime input
- Persian filters
- Geographic fields doc
- Service worker
- Security and deployment docs
- Roles and dashboards docs
- Replit overview doc
- Authentication form
- Upload security
- Access policy core
- Error middleware
- Request logging
- Event permits
- Suggestions
- City/village requests
- Community 75
- Community 76
- Community 77
- Community 78
- Community 79
- Community 80
- Community 81
- Community 83
- Community 84
- Community 86
- Community 87
- Community 88
- Community 89
- Community 90
- Community 91
- Community 92
- Community 93
- Community 94
- Community 95
- Community 96
- Community 97
- Community 98
- Community 99
- Community 102
- Community 110

## God Nodes (most connected - your core abstractions)
1. `UserProfile` - 73 edges
2. `ServiceRequest` - 73 edges
3. `Notification` - 65 edges
4. `policy_required()` - 54 edges
5. `Municipality` - 41 edges
6. `Property` - 38 edges
7. `KeyboardShortcuts` - 38 edges
8. `import_province_data()` - 37 edges
9. `Province` - 36 edges
10. `County` - 36 edges

## Surprising Connections (you probably didn't know these)
- `create_admin()` --uses--> `UserProfile`  [INFERRED]
  create_admin_user.py → main/models.py
- `create_all_users()` --uses--> `UserProfile`  [INFERRED]
  create_all_users.py → main/models.py
- `create_comprehensive_services()` --uses--> `Announcement`  [INFERRED]
  create_comprehensive_services.py → main/models.py
- `create_comprehensive_services()` --uses--> `Service`  [INFERRED]
  create_comprehensive_services.py → main/models.py
- `create_comprehensive_services()` --uses--> `ServiceStep`  [INFERRED]
  create_comprehensive_services.py → main/models.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Custom Middleware Stack** — improvements_error_handling_middleware, improvements_performance_middleware, improvements_security_headers_middleware, improvements_request_logging_middleware [EXTRACTED 1.00]
- **Municipality Approval Workflow** — municipality_approval_changes_manage_view, municipality_approval_changes_admin_api, municipality_approval_changes_approve_flow, municipality_approval_changes_reject_flow, municipality_approval_changes_cityvillage_model [EXTRACTED 1.00]
- **Cascading Geographic Selection Flow** — static_js_geographic_selector, geographic_fields_usage_geo_api, geographic_fields_usage_citizen_registration_form, import_geographic_data [EXTRACTED 1.00]

## Communities (112 total, 61 thin omitted)

### Community 0 - "Tests and URL config"
Cohesion: 0.06
Nodes (15): client_for(), make_municipality(), make_payment(), make_request(), make_user(), PaymentReviewAccess, RoleGates, CouncilVoteAccess (+7 more)

### Community 1 - "Sample conversations seed"
Cohesion: 0.17
Nodes (16): create_sample_conversations(), ContactForm, announcement_detail(), announcement_list(), api_mark_message_read(), api_send_quick_message(), api_unread_count(), conversation_detail() (+8 more)

### Community 2 - "Service wizard and forms"
Cohesion: 0.04
Nodes (24): ServiceWizardStepForm, ServiceStep, building_permit_form(), building_permit_step2(), building_permit_step3(), building_permit_step4(), building_permit_step5(), building_permit_step6() (+16 more)

### Community 3 - "AutoCAD, Payment, Property data"
Cohesion: 0.04
Nodes (25): AutoCADFile, Payment, PropertyData, dashboard_payments(), ai_fraud_detection(), api_conversation_messages(), api_conversation_reply(), api_get_city_villages() (+17 more)

### Community 4 - "Modern interactions JS"
Cohesion: 0.09
Nodes (4): AnimationManager, DragDropManager, SmartForms, ThemeManager

### Community 5 - "Accessibility JS"
Cohesion: 0.09
Nodes (9): ContrastEnhancer, decreaseFontSize(), FocusManager, FontSizeController, increaseFontSize(), setTheme(), ThemeManager, toggleHighContrast() (+1 more)

### Community 6 - "Geographic data import"
Cohesion: 0.09
Nodes (32): import_alborz(), import_ardabil(), import_bushehr(), import_chaharmahal_bakhtiari(), import_east_azerbaijan(), import_fars(), import_gilan(), import_golestan() (+24 more)

### Community 9 - "Sample geography seed"
Cohesion: 0.11
Nodes (15): show_available_locations(), create_sample_data(), clear_all_data(), run_import(), CityVillage, County, District, Province (+7 more)

### Community 10 - "User creation scripts"
Cohesion: 0.10
Nodes (6): create_admin(), create_all_users(), create_demo_users(), print_user_table(), create_sample_properties(), create_user()

### Community 11 - "Council and access policy"
Cohesion: 0.06
Nodes (17): policy_required(), council_financial_reports(), council_request_detail(), council_review_requests(), council_submit_vote(), council_voting_list(), mayor_announcements_list(), mayor_staff_add() (+9 more)

### Community 13 - "Registration forms"
Cohesion: 0.09
Nodes (13): CustomUserCreationForm, ProfileUpdateForm, access_blocked(), pending_verification(), register_accountant(), register_choice(), register_council(), register_dehyari() (+5 more)

### Community 14 - "Notifications and admin dashboard"
Cohesion: 0.07
Nodes (14): Notification, admin_api_municipality_action(), admin_dashboard(), council_add_comment(), dashboard_messages(), notifications(), api_notification_delete(), api_notification_mark_read() (+6 more)

### Community 15 - "UserProfile and roles"
Cohesion: 0.07
Nodes (11): UserProfile, admin_api_reports_chart_data(), admin_api_user_change_role(), admin_api_user_toggle_active(), admin_api_users_list(), manage_users(), analytics_dashboard(), dashboard() (+3 more)

### Community 20 - "Forms module"
Cohesion: 0.09
Nodes (10): AnnouncementForm, CitizenRegistrationForm, ConstructionPermitForm, DocumentUploadForm, Meta, PropertyAdvertisementForm, PropertyRegistrationForm, ServiceRequestForm (+2 more)

### Community 21 - "Services seed data"
Cohesion: 0.07
Nodes (11): create_seed_data(), Service, admin_api_service_create(), admin_api_service_delete(), admin_api_service_toggle_active(), admin_api_service_update(), admin_api_services_list(), home() (+3 more)

### Community 22 - "Django admin"
Cohesion: 0.11
Nodes (19): CityVillageAdmin, CountyAdmin, DistrictAdmin, InspectionAdmin, InspectionDocumentAdmin, NotificationAdmin, PropertyAdmin, ProvinceAdmin (+11 more)

### Community 23 - "Request lifecycle"
Cohesion: 0.14
Nodes (14): approve(), assign(), _ensure_open(), _finish(), record_inspection(), refer(), reject(), request_documents() (+6 more)

### Community 24 - "ServiceRequest model"
Cohesion: 0.07
Nodes (11): ServiceRequest, admin_api_reports_export_excel(), manage_requests(), council_dashboard(), dashboard_request_detail(), dashboard_track_requests(), user_dashboard(), my_requests() (+3 more)

### Community 26 - "Geography API"
Cohesion: 0.13
Nodes (9): get_cities_villages(), get_counties(), get_dehestans(), get_districts(), get_old_counties(), get_property_detail(), get_provinces(), get_villages() (+1 more)

### Community 27 - "Municipality and violations"
Cohesion: 0.09
Nodes (10): Municipality, ViolationReport, admin_api_municipalities_list(), manage_municipalities(), dehyari_dashboard(), mayor_requests_list(), mayor_violation_create(), mayor_violation_update() (+2 more)

### Community 28 - "PWA manifest"
Cohesion: 0.08
Nodes (23): background_color, categories, description, dir, display, edge_side_panel, preferred_width, icons (+15 more)

### Community 29 - "Admin API endpoints"
Cohesion: 0.09
Nodes (10): api_approve_ad_edit(), api_approve_property_ad(), api_delete_property_ad(), api_delete_user(), api_get_property_ad_detail(), api_reject_ad_edit(), api_reject_property_ad(), api_toggle_user_access() (+2 more)

### Community 30 - "Expert (engineer) views"
Cohesion: 0.16
Nodes (8): api_expert_add_technical_report(), api_expert_approve_direct(), api_expert_forward_request(), api_expert_reject_request(), api_expert_request_details(), api_expert_request_documents(), dehyari_expert_dashboard(), _json_body()

### Community 31 - "Validators"
Cohesion: 0.11
Nodes (8): validate_file_content(), validate_file_extension(), validate_file_size(), validate_iranian_mobile(), validate_iranian_national_id(), validate_price(), validate_property_area(), validate_year()

### Community 32 - "Property advertisements"
Cohesion: 0.10
Nodes (6): PropertyAdvertisement, PropertyAdvertisementEditLog, manage_property_ads(), my_property_ads(), property_detail(), view_property_ad()

### Community 33 - "Council and inspections"
Cohesion: 0.11
Nodes (7): Announcement, CouncilComment, Inspection, InspectionDocument, Meta, TechnicalReport, Vote

### Community 34 - "Migrations (early)"
Cohesion: 0.12
Nodes (8): Migration, Migration, Migration, Migration, Migration, Migration, Migration, Migration

### Community 35 - "Jalali template tags"
Cohesion: 0.18
Nodes (7): english_numbers(), jalali_date(), jalali_datetime(), jalali_short(), jalali_verbose(), persian_numbers(), time_since_jalali()

### Community 37 - "Migrations (mid)"
Cohesion: 0.13
Nodes (7): Migration, Migration, Migration, Migration, Migration, Migration, Migration

### Community 38 - "AI prompt and roadmap docs"
Cohesion: 0.17
Nodes (12): AI_PROMPT_COMPLETE.md Full Continuation Prompt, Design Guide (blue #007bff, Vazir, RTL cards), Phase 1: UI/UX Improvements, Phase 2: Advanced Features, Phase 3: Final Optimization (PWA, SEO, tests), AI_PROMPT_SHORT.md Short Prompt, Three-Phase Roadmap (UI/UX, features, optimization), Accessibility (+4 more)

### Community 39 - "Municipality approval docs"
Cohesion: 0.18
Nodes (9): admin_api_municipality_action API View, CityVillage Model, manage_municipalities.html Template, manage_municipalities View, Municipality Approval Test Scripts, ViolationReport Model, Announcement System, Municipality Model (+1 more)

### Community 40 - "Core models doc"
Cohesion: 0.18
Nodes (13): Database Indexing, Payment Model, Property Model, ServiceRequest Model, UserProfile Model, Multi-Step Service Wizards, RequestDocument Model, Council Voting (+5 more)

### Community 42 - "Sample messages seed"
Cohesion: 0.20
Nodes (4): create_sample_announcements(), create_sample_notifications(), main(), main()

### Community 44 - "Dev tooling and deps docs"
Cohesion: 0.17
Nodes (11): Code Style (PEP8, Black, Flake8), Testing with pytest, Core Django Dependencies (Django, DRF, cors, simplejwt), File Processing Deps (pillow, ezdxf, matplotlib), Monitoring Deps (sentry-sdk, django-silk), psycopg2-binary PostgreSQL Driver, Testing Deps (pytest, pytest-django, factory-boy), AutoCAD DWG/DXF Integration (ezdxf) (+3 more)

### Community 46 - "Migrations (late)"
Cohesion: 0.18
Nodes (5): Migration, Migration, Migration, Migration, Migration

### Community 47 - "Property search"
Cohesion: 0.18
Nodes (3): PropertySearchForm, Property, property_marketplace()

### Community 48 - "Jalali datepicker JS"
Cohesion: 0.38
Nodes (10): addTodayButton(), clearValidation(), formatDateInput(), handleKeyNavigation(), initializeDatePickers(), setupDateInput(), showValidationError(), showValidationSuccess() (+2 more)

### Community 49 - "Custom users seed"
Cohesion: 0.22
Nodes (4): create_custom_user(), create_sample_users(), Dehestan, api_get_dehestans()

### Community 52 - "Mayor request actions"
Cohesion: 0.22
Nodes (5): _in_municipality(), _managed_municipality(), mayor_request_approve(), mayor_request_assign(), mayor_request_reject()

### Community 53 - "Geographic selector JS"
Cohesion: 0.53
Nodes (9): initGeographicSelectors(), loadCitiesVillages(), loadCounties(), loadDehestans(), loadDistricts(), populateDropdown(), resetDropdown(), setupGeographicSelector() (+1 more)

### Community 54 - "Checklist and error handling"
Cohesion: 0.25
Nodes (8): 500.html Error Page, ErrorHandlingMiddleware, main/middleware.py Custom Middleware, Migration 0018_add_performance_indexes, PerformanceMonitoringMiddleware, RequestLoggingMiddleware, Logging System (django.log, django_errors.log, security.log), Performance Monitoring (slow requests >1s)

### Community 55 - "Services and FAQ seed"
Cohesion: 0.28
Nodes (3): create_comprehensive_services(), FAQ, LocalBusiness

### Community 56 - "Improvements doc"
Cohesion: 0.22
Nodes (9): IMPROVEMENTS.md v2.0.0 Summary, Environment Variables (.env) for SECRET_KEY and DEBUG, Suggested Next Phases (UI/UX, WebSocket, payment gateways), Password Policy, MelkID README, Installation and Setup, MelkID Rural/Municipal Services System, Project Structure (django_project, main, static, logs) (+1 more)

### Community 58 - "Request documents"
Cohesion: 0.22
Nodes (4): RequestDocument, dashboard_delete_document(), dashboard_download_document(), dashboard_upload_document()

### Community 62 - "Geographic fields doc"
Cohesion: 0.25
Nodes (7): GEOGRAPHIC_FIELDS_USAGE.md Cascading Geographic Selectors Guide, Cascading Geographic Dropdowns, CitizenRegistrationForm and ProfileUpdateForm, Dehestan Model, Geographic Data API Endpoints (/api/geo/...), Province, County, District Models, Geographic Hierarchy (Province>County>District>City/Village>Dehestan)

### Community 64 - "Security and deployment docs"
Cohesion: 0.29
Nodes (7): ManifestStaticFilesStorage, Security Headers, SecurityHeadersMiddleware, Caching (LocMem dev / Redis prod), Deployment (Docker, Gunicorn, production checklist), Security Settings, django-redis and redis

### Community 65 - "Roles and dashboards docs"
Cohesion: 0.29
Nodes (7): User Roles (9 roles), WARP.md Development Guide, Development Commands (manage.py, seed scripts), Role-Based Access Control, Role-Based Dashboards, role_required Decorator, Seed Data Scripts

### Community 66 - "Replit overview doc"
Cohesion: 0.29
Nodes (7): replit.md Overview, Django and Django REST Framework Backend, Frontend Stack (Bootstrap 5 RTL, Tailwind, Font Awesome, Vazirmatn), Notification System, Potential Third-Party Services (SMS, Payment, S3, Email), jdatetime Persian Calendar, Persian Language and RTL Support

### Community 68 - "Upload security"
Cohesion: 0.33
Nodes (6): File Upload Security, validate_file_content (anti-spoofing), validate_iranian_national_id, main/validators.py Custom Validators, python-magic File Content Validation, Persian Data Validation (national ID, mobile)

### Community 69 - "Access policy core"
Cohesion: 0.33
Nodes (4): can(), decorator(), wrapped(), role_of()

### Community 77 - "Community 77"
Cohesion: 0.50
Nodes (4): static/js/improvements.js (loading states, toasts), Loading States, Navigation (breadcrumb, back to top), User Feedback (toasts, alerts)

## Ambiguous Edges - Review These
- `Mobile Responsiveness` → `Phase 1: UI/UX Improvements`  [AMBIGUOUS]
  AI_PROMPT_COMPLETE.md · relation: conceptually_related_to

## Knowledge Gaps
- **94 isolated node(s):** `Migration`, `Migration`, `Migration`, `Migration`, `Migration` (+89 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 623 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **61 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Mobile Responsiveness` and `Phase 1: UI/UX Improvements`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `Geographic Data API Endpoints (/api/geo/...)` connect `Geographic fields doc` to `Geographic selector JS`, `Geographic data import`?**
  _High betweenness centrality (0.097) - this node is a cross-community bridge._
- **Are the 39 inferred relationships involving `UserProfile` (e.g. with `create_admin()` and `create_all_users()`) actually correct?**
  _`UserProfile` has 39 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Migration`, `Migration`, `Migration` to the rest of the system?**
  _94 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Tests and URL config` be split into smaller, more focused modules?**
  _Cohesion score 0.06265822784810127 - nodes in this community are weakly interconnected._
- **Why does `Cascading Geographic Dropdowns` connect `Geographic fields doc` to `Geographic selector JS`?**
  _High betweenness centrality (0.079) - this node is a cross-community bridge._
- **Are the 46 inferred relationships involving `ServiceRequest` (e.g. with `ConstructionPermitForm` and `ServiceRequestForm`) actually correct?**
  _`ServiceRequest` has 46 INFERRED edges - model-reasoned connections that need verification._