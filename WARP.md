# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

MelkID is a comprehensive Persian (Farsi) web application for digital municipal and rural property services. It serves as a smart municipal service system for rural areas in Iran, providing services like building permits, property deed issuance, residence confirmation, and property management with full RTL (right-to-left) support.

## Development Commands

### Environment Setup
```powershell
# Install dependencies using Poetry
poetry install

# Activate virtual environment
poetry shell

# Set up environment variables for Replit deployment
$env:REPLIT_DOMAINS = "localhost,127.0.0.1"
$env:PGDATABASE = "your_db_name"
$env:PGUSER = "your_db_user" 
$env:PGPASSWORD = "your_db_password"
$env:PGHOST = "your_db_host"
$env:PGPORT = "5432"
```

### Database Operations
```powershell
# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Load sample data (use the provided seed scripts)
python create_seed_data.py
python create_sample_properties.py
python create_admin_user.py
python create_comprehensive_services.py
```

### Running the Application
```powershell
# Development server
python manage.py runserver

# Run on specific port
python manage.py runserver 0.0.0.0:8000

# Collect static files for production
python manage.py collectstatic --noinput
```

### Testing and Development
```powershell
# Run Django shell for testing
python manage.py shell

# Create new migrations after model changes
python manage.py makemigrations

# Check for issues
python manage.py check

# Run specific management commands
python manage.py dbshell
```

## Architecture Overview

### Core Architecture Pattern
- **Framework**: Django 5.1.3 with Django REST Framework
- **Pattern**: Multi-tenant municipal service platform with role-based access control
- **Database**: PostgreSQL with SSL (Neon cloud database)
- **Authentication**: Extended Django User model + JWT for API access
- **UI**: Server-side rendered templates with Bootstrap 5 RTL + modern JavaScript

### Key Architectural Components

#### 1. User Management & Role System
The application implements a sophisticated role-based access control system:

- **UserProfile Model**: Extends Django User with Persian-specific fields (national ID, mobile validation)
- **Roles**: `citizen`, `owner`, `resident`, `dehyari` (mayor), `engineer`, `inspector`, `accountant`, `council`, `admin`
- **Geographic Hierarchy**: Province → County → District → City/Village → Dehestan (rural council area)
- **Permission System**: Each role has specific dashboard views and capabilities

#### 2. Service Request Workflow Engine
Complex multi-step service processing system:

- **Service & ServiceStep Models**: Define configurable multi-step workflows
- **ServiceRequest Model**: Tracks request lifecycle with status management
- **Document Management**: File upload system with validation
- **Status Flow**: `pending` → `in_review` → `approved/rejected` → `completed`
- **Assignment System**: Requests can be assigned to specific staff members

#### 3. Property Management System
Comprehensive property and real estate management:

- **Property Model**: Detailed property records with Persian address validation
- **Usage Types**: Residential, commercial, agricultural, industrial, mixed
- **Financial Integration**: Property taxes, assessments, market valuations
- **Geographic Coordination**: Latitude/longitude support for future mapping

#### 4. Municipal Administration Framework
Multi-municipality support system:

- **Municipality Model**: Registration and management of rural councils (dehyari)
- **Staff Management**: Hierarchical staff assignment per municipality
- **Violation Reporting**: Construction violation tracking and resolution
- **Payment Processing**: Tax collection and fee management
- **Announcement System**: Role-targeted notifications

#### 5. Technical Review & Inspection System
Professional workflow for construction oversight:

- **Inspection Model**: Scheduled property inspections by technical staff
- **TechnicalReport Model**: Formal reports by engineers and inspectors
- **AutoCAD Integration**: DWG/DXF file processing for property data extraction
- **PropertyData Model**: Extracted boundary and measurement data from CAD files

### Data Flow Patterns

#### Request Processing Flow
1. **Citizen Submission**: User submits service request through role-specific dashboard
2. **Initial Review**: Municipality staff (dehyari) reviews and assigns to specialists
3. **Technical Assessment**: Engineers/inspectors conduct reviews and site visits
4. **Council Voting**: Complex requests require council member votes
5. **Final Approval**: Municipality finalizes decision with notifications
6. **Documentation**: All steps logged with audit trail

#### Role-Based Dashboard Architecture
Each role has a specialized dashboard with targeted functionality:

- **Citizens/Owners**: Request submission, tracking, payments, property ads
- **Dehyari (Mayor)**: Staff management, request approval, announcements, violations
- **Engineers**: Technical reviews, inspection scheduling, report generation  
- **Council Members**: Voting on requests, financial oversight, policy decisions
- **Accountants**: Financial reporting, payment processing, tax management
- **Admins**: System-wide user management, municipality registration

### Persian Language & RTL Considerations
- **Language**: All UI text, model verbose names, and user content in Persian (Farsi)
- **RTL Layout**: Bootstrap 5 RTL implementation throughout
- **Persian Fonts**: Vazirmatn font family for optimal Persian typography
- **Date Handling**: jdatetime library for Persian calendar support
- **Input Validation**: Persian-specific validators for national IDs and mobile numbers

### Integration Points
- **Database**: PostgreSQL with SSL (currently Neon cloud service)
- **File Storage**: Local filesystem (configurable for cloud storage)
- **SMS/Email**: Placeholder integration points for notifications
- **Payment Gateways**: Framework ready for Iranian payment processors
- **CAD Processing**: ezdxf library for AutoCAD file analysis
- **Government APIs**: Mock integration structure for official document verification

### Performance & Scalability Considerations
- **Pagination**: Implemented throughout for large datasets (20 items per page standard)
- **Query Optimization**: select_related and prefetch_related usage in complex views
- **Caching Strategy**: Django session framework, ready for Redis integration
- **File Management**: Organized upload directories by model type
- **Database Indexing**: Strategic indexes on foreign keys and frequently queried fields

## Important Development Notes

### Persian Data Handling
- National ID validation: exactly 10 digits with checksum validation
- Mobile number format: Iranian format (09xxxxxxxxx)
- Address components follow Iranian administrative divisions
- All user-facing strings should be in Persian

### Role-Based View Structure
- Use the `@role_required(['role1', 'role2'])` decorator for access control
- Dashboard views are organized by role in `main/dashboards/` templates
- Each role has distinct URL patterns and view functions

### Service Request Lifecycle
- Multi-step wizard pattern for complex service requests
- JSON field storage for flexible form data
- Document attachment system with file type validation
- Status change triggers automatic notifications

### Municipality Multi-Tenancy
- Municipality-scoped data filtering in most views
- Geographic hierarchy enforced at database level
- Staff assignment limited to municipality boundaries
- Cross-municipality operations restricted

### Testing Approach
- Use the provided seed data scripts for consistent test environments
- Sample properties and services are pre-configured
- Admin user creation automated for development

### Security Considerations
- CSRF protection enabled with iframe-compatible development settings
- Role-based access control on all sensitive operations
- File upload restrictions and validation
- Session-based authentication with JWT API support