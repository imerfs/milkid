import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_project.settings')
django.setup()

from main.models import Province, County, District, CityVillage
from django.db import transaction

DATA = {
  "province": "خراسان جنوبی",
  "counties": [
    {
      "county": "بیرجند",
      "capital": "بیرجند",
      "districts": [
        {
          "district": "مرکزی",
          "cities": ["بیرجند"],
          "villages": [
            "دستگرد",
            "چهکند",
            "حاجی‌آباد",
            "شوکت‌آباد",
            "حسین‌آباد سادات / رقویی",
            "امیرآباد",
            "بجد",
            "شکراب"
          ]
        }
      ]
    },
    {
      "county": "بشرویه",
      "capital": "بشرویه",
      "districts": [
        {"district": "مرکزی", "cities": ["بشرویه"], "villages": []},
        {"district": "ارسک", "cities": ["ارسک"], "villages": []}
      ]
    },
    {
      "county": "خوسف",
      "capital": "خوسف",
      "districts": [
        {"district": "مرکزی", "cities": ["خوسف", "محمدشهر"], "villages": []},
        {"district": "جلگه ماژان", "cities": ["ماژان"], "villages": []}
      ]
    },
    {
      "county": "درمیان",
      "capital": "اسدیه",
      "districts": [
        {"district": "مرکزی", "cities": ["اسدیه"], "villages": []},
        {"district": "قهستان", "cities": ["قهستان"], "villages": []},
        {"district": "گزیک", "cities": ["گزیک", "طبس مسینا"], "villages": []}
      ]
    },
    {
      "county": "زیرکوه",
      "capital": "حاجی‌آباد",
      "districts": [
        {"district": "مرکزی", "cities": ["حاجی‌آباد"], "villages": []},
        {"district": "زهان", "cities": ["زهان"], "villages": []},
        {"district": "شاسکوه", "cities": ["آبیز"], "villages": []}
      ]
    },
    {
      "county": "سرایان",
      "capital": "سرایان",
      "districts": [
        {"district": "مرکزی", "cities": ["سرایان"], "villages": []},
        {"district": "آیسک", "cities": ["آیسک"], "villages": []},
        {"district": "سه قلعه", "cities": ["سه قلعه"], "villages": []}
      ]
    },
    {
      "county": "سربیشه",
      "capital": "سربیشه",
      "districts": [
        {"district": "مرکزی", "cities": ["سربیشه"], "villages": []},
        {"district": "درح", "cities": ["درح"], "villages": []},
        {"district": "مود", "cities": ["مود"], "villages": []}
      ]
    },
    {
      "county": "طبس",
      "capital": "طبس",
      "districts": [
        {"district": "مرکزی", "cities": ["طبس"], "villages": []},
        {"district": "دیهوک", "cities": ["دیهوک"], "villages": []}
      ]
    },
    {
      "county": "فردوس",
      "capital": "فردوس",
      "districts": [
        {"district": "مرکزی", "cities": ["فردوس", "اسلامیه"], "villages": []},
        {"district": "باغستان", "cities": ["باغستان"], "villages": []}
      ]
    },
    {
      "county": "قائنات",
      "capital": "قائن",
      "districts": [
        {"district": "مرکزی", "cities": ["قائن", "اسفدن"], "villages": []},
        {"district": "سده", "cities": ["آرین‌شهر"], "villages": []},
        {"district": "نیمبلوک", "cities": ["خضری دشت‌بیاض", "نیمبلوک"], "villages": []}
      ]
    },
    {
      "county": "نهبندان",
      "capital": "نهبندان",
      "districts": [
        {"district": "مرکزی", "cities": ["نهبندان"], "villages": []},
        {"district": "شوسف", "cities": ["شوسف"], "villages": []},
        {"district": "سرداران", "cities": [], "villages": []}
      ]
    },
    {
      "county": "عشق‌آباد",
      "capital": "عشق‌آباد",
      "districts": [
        {"district": "مرکزی", "cities": ["عشق‌آباد"], "villages": []},
        {"district": "کوه یخاب", "cities": [], "villages": []}
      ]
    }
  ]
}

@transaction.atomic
def run_import():
    prov_name = DATA["province"]
    province, created = Province.objects.get_or_create(
        name=prov_name,
        defaults={'capital': 'بیرجند'}
    )

    total_counties = 0
    total_districts = 0
    total_cities = 0
    total_villages = 0

    for c_data in DATA["counties"]:
        c_name = c_data["county"]
        county, c_created = County.objects.get_or_create(
            province=province,
            name=c_name
        )
        if c_created:
            total_counties += 1

        for d_data in c_data["districts"]:
            d_name = d_data["district"]
            district, d_created = District.objects.get_or_create(
                county=county,
                name=d_name
            )
            if d_created:
                total_districts += 1

            # Cities
            for city_name in d_data.get("cities", []):
                city, city_created = CityVillage.objects.get_or_create(
                    district=district,
                    name=city_name,
                    defaults={'settlement_type': 'city', 'has_municipality': True}
                )
                if city_created:
                    total_cities += 1

            # Villages
            for village_name in d_data.get("villages", []):
                village, v_created = CityVillage.objects.get_or_create(
                    district=district,
                    name=village_name,
                    defaults={'settlement_type': 'village', 'has_municipality': False}
                )
                if v_created:
                    total_villages += 1

    c_cnt = County.objects.filter(province=province).count()
    d_cnt = District.objects.filter(county__province=province).count()
    cv_cnt = CityVillage.objects.filter(district__county__province=province).count()
    print("SUCCESS: Import complete!")
    print(f"Total Counties in South Khorasan: {c_cnt}")
    print(f"Total Districts in South Khorasan: {d_cnt}")
    print(f"Total Cities and Villages in South Khorasan: {cv_cnt}")

if __name__ == '__main__':
    run_import()
