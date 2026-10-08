# Generated migration for performance optimization

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0017_inspection_inspectiondocument_technicalreport'),
    ]

    operations = [
        # UserProfile indexes
        migrations.AddIndex(
            model_name='userprofile',
            index=models.Index(fields=['role', 'is_verified'], name='main_userpr_role_ve_idx'),
        ),
        migrations.AddIndex(
            model_name='userprofile',
            index=models.Index(fields=['national_id'], name='main_userpr_nationa_idx'),
        ),
        migrations.AddIndex(
            model_name='userprofile',
            index=models.Index(fields=['city_village', 'role'], name='main_userpr_city_ro_idx'),
        ),
        
        # ServiceRequest indexes
        migrations.AddIndex(
            model_name='servicerequest',
            index=models.Index(fields=['user', 'status'], name='main_servic_user_st_idx'),
        ),
        migrations.AddIndex(
            model_name='servicerequest',
            index=models.Index(fields=['status', 'created_at'], name='main_servic_status__idx'),
        ),
        migrations.AddIndex(
            model_name='servicerequest',
            index=models.Index(fields=['assigned_to', 'status'], name='main_servic_assign__idx'),
        ),
        migrations.AddIndex(
            model_name='servicerequest',
            index=models.Index(fields=['-created_at'], name='main_servic_created_idx'),
        ),
        
        # Property indexes
        migrations.AddIndex(
            model_name='property',
            index=models.Index(fields=['parcel_number'], name='main_proper_parcel__idx'),
        ),
        migrations.AddIndex(
            model_name='property',
            index=models.Index(fields=['owner_national_id'], name='main_proper_owner_n_idx'),
        ),
        migrations.AddIndex(
            model_name='property',
            index=models.Index(fields=['usage_type', 'status'], name='main_proper_usage_t_idx'),
        ),
        
        # PropertyAdvertisement indexes
        migrations.AddIndex(
            model_name='propertyadvertisement',
            index=models.Index(fields=['status', '-created_at'], name='main_proper_status__idx'),
        ),
        migrations.AddIndex(
            model_name='propertyadvertisement',
            index=models.Index(fields=['user', 'status'], name='main_proper_user_st_idx'),
        ),
        migrations.AddIndex(
            model_name='propertyadvertisement',
            index=models.Index(fields=['city_village', 'status'], name='main_proper_city_st_idx'),
        ),
        
        # Payment indexes
        migrations.AddIndex(
            model_name='payment',
            index=models.Index(fields=['user', 'status'], name='main_paymen_user_st_idx'),
        ),
        migrations.AddIndex(
            model_name='payment',
            index=models.Index(fields=['status', 'due_date'], name='main_paymen_status__idx'),
        ),
        
        # Notification indexes
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['user', 'is_read'], name='main_notifi_user_is_idx'),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['-created_at'], name='main_notifi_created_idx'),
        ),
    ]
