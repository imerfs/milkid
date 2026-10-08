from django.test import TestCase, Client
from django.contrib.auth.models import User
from main.models import UserProfile, ServiceRequest, RequestDocument, Service
import main.views as views

class BackendRefactorTest(TestCase):
    def setUp(self):
        self.client = Client()
        # Create standard citizen
        self.user = User.objects.create_user(username='citizen_user', password='password123')
        self.profile, _ = UserProfile.objects.get_or_create(user=self.user)
        self.profile.role = 'citizen'
        self.profile.approval_status = 'approved'
        self.profile.is_verified = True
        self.profile.save()
        
        # Create dehyari user
        self.staff_user = User.objects.create_user(username='dehyari_user', password='password123')
        self.staff_profile, _ = UserProfile.objects.get_or_create(user=self.staff_user)
        self.staff_profile.role = 'dehyari'
        self.staff_profile.approval_status = 'approved'
        self.staff_profile.is_verified = True
        self.staff_profile.save()

        # Create unauthorized user
        self.other_user = User.objects.create_user(username='other_user', password='password123')
        self.other_profile, _ = UserProfile.objects.get_or_create(user=self.other_user)
        self.other_profile.role = 'citizen'
        self.other_profile.approval_status = 'approved'
        self.other_profile.is_verified = True
        self.other_profile.save()

    def test_view_package_exports(self):
        """Verify that main.views exports key view functions after refactor"""
        self.assertTrue(hasattr(views, 'home'))
        self.assertTrue(hasattr(views, 'dashboard'))
        self.assertTrue(hasattr(views, 'dehyari_dashboard'))
        self.assertTrue(hasattr(views, 'council_dashboard'))
        self.assertTrue(hasattr(views, 'admin_dashboard'))
        self.assertTrue(hasattr(views, 'CustomLoginView'))
        self.assertTrue(hasattr(views, 'staff_registration_info'))

    def test_document_download_security(self):
        """Verify document download access control for owner, staff, and unauthorized users"""
        service = Service.objects.create(name='Test Service', slug='test-service', is_active=True)
        req = ServiceRequest.objects.create(
            user=self.user,
            service=service,
            title='Test Request',
            description='Test Description'
        )
        doc = RequestDocument.objects.create(
            request=req,
            document_name='test.pdf'
        )

        # Unauthorized user should be forbidden
        self.client.login(username='other_user', password='password123')
        res_other = self.client.get(f'/dashboard/download-document/{doc.id}/')
        self.assertEqual(res_other.status_code, 403)

        # Owner user should not get 403
        self.client.login(username='citizen_user', password='password123')
        res_owner = self.client.get(f'/dashboard/download-document/{doc.id}/')
        self.assertNotEqual(res_owner.status_code, 403)

        # Staff user should not get 403
        self.client.login(username='dehyari_user', password='password123')
        res_staff = self.client.get(f'/dashboard/download-document/{doc.id}/')
        self.assertNotEqual(res_staff.status_code, 403)
