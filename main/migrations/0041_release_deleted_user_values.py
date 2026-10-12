from django.db import migrations


def release(apps, schema_editor):
    """Free the username and national ID of accounts deleted before they were released on delete."""
    UserProfile = apps.get_model('main', 'UserProfile')
    for profile in UserProfile.objects.filter(deleted_at__isnull=False, deleted_username='').select_related('user'):
        profile.deleted_username = profile.user.username
        profile.deleted_national_id = profile.national_id or ''
        profile.national_id = None
        profile.save(update_fields=['deleted_username', 'deleted_national_id', 'national_id'])
        profile.user.username = f'deleted-{profile.user_id}'
        profile.user.save(update_fields=['username'])


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0040_userprofile_must_change_password'),
    ]

    operations = [migrations.RunPython(release, migrations.RunPython.noop)]
