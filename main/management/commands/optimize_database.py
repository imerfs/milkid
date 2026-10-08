"""
Django management command to optimize database performance
Usage: python manage.py optimize_database
"""

from django.core.management.base import BaseCommand
from django.db import connection
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Optimize database performance with indexes and cleanup'

    def add_arguments(self, parser):
        parser.add_argument(
            '--analyze',
            action='store_true',
            help='Analyze database performance',
        )
        parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Clean up old data',
        )
        parser.add_argument(
            '--vacuum',
            action='store_true',
            help='Vacuum database (PostgreSQL only)',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🚀 شروع بهینه‌سازی پایگاه داده...')
        )

        if options['analyze']:
            self.analyze_performance()

        if options['cleanup']:
            self.cleanup_old_data()

        if options['vacuum']:
            self.vacuum_database()

        self.create_missing_indexes()
        self.update_statistics()

        self.stdout.write(
            self.style.SUCCESS('✅ بهینه‌سازی پایگاه داده تکمیل شد!')
        )

    def analyze_performance(self):
        """Analyze database performance and show slow queries"""
        self.stdout.write('📊 تجزیه و تحلیل عملکرد...')
        
        with connection.cursor() as cursor:
            if 'postgresql' in settings.DATABASES['default']['ENGINE']:
                # PostgreSQL specific queries
                cursor.execute("""
                    SELECT query, calls, total_time, mean_time
                    FROM pg_stat_statements
                    WHERE calls > 100
                    ORDER BY total_time DESC
                    LIMIT 10;
                """)
                
                results = cursor.fetchall()
                if results:
                    self.stdout.write('🐌 کوئری‌های کند:')
                    for query, calls, total_time, mean_time in results:
                        self.stdout.write(f'  - {query[:100]}... ({calls} calls, {mean_time:.2f}ms avg)')
                else:
                    self.stdout.write('✅ هیچ کوئری کندی یافت نشد')

    def cleanup_old_data(self):
        """Clean up old unnecessary data"""
        self.stdout.write('🧹 پاکسازی داده‌های قدیمی...')
        
        from main.models import Notification, RequestDocument
        from django.utils import timezone
        from datetime import timedelta

        # Delete old notifications (older than 6 months)
        old_date = timezone.now() - timedelta(days=180)
        old_notifications = Notification.objects.filter(
            created_at__lt=old_date,
            is_read=True
        )
        count = old_notifications.count()
        old_notifications.delete()
        self.stdout.write(f'🗑️  {count} اعلان قدیمی حذف شد')

        # Clean up orphaned files
        # This would require more complex logic to check file system
        self.stdout.write('📁 بررسی فایل‌های یتیم...')

    def vacuum_database(self):
        """Vacuum database for PostgreSQL"""
        if 'postgresql' not in settings.DATABASES['default']['ENGINE']:
            self.stdout.write(
                self.style.WARNING('⚠️  Vacuum فقط برای PostgreSQL در دسترس است')
            )
            return

        self.stdout.write('🔧 اجرای VACUUM...')
        
        with connection.cursor() as cursor:
            cursor.execute('VACUUM ANALYZE;')
        
        self.stdout.write('✅ VACUUM تکمیل شد')

    def create_missing_indexes(self):
        """Create additional performance indexes"""
        self.stdout.write('📈 ایجاد ایندکس‌های عملکردی...')
        
        indexes = [
            # Composite indexes for common queries
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_servicerequest_user_status_created ON main_servicerequest(user_id, status, created_at DESC);",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_property_owner_city ON main_property(owner_national_id, location_area);",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_userprofile_role_city ON main_userprofile(role, city_village);",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_payment_user_status_due ON main_payment(user_id, status, due_date);",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notification_user_read_created ON main_notification(user_id, is_read, created_at DESC);",
            
            # Text search indexes
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_property_address_gin ON main_property USING gin(to_tsvector('english', address));",
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_servicerequest_title_gin ON main_servicerequest USING gin(to_tsvector('english', title));",
        ]

        with connection.cursor() as cursor:
            for index_sql in indexes:
                try:
                    if 'postgresql' in settings.DATABASES['default']['ENGINE']:
                        cursor.execute(index_sql)
                        self.stdout.write(f'✅ ایندکس ایجاد شد')
                    else:
                        # SQLite version (remove CONCURRENTLY and GIN)
                        sqlite_sql = index_sql.replace('CONCURRENTLY ', '').replace(' USING gin(to_tsvector(\'english\', address))', '(address)').replace(' USING gin(to_tsvector(\'english\', title))', '(title)')
                        cursor.execute(sqlite_sql)
                        self.stdout.write(f'✅ ایندکس ایجاد شد (SQLite)')
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f'⚠️  خطا در ایجاد ایندکس: {str(e)}')
                    )

    def update_statistics(self):
        """Update database statistics"""
        self.stdout.write('📊 به‌روزرسانی آمار پایگاه داده...')
        
        with connection.cursor() as cursor:
            if 'postgresql' in settings.DATABASES['default']['ENGINE']:
                cursor.execute('ANALYZE;')
            else:
                cursor.execute('ANALYZE;')
        
        self.stdout.write('✅ آمار به‌روزرسانی شد')

    def get_database_size(self):
        """Get database size information"""
        with connection.cursor() as cursor:
            if 'postgresql' in settings.DATABASES['default']['ENGINE']:
                cursor.execute("""
                    SELECT pg_size_pretty(pg_database_size(current_database())) as size;
                """)
                result = cursor.fetchone()
                return result[0] if result else 'نامشخص'
            else:
                # For SQLite, we'd need to check file size
                return 'نامشخص'