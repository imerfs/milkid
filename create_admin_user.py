#!/usr/bin/env python
"""
Create admin user for testing
"""
import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_project.settings')
django.setup()

from django.contrib.auth.models import User
from main.models import UserProfile

def create_admin():
    """Create admin user"""
    
    username = 'admin'
    password = 'admin123'
    email = 'admin@melkid.com'
    
    # Check if admin already exists
    if User.objects.filter(username=username).exists():
        print(f"⚠️  Admin user '{username}' already exists")
        admin_user = User.objects.get(username=username)
    else:
        # Create admin user
        admin_user = User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            first_name='مدیر',
            last_name='سیستم'
        )
        print(f"✅ Created admin user: {username}")
    
    # Create/update profile
    profile, created = UserProfile.objects.get_or_create(user=admin_user)
    profile.role = 'admin'
    profile.approval_status = 'approved'
    profile.is_verified = True
    profile.national_id = '0000000000'
    profile.mobile_number = '09000000000'
    profile.save()
    
    if created:
        print("✅ Created admin profile")
    else:
        print("✅ Updated admin profile")
    
    print(f"\n{'='*50}")
    print("🎉 Admin user ready!")
    print(f"Username: {username}")
    print(f"Password: {password}")
    print(f"Email: {email}")
    print(f"{'='*50}")

if __name__ == '__main__':
    create_admin()