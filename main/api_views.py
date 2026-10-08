
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.conf import settings
from django.db.models import Q
import json

@api_view(['GET'])
@permission_classes([AllowAny])
def get_provinces(request):
    """Get all provinces for dropdown from database"""
    from .models import Province
    
    try:
        provinces = Province.objects.all().order_by('name')
        provinces_data = [
            {"id": str(province.id), "name": province.name}
            for province in provinces
        ]
        
        return Response({
            "success": True,
            "data": provinces_data
        })
    except Exception as e:
        return Response({
            "success": False,
            "error": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([AllowAny])
def get_counties(request, province_id):
    """Get counties for a specific province from database"""
    from .models import County
    
    try:
        counties = County.objects.filter(province_id=province_id).order_by('name')
        counties_data = [
            {"id": str(county.id), "name": county.name}
            for county in counties
        ]
        
        return Response({
            "success": True,
            "data": counties_data
        })
    except Exception as e:
        return Response({
            "success": False,
            "error": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_districts(request, county_id):
    """Get districts (بخش) for a specific county"""
    from .models import District
    
    try:
        districts = District.objects.filter(county_id=county_id).order_by('name')
        districts_data = [
            {"id": str(district.id), "name": district.name}
            for district in districts
        ]
        
        return Response({
            "success": True,
            "data": districts_data
        })
    except Exception as e:
        return Response({
            "success": False,
            "error": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_dehestans(request, district_id):
    """Get dehestans (دهستان) for a specific district"""
    from .models import Dehestan
    
    try:
        dehestans = Dehestan.objects.filter(district_id=district_id).order_by('name')
        dehestans_data = [
            {"id": str(dehestan.id), "name": dehestan.name}
            for dehestan in dehestans
        ]
        
        return Response({
            "success": True,
            "data": dehestans_data
        })
    except Exception as e:
        return Response({
            "success": False,
            "error": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_cities_villages(request):
    """Get cities/villages for a specific district or dehestan"""
    from .models import CityVillage
    
    try:
        district_id = request.GET.get('district_id')
        dehestan_id = request.GET.get('dehestan_id')
        settlement_type = request.GET.get('type')  # 'city' or 'village'
        
        # Build query
        query = CityVillage.objects.all()
        
        if district_id:
            query = query.filter(district_id=district_id)
        
        if dehestan_id:
            query = query.filter(dehestan_id=dehestan_id)
        
        if settlement_type:
            query = query.filter(settlement_type=settlement_type)
        
        query = query.order_by('name')
        
        cities_villages_data = [
            {
                "id": str(cv.id),
                "name": cv.name,
                "type": cv.settlement_type,
                "type_display": cv.get_settlement_type_display()
            }
            for cv in query
        ]
        
        return Response({
            "success": True,
            "data": cities_villages_data
        })
    except Exception as e:
        return Response({
            "success": False,
            "error": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_old_counties(request, province_id):
    """DEPRECATED: Get counties for a specific province (old hardcoded version)"""
    counties_data = {
        "tehran": [
            {"id": "tehran-c", "name": "تهران"},
            {"id": "rey-c", "name": "ری"},
            {"id": "shemiranat-c", "name": "شمیرانات"},
            {"id": "eslamshahr-c", "name": "اسلامشهر"},
            {"id": "robat-karim-c", "name": "رباط کریم"},
            {"id": "damavand-c", "name": "دماوند"},
            {"id": "firuzkuh-c", "name": "فیروزکوه"},
            {"id": "pakdasht-c", "name": "پاکدشت"}
        ],
        "alborz": [
            {"id": "karaj-c", "name": "کرج"},
            {"id": "nazarabad-c", "name": "نظرآباد"},
            {"id": "savojbolagh-c", "name": "ساوجبلاغ"},
            {"id": "taleghan-c", "name": "طالقان"},
            {"id": "fardis-c", "name": "فردیس"}
        ],
        "markazi": [
            {"id": "arak-c", "name": "اراک"},
            {"id": "khomein-c", "name": "خمین"},
            {"id": "mahalat-c", "name": "محلات"},
            {"id": "delijan-c", "name": "دلیجان"},
            {"id": "tafresh-c", "name": "تفرش"},
            {"id": "zarandieh-c", "name": "زرندیه"},
            {"id": "saveh-c", "name": "ساوه"}
        ],
        "qom": [
            {"id": "qom-c", "name": "قم"}
        ],
        "qazvin": [
            {"id": "qazvin-c", "name": "قزوین"},
            {"id": "takestan-c", "name": "تاکستان"},
            {"id": "abyek-c", "name": "آبیک"},
            {"id": "buin-zahra-c", "name": "بوئین زهرا"}
        ],
        "gilan": [
            {"id": "rasht-c", "name": "رشت"},
            {"id": "bandar-anzali-c", "name": "بندر انزلی"},
            {"id": "lahijan-c", "name": "لاهیجان"},
            {"id": "langarud-c", "name": "لنگرود"},
            {"id": "rudsar-c", "name": "رودسر"},
            {"id": "astara-c", "name": "آستارا"},
            {"id": "talesh-c", "name": "تالش"},
            {"id": "masuleh-c", "name": "ماسوله"},
            {"id": "fouman-c", "name": "فومن"},
            {"id": "sowme'eh-sara-c", "name": "صومعه سرا"}
        ],
        "mazandaran": [
            {"id": "sari-c", "name": "ساری"},
            {"id": "babol-c", "name": "بابل"},
            {"id": "amol-c", "name": "آمل"},
            {"id": "qaemshahr-c", "name": "قائمشهر"},
            {"id": "gorgan-c", "name": "گرگان"},
            {"id": "noshahr-c", "name": "نوشهر"},
            {"id": "tonekabon-c", "name": "تنکابن"},
            {"id": "chalous-c", "name": "چالوس"},
            {"id": "ramsar-c", "name": "رامسر"},
            {"id": "behshahr-c", "name": "بهشهر"}
        ],
        "golestan": [
            {"id": "gorgan-c", "name": "گرگان"},
            {"id": "gonbad-c", "name": "گنبد کاووس"},
            {"id": "aliabad-c", "name": "علی آباد"},
            {"id": "azadshahr-c", "name": "آزادشهر"},
            {"id": "kalaleh-c", "name": "کلاله"},
            {"id": "bandar-torkmen-c", "name": "بندر ترکمن"}
        ],
        "khorasan-razavi": [
            {"id": "mashhad-c", "name": "مشهد"},
            {"id": "neyshabur-c", "name": "نیشابور"},
            {"id": "torbat-heydariyeh-c", "name": "تربت حیدریه"},
            {"id": "kashmar-c", "name": "کاشمر"},
            {"id": "sabzevar-c", "name": "سبزوار"},
            {"id": "chenaran-c", "name": "چناران"},
            {"id": "gonabad-c", "name": "گناباد"},
            {"id": "fariman-c", "name": "فریمان"},
            {"id": "khaf-c", "name": "خاف"},
            {"id": "torbat-jam-c", "name": "تربت جام"}
        ],
        "خراسان-جنوبی": [
            {"id": "بیرجند-ش", "name": "بیرجند"},
            {"id": "qaen-c", "name": "قائن"},
            {"id": "ferdows-c", "name": "فردوس"},
            {"id": "nehbandan-c", "name": "نهبندان"},
            {"id": "sarayan-c", "name": "سرایان"},
            {"id": "boshruyeh-c", "name": "بشرویه"},
            {"id": "tabas-c", "name": "طبس"}
        ],
        "khorasan-shomali": [
            {"id": "bojnurd-c", "name": "بجنورد"},
            {"id": "shirvan-c", "name": "شیروان"},
            {"id": "esfarayen-c", "name": "اسفراین"},
            {"id": "faruj-c", "name": "فاروج"},
            {"id": "maneh-samalqan-c", "name": "مانه و سملقان"}
        ],
        "sistan-baluchestan": [
            {"id": "zahedan-c", "name": "زاهدان"},
            {"id": "zabol-c", "name": "زابل"},
            {"id": "iranshahr-c", "name": "ایرانشهر"},
            {"id": "chabahar-c", "name": "چابهار"},
            {"id": "khash-c", "name": "خاش"},
            {"id": "saravan-c", "name": "سراوان"},
            {"id": "mirjaveh-c", "name": "میرجاوه"},
            {"id": "nikshahr-c", "name": "نیکشهر"}
        ],
        "kerman": [
            {"id": "kerman-c", "name": "کرمان"},
            {"id": "rafsanjan-c", "name": "رفسنجان"},
            {"id": "sirjan-c", "name": "سیرجان"},
            {"id": "bam-c", "name": "بم"},
            {"id": "jiroft-c", "name": "جیرفت"},
            {"id": "zarand-c", "name": "زرند"},
            {"id": "bardsir-c", "name": "بردسیر"},
            {"id": "shahr-babak-c", "name": "شهربابک"}
        ],
        "hormozgan": [
            {"id": "bandar-abbas-c", "name": "بندرعباس"},
            {"id": "minab-c", "name": "میناب"},
            {"id": "qeshm-c", "name": "قشم"},
            {"id": "kish-c", "name": "کیش"},
            {"id": "parsian-c", "name": "پارسیان"},
            {"id": "bandar-lengeh-c", "name": "بندرلنگه"},
            {"id": "rudan-c", "name": "رودان"}
        ],
        "fars": [
            {"id": "shiraz-c", "name": "شیراز"},
            {"id": "marvdasht-c", "name": "مرودشت"},
            {"id": "kazerun-c", "name": "کازرون"},
            {"id": "firuzabad-c", "name": "فیروزآباد"},
            {"id": "jahrom-c", "name": "جهرم"},
            {"id": "darab-c", "name": "داراب"},
            {"id": "larestan-c", "name": "لارستان"},
            {"id": "lar-c", "name": "لار"},
            {"id": "fasa-c", "name": "فسا"},
            {"id": "neyriz-c", "name": "نیریز"}
        ],
        "bushehr": [
            {"id": "bushehr-c", "name": "بوشهر"},
            {"id": "dashtestan-c", "name": "دشتستان"},
            {"id": "tangestan-c", "name": "تنگستان"},
            {"id": "dashti-c", "name": "دشتی"},
            {"id": "ganaveh-c", "name": "گناوه"},
            {"id": "dayyer-c", "name": "دیر"}
        ],
        "khuzestan": [
            {"id": "ahvaz-c", "name": "اهواز"},
            {"id": "abadan-c", "name": "آبادان"},
            {"id": "khorramshahr-c", "name": "خرمشهر"},
            {"id": "dezful-c", "name": "دزفول"},
            {"id": "masjed-soleyman-c", "name": "مسجدسلیمان"},
            {"id": "shushtar-c", "name": "شوشتر"},
            {"id": "andimeshk-c", "name": "اندیمشک"},
            {"id": "behbahan-c", "name": "بهبهان"},
            {"id": "susangerd-c", "name": "سوسنگرد"},
            {"id": "shadegan-c", "name": "شادگان"}
        ],
        "chaharmahal-bakhtiari": [
            {"id": "shahrekord-c", "name": "شهرکرد"},
            {"id": "borujen-c", "name": "بروجن"},
            {"id": "farsan-c", "name": "فارسان"},
            {"id": "lordegan-c", "name": "لردگان"},
            {"id": "kiar-c", "name": "کیار"},
            {"id": "ardal-c", "name": "اردل"}
        ],
        "kohgiluyeh-boyerahmad": [
            {"id": "yasuj-c", "name": "یاسوج"},
            {"id": "gachsaran-c", "name": "گچساران"},
            {"id": "dehdasht-c", "name": "دهدشت"},
            {"id": "dogonbadan-c", "name": "دوگنبدان"},
            {"id": "margoon-c", "name": "مارگون"}
        ],
        "isfahan": [
            {"id": "isfahan-c", "name": "اصفهان"},
            {"id": "kashan-c", "name": "کاشان"},
            {"id": "najafabad-c", "name": "نجف آباد"},
            {"id": "khomeini-shahr-c", "name": "خمینی شهر"},
            {"id": "shahin-shahr-c", "name": "شاهین شهر"},
            {"id": "natanz-c", "name": "نطنز"},
            {"id": "ardestan-c", "name": "اردستان"},
            {"id": "mobarakeh-c", "name": "مبارکه"},
            {"id": "khour-biabanak-c", "name": "خور و بیابانک"},
            {"id": "golpayegan-c", "name": "گلپایگان"}
        ],
        "yazd": [
            {"id": "yazd-c", "name": "یزد"},
            {"id": "meybod-c", "name": "میبد"},
            {"id": "ardakan-c", "name": "اردکان"},
            {"id": "abarkuh-c", "name": "ابرکوه"},
            {"id": "taft-c", "name": "تفت"},
            {"id": "bafq-c", "name": "بافق"},
            {"id": "mehriz-c", "name": "مهریز"}
        ],
        "semnan": [
            {"id": "semnan-c", "name": "سمنان"},
            {"id": "shahroud-c", "name": "شاهرود"},
            {"id": "damghan-c", "name": "دامغان"},
            {"id": "garmsar-c", "name": "گرمسار"},
            {"id": "aradan-c", "name": "آرادان"},
            {"id": "miami-c", "name": "میامی"}
        ],
        "zanjan": [
            {"id": "zanjan-c", "name": "زنجان"},
            {"id": "khodabandeh-c", "name": "خدابنده"},
            {"id": "abhar-c", "name": "ابهر"},
            {"id": "khorramdarreh-c", "name": "خرمدره"},
            {"id": "tarom-c", "name": "طارم"},
            {"id": "mahneshan-c", "name": "ماهنشان"}
        ],
        "east-azerbaijan": [
            {"id": "tabriz-c", "name": "تبریز"},
            {"id": "marand-c", "name": "مرند"},
            {"id": "maragheh-c", "name": "مراغه"},
            {"id": "miyaneh-c", "name": "میانه"},
            {"id": "shabestar-c", "name": "شبستر"},
            {"id": "sarab-c", "name": "سراب"},
            {"id": "ahar-c", "name": "اهر"},
            {"id": "jolfa-c", "name": "جلفا"},
            {"id": "bonab-c", "name": "بناب"},
            {"id": "varzeqan-c", "name": "ورزقان"}
        ],
        "west-azerbaijan": [
            {"id": "urmia-c", "name": "ارومیه"},
            {"id": "khoy-c", "name": "خوی"},
            {"id": "mahabad-c", "name": "مهاباد"},
            {"id": "piranshahr-c", "name": "پیرانشهر"},
            {"id": "sardasht-c", "name": "سردشت"},
            {"id": "maku-c", "name": "ماکو"},
            {"id": "salmas-c", "name": "سلماس"},
            {"id": "naghadeh-c", "name": "نقده"},
            {"id": "takab-c", "name": "تکاب"}
        ],
        "ardabil": [
            {"id": "ardabil-c", "name": "اردبیل"},
            {"id": "meshgin-shahr-c", "name": "مشگین شهر"},
            {"id": "parsabad-c", "name": "پارس آباد"},
            {"id": "khalkhal-c", "name": "خلخال"},
            {"id": "germi-c", "name": "گرمی"},
            {"id": "bileh-savar-c", "name": "بیله سوار"}
        ],
        "kurdistan": [
            {"id": "sanandaj-c", "name": "سنندج"},
            {"id": "saghez-c", "name": "سقز"},
            {"id": "marivan-c", "name": "مریوان"},
            {"id": "baneh-c", "name": "بانه"},
            {"id": "qorveh-c", "name": "قروه"},
            {"id": "bijar-c", "name": "بیجار"},
            {"id": "kamyaran-c", "name": "کامیاران"},
            {"id": "divandarreh-c", "name": "دیواندره"}
        ],
        "hamadan": [
            {"id": "hamadan-c", "name": "همدان"},
            {"id": "malayer-c", "name": "ملایر"},
            {"id": "nahavand-c", "name": "نهاوند"},
            {"id": "toyserkan-c", "name": "تویسرکان"},
            {"id": "asadabad-c", "name": "اسدآباد"},
            {"id": "bahar-c", "name": "بهار"},
            {"id": "razan-c", "name": "رزن"},
            {"id": "kaboudarahang-c", "name": "کبودرآهنگ"}
        ],
        "kermonshah": [
            {"id": "kermanshah-c", "name": "کرمانشاه"},
            {"id": "islamabad-gharb-c", "name": "اسلام آباد غرب"},
            {"id": "harsin-c", "name": "هرسین"},
            {"id": "kangavar-c", "name": "کنگاور"},
            {"id": "sonqor-c", "name": "سنقر"},
            {"id": "sarpol-zahab-c", "name": "سرپل ذهاب"},
            {"id": "paveh-c", "name": "پاوه"},
            {"id": "javanroud-c", "name": "جوانرود"}
        ],
        "ilam": [
            {"id": "ilam-c", "name": "ایلام"},
            {"id": "dehloran-c", "name": "دهلران"},
            {"id": "mehran-c", "name": "مهران"},
            {"id": "dareh-shahr-c", "name": "دره شهر"},
            {"id": "abdanan-c", "name": "آبدانان"},
            {"id": "eyvan-c", "name": "ایوان"},
            {"id": "malekshahi-c", "name": "ملکشاهی"}
        ],
        "lorestan": [
            {"id": "khorramabad-c", "name": "خرم آباد"},
            {"id": "borujerd-c", "name": "بروجرد"},
            {"id": "dorud-c", "name": "دورود"},
            {"id": "aligudarz-c", "name": "الیگودرز"},
            {"id": "azna-c", "name": "ازنا"},
            {"id": "kuhdasht-c", "name": "کوهدشت"},
            {"id": "pol-dokhtar-c", "name": "پل دختر"},
            {"id": "selseleh-c", "name": "سلسله"}
        ]
    }

    counties = counties_data.get(province_id, [])
    return Response({
        "success": True,
        "data": counties
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def get_villages(request, county_id):
    """Get villages for a specific county including approved municipalities"""
    from .models import Municipality
    villages_data = {
        # تهران
        "tehran-c": [
            {"id": "tehran-city", "name": "تهران"},
            {"id": "tajrish", "name": "تجریش"},
            {"id": "darband", "name": "دربند"},
            {"id": "lavasan", "name": "لواسان"},
            {"id": "fasham", "name": "فشم"},
            {"id": "rudehen", "name": "رودهن"},
            {"id": "evin", "name": "اوین"}
        ],
        "rey-c": [
            {"id": "rey-city", "name": "ری"},
            {"id": "kahrizak", "name": "کهریزک"},
            {"id": "varamin", "name": "ورامین"},
            {"id": "qarchak", "name": "قرچک"}
        ],
        "shemiranat-c": [
            {"id": "shemiran", "name": "شمیران"},
            {"id": "niavaran", "name": "نیاوران"},
            {"id": "velenjak", "name": "ولنجک"}
        ],
        "karaj-c": [
            {"id": "karaj-city", "name": "کرج"},
            {"id": "hashtgerd", "name": "هشتگرد"},
            {"id": "mahdasht", "name": "مهدشت"},
            {"id": "asara", "name": "اسارا"}
        ],
        
        # خراسان جنوبی
        "بیرجند-ش": [
            {"id": "بیرجند-شهر", "name": "بیرجند"},
            {"id": "دستگرد", "name": "دستگرد"},
            {"id": "hajiabad", "name": "حاجی آباد"},
            {"id": "chahkand", "name": "چهکند"},
            {"id": "amirabad", "name": "امیر اباد"},
            {"id": "mud", "name": "مود"}
        ],
        "qaen-c": [
            {"id": "qaen-city", "name": "قائن"},
            {"id": "sedeh", "name": "سده"},
            {"id": "nimbolook", "name": "نیمبلوک"}
        ],
        "ferdows-c": [
            {"id": "ferdows-city", "name": "فردوس"},
            {"id": "asadiyeh", "name": "اسدیه"},
            {"id": "deyhook", "name": "دیهوک"}
        ],
        
        # فارس
        "shiraz-c": [
            {"id": "shiraz-city", "name": "شیراز"},
            {"id": "zarghan", "name": "زرقان"},
            {"id": "sivand", "name": "سیوند"},
            {"id": "zarqan", "name": "زرقان"}
        ],
        "marvdasht-c": [
            {"id": "marvdasht-city", "name": "مرودشت"},
            {"id": "persepolis", "name": "تخت جمشید"},
            {"id": "doroodzan", "name": "درودزن"}
        ],
        "kazerun-c": [
            {"id": "kazerun-city", "name": "کازرون"},
            {"id": "konartakhteh", "name": "کنارتخته"},
            {"id": "jereh", "name": "جره"}
        ],
        
        # اصفهان
        "isfahan-c": [
            {"id": "isfahan-city", "name": "اصفهان"},
            {"id": "najafabad", "name": "نجف آباد"},
            {"id": "khomeini-shahr", "name": "خمینی شهر"},
            {"id": "fooladshahr", "name": "فولادشهر"}
        ],
        "kashan-c": [
            {"id": "kashan-city", "name": "کاشان"},
            {"id": "aran-bidgol", "name": "آران و بیدگل"},
            {"id": "niasar", "name": "نیاسر"},
            {"id": "qamsar", "name": "قمصر"}
        ],
        
        # خوزستان
        "ahvaz-c": [
            {"id": "ahvaz-city", "name": "اهواز"},
            {"id": "karoun", "name": "کارون"},
            {"id": "golestan", "name": "گلستان"},
            {"id": "kout-abdollah", "name": "کوت عبدالله"}
        ],
        "abadan-c": [
            {"id": "abadan-city", "name": "آبادان"},
            {"id": "khorramabad", "name": "خرمآباد"},
            {"id": "arvand", "name": "اروند"}
        ],
        
        # مازندران
        "sari-c": [
            {"id": "sari-city", "name": "ساری"},
            {"id": "farah-abad", "name": "فرح آباد"},
            {"id": "kiakola", "name": "کیاکلا"}
        ],
        "babol-c": [
            {"id": "babol-city", "name": "بابل"},
            {"id": "babolsar", "name": "بابلسر"},
            {"id": "ghaemshahr", "name": "قائمشهر"}
        ],
        
        # گیلان
        "rasht-c": [
            {"id": "rasht-city", "name": "رشت"},
            {"id": "fuman", "name": "فومن"},
            {"id": "rasht-khomam", "name": "خمام"}
        ],
        "lahijan-c": [
            {"id": "lahijan-city", "name": "لاهیجان"},
            {"id": "langarud", "name": "لنگرود"},
            {"id": "chaboksar", "name": "چابکسر"}
        ],
        
        # کرمان
        "kerman-c": [
            {"id": "kerman-city", "name": "کرمان"},
            {"id": "mahan", "name": "ماهان"},
            {"id": "rafsanjan", "name": "رفسنجان"}
        ],
        "bam-c": [
            {"id": "bam-city", "name": "بم"},
            {"id": "baravat", "name": "براوات"},
            {"id": "narmashir", "name": "نرماشیر"}
        ],
        
        # آذربایجان شرقی
        "tabriz-c": [
            {"id": "tabriz-city", "name": "تبریز"},
            {"id": "sis", "name": "سیس"},
            {"id": "khosrowshahr", "name": "خسروشهر"}
        ],
        "marand-c": [
            {"id": "marand-city", "name": "مرند"},
            {"id": "yamchi", "name": "یامچی"},
            {"id": "khomarloo", "name": "خمارلو"}
        ],
        
        # یزد
        "yazd-c": [
            {"id": "yazd-city", "name": "یزد"},
            {"id": "taft", "name": "تفت"},
            {"id": "mehriz", "name": "مهریز"}
        ],
        "meybod-c": [
            {"id": "meybod-city", "name": "میبد"},
            {"id": "chak-chak", "name": "چک چک"},
            {"id": "narin", "name": "نارین"}
        ],
        
        # هرمزگان
        "bandar-abbas-c": [
            {"id": "bandar-abbas-city", "name": "بندرعباس"},
            {"id": "tiab", "name": "تیاب"},
            {"id": "takht", "name": "تخت"}
        ],
        "qeshm-c": [
            {"id": "qeshm-city", "name": "قشم"},
            {"id": "dargahan", "name": "درگهان"},
            {"id": "suza", "name": "سوزا"}
        ],
        
        # قزوین
        "qazvin-c": [
            {"id": "qazvin-city", "name": "قزوین"},
            {"id": "alamut", "name": "الموت"},
            {"id": "mohammadieh", "name": "محمدیه"}
        ],
        
        # سمنان
        "semnan-c": [
            {"id": "semnan-city", "name": "سمنان"},
            {"id": "damghan", "name": "دامغان"},
            {"id": "shahroud", "name": "شاهرود"}
        ],
        
        # Default for counties without specific data
        "default": [
            {"id": "center", "name": "مرکز شهرستان"},
            {"id": "rural-1", "name": "روستای یک"},
            {"id": "rural-2", "name": "روستای دو"}
        ]
    }

    # Get villages for the specific county, or default list if not found
    villages = villages_data.get(county_id, villages_data["default"])
    
    # Add approved municipalities to the list
    try:
        # Map county_id to possible county name variations
        county_mapping = {
            'shiraz-c': ['شیراز', 'shiraz'],
            'tehran-c': ['تهران', 'tehran'],
            'karaj-c': ['کرج', 'karaj'],
            'بیرجند-ش': ['بیرجند', 'birjand'],
            'marvdasht-c': ['مرودشت', 'marvdasht'],
            'kazerun-c': ['کازرون', 'kazerun']
        }
        
        possible_names = county_mapping.get(county_id, [county_id.replace('-c', '')])
        
        # Find approved municipalities in this county
        query = Municipality.objects.filter(status='active')
        for name in possible_names:
            query = query.filter(
                Q(county__icontains=name) | Q(county__iexact=name)
            )
            break  # Use first match
            
        approved_municipalities = query
        
        for municipality in approved_municipalities:
            municipality_item = {
                "id": f"municipality-{municipality.id}",
                "name": f"{municipality.get_municipality_type_display()} {municipality.name}"
            }
            # Avoid duplicates
            if municipality_item not in villages:
                villages.append(municipality_item)
                
    except Exception as e:
        # If there's any error, just continue with the original list
        pass
    
    return Response({
        "success": True,
        "data": villages
    })

@api_view(['POST'])
@permission_classes([AllowAny])
def search_properties(request):
    """Search properties with filters"""
    data = request.data

    # Mock property search results
    mock_properties = [
        {
            "id": 1,
            "title": "ملک مسکونی ۲۰۰ متری",
            "address": f"{data.get('villageName', 'نامشخص')} - خیابان اصلی",
            "area": 200,
            "usage": "residential",
            "hasDebt": False,
            "price": "450,000,000 تومان",
            "owner": "احمد محمدی",
            "image": "https://placehold.co/300x200/14b8a6/FFFFFF?text=Property+1"
        },
        {
            "id": 2,
            "title": "زمین کشاورزی ۱۵۰۰ متری",
            "address": f"{data.get('villageName', 'نامشخص')} - حومه شرقی",
            "area": 1500,
            "usage": "agricultural",
            "hasDebt": True,
            "price": "280,000,000 تومان",
            "owner": "مریم احمدی",
            "image": "https://placehold.co/300x200/0ea5e9/FFFFFF?text=Property+2"
        }
    ]

    # Apply filters
    filtered_properties = mock_properties

    if data.get('usageType'):
        filtered_properties = [p for p in filtered_properties if p['usage'] == data['usageType']]

    if data.get('minArea'):
        filtered_properties = [p for p in filtered_properties if p['area'] >= int(data['minArea'])]

    if data.get('maxArea'):
        filtered_properties = [p for p in filtered_properties if p['area'] <= int(data['maxArea'])]

    if data.get('hasDebt') is not None:
        has_debt = data['hasDebt'] == 'true'
        filtered_properties = [p for p in filtered_properties if p['hasDebt'] == has_debt]

    return Response({
        "success": True,
        "data": {
            "properties": filtered_properties,
            "total": len(filtered_properties),
            "search_params": data
        }
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def get_property_detail(request, property_id):
    """Get detailed property information"""
    # Mock property detail
    property_detail = {
        "id": property_id,
        "title": "ملک مسکونی ۲۰۰ متری",
        "address": "فشم - خیابان اصلی - پلاک ۱۵",
        "area": 200,
        "usage": "residential",
        "hasDebt": False,
        "price": "450,000,000 تومان",
        "owner": {
            "name": "احمد محمدی",
            "phone": "09121234567"
        },
        "coordinates": {"lat": 35.8247, "lng": 51.1656},
        "documents": [
            {"type": "deed", "name": "سند مالکیت", "verified": True},
            {"type": "plan", "name": "نقشه UTM", "verified": False}
        ],
        "services_available": [
            "صدور پروانه ساختمان",
            "تایید سکونت",
            "تغییر کاربری"
        ],
        "images": [
            "https://placehold.co/600x400/14b8a6/FFFFFF?text=Main+View",
            "https://placehold.co/600x400/0ea5e9/FFFFFF?text=Side+View"
        ]
    }

    return Response({
        "success": True,
        "data": property_detail
    })
