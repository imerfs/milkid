#!/usr/bin/env python
"""
Create sample geographic data for testing
"""
import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_project.settings')
django.setup()

from main.models import Province, County, District

def create_sample_data():
    """Create sample geographic data"""
    
    # Create sample provinces
    provinces_data = [
        {'name': 'تهران', 'code': '01', 'capital': 'تهران'},
        {'name': 'اصفهان', 'code': '02', 'capital': 'اصفهان'},
        {'name': 'فارس', 'code': '03', 'capital': 'شیراز'},
        {'name': 'خراسان رضوی', 'code': '04', 'capital': 'مشهد'},
        {'name': 'خوزستان', 'code': '05', 'capital': 'اهواز'},
        {'name': 'مازندران', 'code': '06', 'capital': 'ساری'},
        {'name': 'گیلان', 'code': '07', 'capital': 'رشت'},
        {'name': 'آذربایجان شرقی', 'code': '08', 'capital': 'تبریز'},
        {'name': 'کرمان', 'code': '09', 'capital': 'کرمان'},
        {'name': 'هرمزگان', 'code': '10', 'capital': 'بندرعباس'},
    ]
    
    print("Creating provinces...")
    for province_data in provinces_data:
        province, created = Province.objects.get_or_create(
            name=province_data['name'],
            defaults={
                'code': province_data['code'],
                'capital': province_data['capital']
            }
        )
        if created:
            print(f"✅ Created province: {province.name}")
        else:
            print(f"⚠️  Province already exists: {province.name}")
    
    # Create sample counties for Tehran province
    tehran_province = Province.objects.get(name='تهران')
    counties_data = [
        {'name': 'تهران', 'code': '01'},
        {'name': 'شمیرانات', 'code': '02'},
        {'name': 'ری', 'code': '03'},
        {'name': 'اسلامشهر', 'code': '04'},
        {'name': 'ورامین', 'code': '05'},
        {'name': 'پاکدشت', 'code': '06'},
        {'name': 'دماوند', 'code': '07'},
        {'name': 'فیروزکوه', 'code': '08'},
        {'name': 'ملارد', 'code': '09'},
        {'name': 'شهریار', 'code': '10'},
    ]
    
    print("\nCreating counties for Tehran province...")
    for county_data in counties_data:
        county, created = County.objects.get_or_create(
            province=tehran_province,
            name=county_data['name'],
            defaults={'code': county_data['code']}
        )
        if created:
            print(f"✅ Created county: {county.name}")
        else:
            print(f"⚠️  County already exists: {county.name}")
    
    # Create sample districts for Tehran county
    tehran_county = County.objects.get(name='تهران', province=tehran_province)
    districts_data = [
        {'name': 'مرکزی', 'code': '01'},
        {'name': 'شمیران', 'code': '02'},
        {'name': 'کن', 'code': '03'},
        {'name': 'لواسان', 'code': '04'},
    ]
    
    print("\nCreating districts for Tehran county...")
    for district_data in districts_data:
        district, created = District.objects.get_or_create(
            county=tehran_county,
            name=district_data['name'],
            defaults={'code': district_data['code']}
        )
        if created:
            print(f"✅ Created district: {district.name}")
        else:
            print(f"⚠️  District already exists: {district.name}")
    
    # Create sample counties and districts for other provinces
    other_provinces_data = {
        'اصفهان': {
            'counties': [
                {'name': 'اصفهان', 'districts': ['مرکزی', 'برخوار', 'نیک‌آباد']},
                {'name': 'کاشان', 'districts': ['مرکزی', 'نیاسر', 'قمصر']},
                {'name': 'نجف‌آباد', 'districts': ['مرکزی', 'مهردشت']},
            ]
        },
        'فارس': {
            'counties': [
                {'name': 'شیراز', 'districts': ['مرکزی', 'ارژن', 'سروستان']},
                {'name': 'مرودشت', 'districts': ['مرکزی', 'کامفیروز']},
                {'name': 'فسا', 'districts': ['مرکزی', 'نوبندگان']},
            ]
        },
        'مازندران': {
            'counties': [
                {'name': 'ساری', 'districts': ['مرکزی', 'رودسر', 'میاندرود']},
                {'name': 'بابل', 'districts': ['مرکزی', 'بندپی شرقی', 'بندپی غربی']},
                {'name': 'آمل', 'districts': ['مرکزی', 'دابودشت', 'گزنک']},
            ]
        }
    }
    
    print("\nCreating counties and districts for other provinces...")
    for province_name, province_info in other_provinces_data.items():
        try:
            province = Province.objects.get(name=province_name)
            print(f"\n📍 Processing {province_name}...")
            
            for county_info in province_info['counties']:
                county, created = County.objects.get_or_create(
                    province=province,
                    name=county_info['name'],
                    defaults={'code': '01'}
                )
                if created:
                    print(f"  ✅ Created county: {county.name}")
                
                for district_name in county_info['districts']:
                    district, created = District.objects.get_or_create(
                        county=county,
                        name=district_name,
                        defaults={'code': '01'}
                    )
                    if created:
                        print(f"    ✅ Created district: {district.name}")
        
        except Province.DoesNotExist:
            print(f"❌ Province {province_name} not found")
    
    print(f"\n{'='*60}")
    print("📊 Summary:")
    print(f"Total Provinces: {Province.objects.count()}")
    print(f"Total Counties: {County.objects.count()}")
    print(f"Total Districts: {District.objects.count()}")
    print(f"{'='*60}")
    print("✅ Sample geographic data created successfully!")

if __name__ == '__main__':
    create_sample_data()