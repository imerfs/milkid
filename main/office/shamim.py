"""Reading the shamim file (the plot's AutoCAD survey): its outline, area, and the plot of the village map it lies on.

A shamim is a DXF (or the DWG it came from). From a DXF we take the closed outlines, pick the one that is the plot
(the one whose area is closest to what the owner declared), and, when its coordinates are UTM (as AutoCAD maps of
this region are) or latitude/longitude, find the plot of the village map it covers. That gives the clerk the renewal
code to confirm instead of reading it off the drawing. GeoJSON, KML and a zip holding one of these are read too; a
DWG cannot be read here and the clerk is told to ask for the DXF export.

Everything returned is plain data (stored on the file); problems become ``notes``, never exceptions.
"""
import io
import json
import re
import zipfile

from main.office import geo, plotmap

MAX_ZIP_BYTES = 60 * 1024 * 1024
READABLE = ('.dxf', '.geojson', '.json', '.kml')
MIN_AREA_M2 = 4


def _rings_from_dxf(data):
    import ezdxf
    from ezdxf import recover
    try:
        doc, _ = recover.read(io.BytesIO(data))
    except Exception:       # pylint: disable=broad-except   # a damaged file is a note for the clerk, not an error page
        doc = ezdxf.read(io.StringIO(data.decode('utf-8', 'ignore')))
    rings, texts = [], []
    for entity in doc.modelspace():
        kind = entity.dxftype()
        points = None
        if kind == 'LWPOLYLINE' and (entity.closed or _is_closed(entity.get_points('xy'))):
            points = [(p[0], p[1]) for p in entity.get_points('xy')]
        elif kind == 'POLYLINE' and entity.is_2d_polyline and (entity.is_closed or _is_closed([v.dxf.location for v in entity.vertices])):
            points = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
        elif kind in ('TEXT', 'MTEXT'):
            raw = entity.dxf.text if kind == 'TEXT' else entity.text
            pos = entity.dxf.insert
            texts.append({'text': str(raw).strip(), 'x': pos.x, 'y': pos.y})
        if points and len(points) >= 3:
            if _is_closed(points) and len(points) > 3:
                points = points[:-1]
            rings.append(points)
    return rings, texts


def _is_closed(points):
    points = list(points)
    return len(points) >= 4 and abs(points[0][0] - points[-1][0]) < 1e-6 and abs(points[0][1] - points[-1][1]) < 1e-6


def _rings_from_geojson(data):
    doc = json.loads(data.decode('utf-8'))
    found = []

    def walk(node):
        kind = node.get('type')
        if kind == 'FeatureCollection':
            for f in node.get('features', []):
                walk(f)
        elif kind == 'Feature':
            walk(node.get('geometry') or {})
        elif kind == 'Polygon':
            found.append([(c[0], c[1]) for c in node['coordinates'][0]])
        elif kind == 'MultiPolygon':
            for poly in node['coordinates']:
                found.append([(c[0], c[1]) for c in poly[0]])
    walk(doc)
    return [r[:-1] if r and r[0] == r[-1] else r for r in found], []


def _rings_from_kml(data):
    """Polygon coordinates by pattern, never by an XML parser: a KML from outside is not trusted with entities."""
    text = data.decode('utf-8', 'ignore')
    rings = []
    for block in re.findall(r'<coordinates[^>]*>(.*?)</coordinates>', text, flags=re.S | re.I):
        points = []
        for chunk in block.split():
            parts = chunk.split(',')
            try:
                points.append((float(parts[0]), float(parts[1])))
            except (ValueError, IndexError):
                continue
        if len(points) >= 4:
            rings.append(points[:-1] if points[0] == points[-1] else points)
    return rings, []


def _unzip(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = [i for i in archive.infolist() if not i.is_dir() and i.filename.lower().endswith(READABLE)]
        if not members or sum(i.file_size for i in archive.infolist()) > MAX_ZIP_BYTES:
            return None, ''
        member = members[0]
        return archive.read(member), member.filename.lower()[member.filename.rfind('.'):]


def _georef(ring):
    x, y = ring[0]
    if 20 < y < 45 and 40 < x < 70:
        return 'lnglat'
    if 100_000 < x < 900_000 and 2_000_000 < y < 5_000_000:
        return 'utm'
    return 'local'


def _to_grid(ring, mode, grid):
    if mode == 'lnglat':
        return [grid.to_xy(y, x) for x, y in ring]
    if mode == 'utm':
        return [grid.to_xy(*geo.utm_to_latlng(x, y)) for x, y in ring]
    return list(ring)


def analyse(upload_name, data, declared_area=None, village_map=None):
    """Plain-data result of reading the shamim: ``ok``, area, vertices, edge lengths, matched plots, notes."""
    ext = '.' + upload_name.rsplit('.', 1)[-1].lower() if '.' in upload_name else ''
    result = {'ok': False, 'format': ext.lstrip('.'), 'notes': [], 'matches': []}
    try:
        if ext == '.zip':
            inner, ext = _unzip(data)
            if inner is None:
                result['notes'].append('در فایل zip فایل قابل خواندن (dxf / geojson / kml) پیدا نشد.')
                return result
            data = inner
            result['format'] = ext.lstrip('.') + ' (داخل zip)'
        if ext == '.dwg':
            result['notes'].append('فایل dwg را سامانه نمی‌خواند؛ از اتوکد با دستور SAVEAS خروجی DXF بگیرید و آن را بفرستید، یا کد نوسازی را دستی بدهید.')
            return result
        if ext == '.dxf':
            rings, texts = _rings_from_dxf(data)
        elif ext in ('.geojson', '.json'):
            rings, texts = _rings_from_geojson(data)
        elif ext == '.kml':
            rings, texts = _rings_from_kml(data)
        else:
            result['notes'].append('این نوع فایل خوانده نمی‌شود.')
            return result
    except Exception:       # pylint: disable=broad-except
        result['notes'].append('فایل خوانده نشد (آسیب‌دیده یا ناقص است)؛ کارشناس باید آن را در اتوکد ببیند.')
        return result

    mode_of = {}
    candidates = []
    for ring in rings:
        mode = _georef(ring)
        mode_of[id(ring)] = mode
        local = _to_grid(ring, mode, geo.Grid(*(utm_to_ll(ring[0]) if mode == 'utm' else (ring[0][1], ring[0][0]) if mode == 'lnglat' else (0, 0))))
        if geo.area(local) >= MIN_AREA_M2:
            candidates.append((ring, mode, local))
    if not candidates:
        result['notes'].append('خط بسته‌ی ملک (پلی‌لاین بسته) در فایل پیدا نشد.')
        return result

    def distance(item):
        a = geo.area(item[2])
        return abs(a - float(declared_area)) / float(declared_area) if declared_area else -a
    ring, mode, local = min(candidates, key=distance)
    area = geo.area(local)
    cx, cy = geo.centroid(local)
    result.update(ok=True, polygons=len(candidates), area=round(area, 2), vertices=len(ring),
                  edges=[round(e['length'], 2) for e in geo.edges(local)], georef=mode,
                  outline=[[round(x - cx, 2), round(y - cy, 2)] for x, y in local])
    if declared_area:
        diff = (area - float(declared_area)) / float(declared_area) * 100
        result['area_diff_pct'] = round(diff, 1)
        if abs(diff) > 5:
            result['notes'].append(f'مساحت شمیم ({area:.1f} م²) با مساحت اعلام‌شده ({float(declared_area):.1f} م²) {abs(diff):.0f}٪ فرق دارد.')
    inside = [t['text'] for t in texts if re.fullmatch(r'\d{1,6}', t['text']) and _text_in(ring, t, mode)]
    result['numbers_inside'] = inside[:6]
    if mode == 'local':
        result['notes'].append('مختصات فایل با نقشه‌ی روستا جور نیست (نه UTM است نه جغرافیایی)؛ ملک روی نقشه پیدا نشد.')
    elif village_map is not None:
        result['matches'] = _match(ring, mode, village_map, inside)
        if not result['matches']:
            result['notes'].append('ملک شمیم روی هیچ قطعه‌ی ترسیم‌شده‌ی نقشه‌ی روستا نیفتاد.')
    return result


def utm_to_ll(point):
    return geo.utm_to_latlng(point[0], point[1])


def _text_in(ring, text, mode):
    return geo.contains(ring, text['x'], text['y'])


def _match(ring, mode, village_map, numbers):
    """Plots of the map under the shamim outline's centre (and its corners), best first."""
    points = []
    cx, cy = geo.centroid(ring)
    for x, y in [(cx, cy)] + list(ring):
        points.append(geo.utm_to_latlng(x, y) if mode == 'utm' else (y, x))
    hits = {}
    for weight, (lat, lng) in zip([4] + [1] * len(ring), points):
        row = plotmap.parcel_at(village_map, lat, lng)
        if row:
            hits.setdefault(row['id'], [row, 0])[1] += weight
    ordered = sorted(hits.values(), key=lambda item: -item[1])
    return [{'parcel_id': r['id'], 'code': r['code'], 'block': r['block'], 'number': r['number'], 'lot': r['lot'],
             'score': score, 'lot_in_drawing': bool(r['lot'] and r['lot'] in numbers)} for r, score in ordered[:4]]
