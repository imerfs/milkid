# Graph Report - melkID  (2026-10-11)

## Corpus Check
- 190 files · ~280,673 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 34 file(s) not represented in the graph (top: .css 19, .woff2 6, (none) 3)

## Summary
- 3697 nodes · 9137 edges · 173 communities (86 shown, 87 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 721 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `331e4889`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- ExpertTransitions
- request_views.py
- building_permit_form
- misc_views.py
- ThemeManager
- ThemeManager
- import_geographic_data.py
- KeyboardShortcuts
- AdvancedSearch
- models.py
- policy_required
- OnboardingTutorial
- register_role
- htmx.min.js
- GeoCheck
- BreadcrumbNavigation
- ModernUI
- VoiceUI
- AutoCADParser
- tn
- Service
- admin.py
- notify
- .grant
- chart.umd.min.js
- api_views.py
- datetime
- manifest.json
- $
- .update
- validators.py
- sn
- l
- django_db
- jalali_tags.py
- Command
- s
- AI_PROMPT_COMPLETE.md Full Continuation Prompt
- Approval Flow (create Province/County/District/CityVillage, delete request)
- UserProfile Model
- GeographicCascade
- Announcement
- django_core_management_base
- requirements.txt
- middleware.py
- remove
- Property
- jalali-datepicker.js
- client_for
- widgets.py
- n
- make_user
- geographic_selector.js
- main/middleware.py Custom Middleware
- ro
- IMPROVEMENTS.md v2.0.0 Summary
- MunicipalityRegistrationForm
- ho
- JalaliDateInput
- JalaliDateTimeInput
- persian_filters.py
- ci
- sw.js
- ln
- jt
- Django and Django REST Framework Backend
- appointments.py
- test_appointments.py
- login_required
- letter_views.py
- RequestLoggingMiddleware
- EventPermit
- Suggestion
- o
- seo.py
- apps.py
- static/js/improvements.js (loading states, toasts)
- CustomLoginView
- role_required
- test_security.py
- .send
- create_user_profile
- rt
- models_office.py
- letters.py
- package.json
- tree
- roles.py
- Ui
- Design System Master File
- make_payment
- Approval
- xn
- oo
- pathlib
- decorator
- property_advertisement_step2
- Inspection Model
- test_observability.py
- django-template
- test_backup_db.py
- Command
- test_mobile_layout.py
- ft
- N
- de
- PropertyAds
- make_ad
- html
- test_seo_files.py
- Y
- settings.py
- Decisions
- ScriptLoading
- test_seo_pages.py
- pi
- test_self_hosted_assets.py
- ۲. نمی‌شود درست کرد مگر تصمیم بگیرید (پیشنهاد)
- geo_options
- Ti
- bo
- RoleGates
- GeoDedupe
- vi
- ProfileUpdateForm
- Navigation
- PublicPageHead
- Operations: deploy, backups, monitoring
- re
- ConversationState
- manage.py
- harden_server.sh
- server_setup.sh
- healthz
- entrypoint.sh
- access_blocked
- pending_verification
- staff_registration_info
- register_choice
- building_permit_step2
- building_permit_step3
- building_permit_step4
- building_permit_step5
- building_permit_step6
- building_permit_step7
- building_permit_step8
- building_permit_step9
- land_use_change_form
- land_use_change_step2
- land_use_change_step3
- without_permit_form
- without_permit_step2
- without_permit_step3
- without_permit_step4
- without_permit_step5
- without_permit_step6
- residence_confirmation_form
- residence_confirmation_step2
- residence_confirmation_step3

## God Nodes (most connected - your core abstractions)
1. `tn` - 127 edges
2. `client_for()` - 99 edges
3. `policy_required()` - 90 edges
4. `UserProfile` - 87 edges
5. `$` - 86 edges
6. `make_user()` - 83 edges
7. `Notification` - 77 edges
8. `ServiceRequest` - 73 edges
9. `n()` - 59 edges
10. `Province` - 57 edges

## Surprising Connections (you probably didn't know these)
- `1. Role grants (دهیار نقش می‌دهد)` --references--> `RoleGrant`  [INFERRED]
  docs/spec-office-system.md → main/models_office.py
- `create_admin()` --uses--> `UserProfile`  [INFERRED]
  create_admin_user.py → main/models.py
- `create_comprehensive_services()` --uses--> `LocalBusiness`  [INFERRED]
  create_comprehensive_services.py → main/models.py
- `create_comprehensive_services()` --uses--> `Service`  [INFERRED]
  create_comprehensive_services.py → main/models.py
- `create_comprehensive_services()` --uses--> `ServiceStep`  [INFERRED]
  create_comprehensive_services.py → main/models.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Cascading Geographic Selection Flow** — static_js_geographic_selector, geographic_fields_usage_geo_api, geographic_fields_usage_citizen_registration_form, import_geographic_data [EXTRACTED 1.00]
- **Custom Middleware Stack** — improvements_error_handling_middleware, improvements_performance_middleware, improvements_security_headers_middleware, improvements_request_logging_middleware [EXTRACTED 1.00]
- **Municipality Approval Workflow** — municipality_approval_changes_manage_view, municipality_approval_changes_admin_api, municipality_approval_changes_approve_flow, municipality_approval_changes_reject_flow, municipality_approval_changes_cityvillage_model [EXTRACTED 1.00]

## Communities (173 total, 87 thin omitted)

### Community 0 - "ExpertTransitions"
Cohesion: 0.14
Nodes (4): ExpertTransitions, InspectionOutcome, LifecycleCase, MayorTransitions

### Community 1 - "request_views.py"
Cohesion: 0.05
Nodes (64): ConstructionPermitForm, Meta, ContactForm, CustomAuthenticationForm, CustomUserCreationForm, Meta, DocumentUploadForm, Meta (+56 more)

### Community 3 - "misc_views.py"
Cohesion: 0.03
Nodes (37): CityVillageRequest, Meta, LocalBusiness, Meta, Payment, Meta, council_financial_reports(), ai_fraud_detection() (+29 more)

### Community 4 - "ThemeManager"
Cohesion: 0.09
Nodes (4): AnimationManager, DragDropManager, SmartForms, ThemeManager

### Community 5 - "ThemeManager"
Cohesion: 0.09
Nodes (9): ContrastEnhancer, decreaseFontSize(), FocusManager, FontSizeController, increaseFontSize(), setTheme(), ThemeManager, toggleHighContrast() (+1 more)

### Community 6 - "import_geographic_data.py"
Cohesion: 0.09
Nodes (32): import_alborz(), import_ardabil(), import_bushehr(), import_chaharmahal_bakhtiari(), import_east_azerbaijan(), import_fars(), import_gilan(), import_golestan() (+24 more)

### Community 9 - "models.py"
Cohesion: 0.03
Nodes (47): create_admin(), create_all_users(), create_custom_user(), create_sample_users(), show_available_locations(), create_demo_users(), print_user_table(), create_sample_data() (+39 more)

### Community 11 - "policy_required"
Cohesion: 0.02
Nodes (87): policy_required(), ViolationReportForm, Meta, Municipality, Meta, Notification, Meta, PropertyAdvertisementEditLog (+79 more)

### Community 13 - "register_role"
Cohesion: 0.22
Nodes (6): register_accountant(), register_council(), register_dehyari(), register_engineer(), register_inspector(), register_role()

### Community 14 - "htmx.min.js"
Cohesion: 0.05
Nodes (129): et(), A(), Ae(), an(), at(), B(), Be(), bn() (+121 more)

### Community 15 - "GeoCheck"
Cohesion: 0.06
Nodes (16): backfill(), _by_name(), norm(), resolve(), Command, groups(), merge(), pick_kept() (+8 more)

### Community 20 - "tn"
Cohesion: 0.04
Nodes (20): aa(), addBox(), afterDatasetsUpdate(), configure(), d(), es(), generateLabels(), ke() (+12 more)

### Community 21 - "Service"
Cohesion: 0.07
Nodes (12): create_seed_data(), Service, Meta, admin_api_service_create(), admin_api_service_delete(), admin_api_service_toggle_active(), admin_api_service_update(), admin_api_services_list() (+4 more)

### Community 22 - "admin.py"
Cohesion: 0.10
Nodes (19): CityVillageAdmin, CountyAdmin, DistrictAdmin, InspectionAdmin, InspectionDocumentAdmin, NotificationAdmin, PropertyAdmin, ProvinceAdmin (+11 more)

### Community 23 - "notify"
Cohesion: 0.19
Nodes (11): approve(), assign(), _ensure_open(), _finish(), record_inspection(), refer(), reject(), request_documents() (+3 more)

### Community 24 - ".grant"
Cohesion: 0.15
Nodes (4): GrantingRoles, LegacyStaffScreensCannotEscalate, RevokingRoles, Village

### Community 25 - "chart.umd.min.js"
Cohesion: 0.03
Nodes (54): ai(), at(), beforeDatasetDraw(), beforeDatasetsDraw(), beforeDraw(), beforeUpdate(), ca, cn() (+46 more)

### Community 26 - "api_views.py"
Cohesion: 0.13
Nodes (9): get_cities_villages(), get_counties(), get_dehestans(), get_districts(), get_old_counties(), get_property_detail(), get_provinces(), get_villages() (+1 more)

### Community 27 - "datetime"
Cohesion: 0.17
Nodes (3): collect(), Command, Metrics

### Community 28 - "manifest.json"
Cohesion: 0.08
Nodes (23): background_color, categories, description, dir, display, edge_side_panel, preferred_width, icons (+15 more)

### Community 29 - "$"
Cohesion: 0.07
Nodes (48): $, ae(), Be(), Bt(), Ce(), D(), ee(), F() (+40 more)

### Community 30 - ".update"
Cohesion: 0.08
Nodes (20): afterDraw(), afterEvent(), afterUpdate(), Ba(), Bi(), Ci(), Fi(), f() (+12 more)

### Community 31 - "validators.py"
Cohesion: 0.09
Nodes (9): UploadValidationMiddleware, validate_file_content(), validate_file_extension(), validate_file_size(), validate_iranian_mobile(), validate_iranian_national_id(), validate_price(), validate_property_area() (+1 more)

### Community 32 - "sn"
Cohesion: 0.06
Nodes (8): addElements(), an(), as(), en, on, sn, ts(), xt

### Community 33 - "l"
Cohesion: 0.07
Nodes (31): Ae(), Bn(), buildTicks(), _calculateBarIndexPixels(), _calculateBarValuePixels(), _getAxis(), _getAxisCount(), getBasePixel() (+23 more)

### Community 34 - "django_db"
Cohesion: 0.04
Nodes (34): Migration, Migration, Migration, Migration, Migration, Migration, Migration, Migration (+26 more)

### Community 35 - "jalali_tags.py"
Cohesion: 0.13
Nodes (9): english_numbers(), jalali_date(), jalali_datetime(), jalali_now(), jalali_short(), jalali_today(), jalali_verbose(), persian_numbers() (+1 more)

### Community 37 - "s"
Cohesion: 0.06
Nodes (39): beforeLayout(), bs(), Bt(), ct(), dn(), e(), fe(), Fs() (+31 more)

### Community 38 - "AI_PROMPT_COMPLETE.md Full Continuation Prompt"
Cohesion: 0.17
Nodes (12): AI_PROMPT_COMPLETE.md Full Continuation Prompt, Design Guide (blue #007bff, Vazir, RTL cards), Phase 1: UI/UX Improvements, Phase 2: Advanced Features, Phase 3: Final Optimization (PWA, SEO, tests), AI_PROMPT_SHORT.md Short Prompt, Three-Phase Roadmap (UI/UX, features, optimization), Accessibility (+4 more)

### Community 39 - "Approval Flow (create Province/County/District/CityVillage, delete request)"
Cohesion: 0.14
Nodes (12): GEOGRAPHIC_FIELDS_USAGE.md Cascading Geographic Selectors Guide, Cascading Geographic Dropdowns, CitizenRegistrationForm and ProfileUpdateForm, Dehestan Model, Geographic Data API Endpoints (/api/geo/...), admin_api_municipality_action API View, CityVillage Model, Province, County, District Models (+4 more)

### Community 40 - "UserProfile Model"
Cohesion: 0.12
Nodes (17): Database Indexing, Payment Model, Property Model, ServiceRequest Model, UserProfile Model, ViolationReport Model, Multi-Step Service Wizards, RequestDocument Model (+9 more)

### Community 42 - "Announcement"
Cohesion: 0.12
Nodes (10): create_comprehensive_services(), create_sample_announcements(), create_sample_conversations(), create_sample_notifications(), main(), Announcement, Meta, FAQ (+2 more)

### Community 44 - "requirements.txt"
Cohesion: 0.11
Nodes (17): File Upload Security, validate_file_content (anti-spoofing), validate_iranian_national_id, main/validators.py Custom Validators, Code Style (PEP8, Black, Flake8), Testing with pytest, Core Django Dependencies (Django, DRF, cors, simplejwt), File Processing Deps (pillow, ezdxf, matplotlib) (+9 more)

### Community 45 - "middleware.py"
Cohesion: 0.10
Nodes (4): ActiveUserMiddleware, ErrorHandlingMiddleware, PerformanceMonitoringMiddleware, SecurityHeadersMiddleware

### Community 46 - "remove"
Cohesion: 0.08
Nodes (5): d(), Ni, Nn, remove(), zi

### Community 47 - "Property"
Cohesion: 0.11
Nodes (6): create_sample_properties(), Property, Meta, _may_see_unapproved(), property_detail(), property_marketplace()

### Community 48 - "jalali-datepicker.js"
Cohesion: 0.38
Nodes (10): addTodayButton(), clearValidation(), formatDateInput(), handleKeyNavigation(), initializeDatePickers(), setupDateInput(), showValidationError(), showValidationSuccess() (+2 more)

### Community 49 - "client_for"
Cohesion: 0.07
Nodes (9): client_for(), AdminSurfaceIsAdminOnly, urls(), Mailboxes, AnnouncementActions, MessagingActions, MessagingPagesDoNotCrash, RolesPage (+1 more)

### Community 51 - "n"
Cohesion: 0.08
Nodes (8): Be(), fn(), gn(), n(), ne(), numeric(), xn(), Ye()

### Community 52 - "make_user"
Cohesion: 0.09
Nodes (12): make_municipality(), make_request(), make_user(), CouncilVoteAccess, ExpertEndpointsAccess, RequestStatusAccess, Backfill, GeoCheckReportsUnlinkedRows (+4 more)

### Community 53 - "geographic_selector.js"
Cohesion: 0.53
Nodes (9): initGeographicSelectors(), loadCitiesVillages(), loadCounties(), loadDehestans(), loadDistricts(), populateDropdown(), resetDropdown(), setupGeographicSelector() (+1 more)

### Community 54 - "main/middleware.py Custom Middleware"
Cohesion: 0.14
Nodes (15): 500.html Error Page, ErrorHandlingMiddleware, ManifestStaticFilesStorage, main/middleware.py Custom Middleware, Migration 0018_add_performance_indexes, PerformanceMonitoringMiddleware, RequestLoggingMiddleware, Security Headers (+7 more)

### Community 55 - "ro"
Cohesion: 0.07
Nodes (24): ao(), average(), co(), da(), dataset(), Do(), getCenterPoint(), index() (+16 more)

### Community 56 - "IMPROVEMENTS.md v2.0.0 Summary"
Cohesion: 0.13
Nodes (16): IMPROVEMENTS.md v2.0.0 Summary, Environment Variables (.env) for SECRET_KEY and DEBUG, Suggested Next Phases (UI/UX, WebSocket, payment gateways), Password Policy, MelkID README, Installation and Setup, MelkID Rural/Municipal Services System, Project Structure (django_project, main, static, logs) (+8 more)

### Community 57 - "MunicipalityRegistrationForm"
Cohesion: 0.09
Nodes (7): CitizenRegistrationForm, Meta, MunicipalityRegistrationForm, Meta, _form_class(), FormsAreWired, register_municipality()

### Community 58 - "ho"
Cohesion: 0.08
Nodes (11): b(), buildLookupTable(), _generate(), _getTimestampsForTable(), ho(), init(), initOffsets(), lt() (+3 more)

### Community 60 - "JalaliDateTimeInput"
Cohesion: 0.18
Nodes (3): AnnouncementForm, Meta, JalaliDateTimeInput

### Community 61 - "persian_filters.py"
Cohesion: 0.24
Nodes (3): dict_get(), persian_date(), persian_date_verbose()

### Community 62 - "ci"
Cohesion: 0.07
Nodes (4): ci, q, W, ti()

### Community 65 - "jt"
Cohesion: 0.06
Nodes (11): color(), cs, hs, It(), jt(), kt(), mt(), qt() (+3 more)

### Community 66 - "Django and Django REST Framework Backend"
Cohesion: 0.29
Nodes (7): replit.md Overview, Django and Django REST Framework Backend, Frontend Stack (Bootstrap 5 RTL, Tailwind, Font Awesome, Vazirmatn), Notification System, Potential Third-Party Services (SMS, Payment, S3, Email), jdatetime Persian Calendar, Persian Language and RTL Support

### Community 67 - "appointments.py"
Cohesion: 0.11
Nodes (22): _aware(), book(), _bookable(), day_strip(), decide(), free_slots(), _grid(), jalali_label() (+14 more)

### Community 68 - "test_appointments.py"
Cohesion: 0.11
Nodes (7): Availability, Booking, Clinic, day(), jalali_weekday(), MyAppointments, Slots

### Community 69 - "login_required"
Cohesion: 0.07
Nodes (15): can(), decorator(), wrapped(), role_of(), analytics_dashboard(), dashboard(), dashboard_delete_document(), dashboard_download_document() (+7 more)

### Community 70 - "letter_views.py"
Cohesion: 0.14
Nodes (22): office(), seo(), OfficeError, get_for(), new_token(), unread_count(), visible_to(), _compose_page() (+14 more)

### Community 72 - "EventPermit"
Cohesion: 0.29
Nodes (4): EventPermitForm, Meta, EventPermit, Meta

### Community 73 - "Suggestion"
Cohesion: 0.29
Nodes (4): SuggestionForm, Meta, Suggestion, Meta

### Community 74 - "o"
Cohesion: 0.10
Nodes (16): a(), determineDataLimits(), Di(), g(), g(), m(), o(), p() (+8 more)

### Community 75 - "seo.py"
Cohesion: 0.13
Nodes (16): absolute(), base_url(), breadcrumb_ld(), breadcrumbs(), ld_dumps(), organization(), page_context(), service_ld() (+8 more)

### Community 77 - "static/js/improvements.js (loading states, toasts)"
Cohesion: 0.50
Nodes (4): static/js/improvements.js (loading states, toasts), Loading States, Navigation (breadcrumb, back to top), User Feedback (toasts, alerts)

### Community 80 - "test_security.py"
Cohesion: 0.09
Nodes (7): AuthThrottleMiddleware, client_ip(), AnonymousAccessTests, LoginThrottleTests, MediaAuthTests, StaffRegistrationTests, UploadGuardTests

### Community 81 - ".send"
Cohesion: 0.13
Nodes (4): Attachments, Composing, Office, Replies

### Community 86 - "models_office.py"
Cohesion: 0.08
Nodes (17): 1. Role grants (دهیار نقش می‌دهد), 2. Official letters (مکاتبات اداری), 3. Appointments (وقت‌دهی), Definition of done (from the standards sheet, translated), Office system: letters, appointments, role grants, Status against the 14-layer sheet, Appointment, Meta (+9 more)

### Community 87 - "letters.py"
Cohesion: 0.17
Nodes (16): providers_for(), Invalid, RateLimited, allowed_recipients(), _check_files(), _clean(), compose(), mailbox() (+8 more)

### Community 88 - "package.json"
Cohesion: 0.09
Nodes (22): description, devDependencies, bootstrap, chart.js, @fortawesome/fontawesome-free, htmx.org, material-icons, sortablejs (+14 more)

### Community 89 - "tree"
Cohesion: 0.18
Nodes (5): MunicipalityRegistration, OptionsEndpoint, RegistrationPages, selects(), tree()

### Community 90 - "roles.py"
Cohesion: 0.15
Nodes (12): NotFound, toggle_archive(), grant_role(), municipality_for(), revoke_role(), staff_and_candidates(), _target(), village_of() (+4 more)

### Community 92 - "Design System Master File"
Cohesion: 0.11
Nodes (17): Additional Forbidden Patterns, Anti-Patterns (Do NOT Use), Buttons, Cards, Color Palette, Component Specs, Design System Master File, Global Rules (+9 more)

### Community 93 - "make_payment"
Cohesion: 0.18
Nodes (3): make_payment(), PaymentReviewAccess, AccountantDashboardPage

### Community 94 - "Approval"
Cohesion: 0.21
Nodes (3): Approval, Registration, registration_data()

### Community 96 - "oo"
Cohesion: 0.14
Nodes (8): ei(), io(), je(), no(), oo, qe(), ze(), zi()

### Community 97 - "pathlib"
Cohesion: 0.16
Nodes (3): ContainerSetup, read(), ViewImports

### Community 103 - "test_observability.py"
Cohesion: 0.13
Nodes (4): Healthz, HealthzOverPlainHttp, JsonLogs, SentrySetup

### Community 113 - "Command"
Cohesion: 0.19
Nodes (3): Command, prune(), PostgresBackup

### Community 114 - "test_mobile_layout.py"
Cohesion: 0.18
Nodes (4): AdminCharts, NoScrollHijacking, PanelMenusOnPhones, PhoneStylesheet

### Community 117 - "de"
Cohesion: 0.21
Nodes (5): ce(), de, dt(), he(), C()

### Community 118 - "PropertyAds"
Cohesion: 0.14
Nodes (3): PropertyAds, Services, StaticPages

### Community 119 - "make_ad"
Cohesion: 0.26
Nodes (3): make_ad(), AdVisibility, ListingFilters

### Community 120 - "html"
Cohesion: 0.27
Nodes (5): make_service(), html(), InternalLinks, jsonld(), StructuredData

### Community 121 - "test_seo_files.py"
Cohesion: 0.22
Nodes (3): LlmsTxt, RobotsTxt, SitemapXml

### Community 126 - "test_seo_pages.py"
Cohesion: 0.26
Nodes (5): IconFiles, meta(), NotFoundPage, PrivatePagesAreNoindex, ServiceDetailSeo

### Community 129 - "۲. نمی‌شود درست کرد مگر تصمیم بگیرید (پیشنهاد)"
Cohesion: 0.18
Nodes (10): الف) منوی حسابداری (۲۸ مورد در پنل حسابدار), ب) پنل دهیار: حدود ۱۲۰ دکمه روی داده‌ی ساختگی, ت) پنل ناظر فنی و کارشناس (۶۰ دکمه: «ثبت گزارش»، «صدور گواهی»، «ثبت اخطاریه»…), ث) «خروجی Excel/PDF», ج) تنظیمات و حساب, دکمه‌های پنل‌ها: چه چیزی درست شد و چه چیزی نیاز به تصمیم دارد, پ) ۳۷ صفحه که قالبشان وجود ندارد (خطای ۵۰۰), چ) آیکن‌ها (+2 more)

### Community 130 - "geo_options"
Cohesion: 0.22
Nodes (6): ancestors(), apply_to_form(), geo_options(), label(), select_attrs(), to_int()

### Community 132 - "bo"
Cohesion: 0.22
Nodes (3): bo, H(), xo()

### Community 136 - "ProfileUpdateForm"
Cohesion: 0.29
Nodes (4): ProfileUpdateForm, Meta, update_profile(), user_profile()

### Community 139 - "Operations: deploy, backups, monitoring"
Cohesion: 0.33
Nodes (5): Backups, Monitoring, Operations: deploy, backups, monitoring, Restore drill (do it once, then every month, and write down how long it took), Two ways to run the site

## Ambiguous Edges - Review These
- `Phase 1: UI/UX Improvements` → `Mobile Responsiveness`  [AMBIGUOUS]
  AI_PROMPT_COMPLETE.md · relation: conceptually_related_to

## Knowledge Gaps
- **51 isolated node(s):** `DEBIAN_FRONTEND`, `DEBIAN_FRONTEND`, `@fortawesome/fontawesome-free`, `bootstrap`, `chart.js` (+46 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1099 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **87 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Geographic Data API Endpoints (/api/geo/...)` connect `Approval Flow (create Province/County/District/CityVillage, delete request)` to `geographic_selector.js`, `import_geographic_data.py`?**
  _High betweenness centrality (0.034) - this node is a cross-community bridge._
- **Are the 48 inferred relationships involving `UserProfile` (e.g. with `create_admin()` and `create_all_users()`) actually correct?**
  _`UserProfile` has 48 INFERRED edges - model-reasoned connections that need verification._
- **What connects `DEBIAN_FRONTEND`, `DEBIAN_FRONTEND`, `@fortawesome/fontawesome-free` to the rest of the system?**
  _51 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `ExpertTransitions` be split into smaller, more focused modules?**
  _Cohesion score 0.14333333333333334 - nodes in this community are weakly interconnected._
- **Why does `make_user()` connect `make_user` to `ExpertTransitions`, `test_appointments.py`, `RoleGates`, `GeoDedupe`, `models.py`, `client_for`, `.send`, `test_mobile_layout.py`, `make_ad`, `.grant`, `tree`, `test_seo_pages.py`, `datetime`, `make_payment`, `Approval`?**
  _High betweenness centrality (0.030) - this node is a cross-community bridge._
- **Should `request_views.py` be split into smaller, more focused modules?**
  _Cohesion score 0.04613975767821921 - nodes in this community are weakly interconnected._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `Phase 1: UI/UX Improvements` and `Mobile Responsiveness`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._