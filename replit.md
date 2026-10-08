# Overview

This is a comprehensive Persian (Farsi) web application called "MelkID" that provides digital municipal and rural property services. The platform serves as a smart municipal service system for rural areas, offering services like building permits, property deed issuance, residence confirmation, and property management. The application supports role-based access for citizens, property owners, village officials (dehyari), technical experts, council members, and system administrators.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Backend Architecture
- **Framework**: Django 5.0.1 with Django REST Framework for API endpoints
- **Authentication**: Extended Django User model with custom UserProfile for Persian-specific fields (national ID, mobile number)
- **Role-Based Access Control**: Six user roles - citizen, owner, dehyari (village official), engineer, council, admin
- **Database Models**: 
  - UserProfile with Persian validation for national ID and mobile numbers
  - Service and ServiceStep models for multi-step service workflows
  - ServiceRequest and RequestDocument for tracking user requests
  - Property model for real estate management
  - Notification system for user communications

## Frontend Architecture
- **Template Engine**: Django templates with Bootstrap 5 RTL support
- **Styling**: Custom CSS with Bootstrap RTL, Tailwind CSS for modern pages
- **Multi-Language Support**: Persian (Farsi) RTL layout with proper text direction
- **Responsive Design**: Mobile-first approach using Bootstrap grid system
- **Progressive Enhancement**: Modern HTML5 with fallback support

## Data Storage
- **Primary Database**: PostgreSQL (Neon) with Django ORM and SSL connection
- **File Storage**: Local filesystem for document uploads
- **Session Management**: Django session framework
- **User Authentication**: Django's built-in authentication with JWT support

## Service Architecture
- **Multi-Step Wizards**: Service requests implemented as step-by-step processes
- **Document Management**: File upload system for required documents per service
- **Status Tracking**: Request lifecycle management (pending, approved, rejected, needs revision)
- **Role-Based Dashboards**: Different interfaces for users vs staff/admin

## Security & Validation
- **Input Validation**: Persian-specific validators for national ID (10 digits) and mobile numbers
- **CSRF Protection**: Django CSRF middleware enabled
- **Permission System**: Role-based view access control
- **Data Sanitization**: Django's built-in XSS protection

# External Dependencies

## Core Framework Dependencies
- **Django 5.0.1**: Main web framework
- **Django REST Framework**: API development
- **django-rest-framework-simplejwt**: JWT authentication
- **django-cors-headers**: CORS handling for API requests

## Frontend Dependencies
- **Bootstrap 5 RTL**: UI framework with right-to-left support
- **Font Awesome 6.4.0**: Icon library
- **Tailwind CSS**: Utility-first CSS framework (via CDN)
- **Vazirmatn Font**: Persian typography from Google Fonts

## Development Tools
- **Python 3.x**: Runtime environment
- **PostgreSQL (Neon)**: Production-ready database with SSL encryption
- **Django Admin**: Built-in admin interface for content management

## Third-Party Services (Potential)
- **SMS Gateway**: For OTP verification and notifications
- **Payment Gateway**: For service fees and property taxes
- **File Storage**: Can be configured for cloud storage (AWS S3, etc.)
- **Email Services**: For notifications and communications

## API Integrations
- **Geographic Data**: Province and county selection APIs
- **Property Validation**: National property registry integration capability
- **Government Services**: Integration endpoints for official document verification