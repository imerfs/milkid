"""Small plane geometry for plots: UTM (AutoCAD) to latitude/longitude, a local metre grid, areas, edges.

Pure Python on purpose (the server has no shapely / pyproj). A village is a few kilometres wide, so a flat local grid
around its centre is exact to well under a centimetre per 20 m edge.
"""
import math

_A = 6378137.0
_F = 1 / 298.257223563
_K0 = 0.9996


def utm_to_latlng(x, y, zone=40, north=True):
    """UTM easting / northing (metres) to (lat, lng) in degrees (Krüger series, the formulas AutoCAD maps use)."""
    n = _F / (2 - _F)
    a_hat = _A / (1 + n) * (1 + n ** 2 / 4 + n ** 4 / 64)
    beta = (n / 2 - 2 * n ** 2 / 3 + 37 * n ** 3 / 96, n ** 2 / 48 + n ** 3 / 15, 17 * n ** 3 / 480)
    delta = (2 * n - 2 * n ** 2 / 3 - 2 * n ** 3, 7 * n ** 2 / 3 - 8 * n ** 3 / 5, 56 * n ** 3 / 15)
    xi = (y if north else y - 10_000_000) / (_K0 * a_hat)
    eta = (x - 500_000) / (_K0 * a_hat)
    xi_p = xi - sum(beta[j] * math.sin(2 * (j + 1) * xi) * math.cosh(2 * (j + 1) * eta) for j in range(3))
    eta_p = eta - sum(beta[j] * math.cos(2 * (j + 1) * xi) * math.sinh(2 * (j + 1) * eta) for j in range(3))
    chi = math.asin(math.sin(xi_p) / math.cosh(eta_p))
    lat = chi + sum(delta[j] * math.sin(2 * (j + 1) * chi) for j in range(3))
    lng = math.radians((zone - 1) * 6 - 180 + 3) + math.atan2(math.sinh(eta_p), math.cos(xi_p))
    return math.degrees(lat), math.degrees(lng)


def latlng_to_utm(lat, lng, zone=40):
    """Latitude / longitude in degrees to UTM easting / northing in metres (north hemisphere); the inverse of utm_to_latlng."""
    n = _F / (2 - _F)
    a_hat = _A / (1 + n) * (1 + n ** 2 / 4 + n ** 4 / 64)
    alpha = (n / 2 - 2 * n ** 2 / 3 + 5 * n ** 3 / 16, 13 * n ** 2 / 48 - 3 * n ** 3 / 5, 61 * n ** 3 / 240)
    e = math.sqrt(_F * (2 - _F))
    phi = math.radians(lat)
    dlam = math.radians(lng) - math.radians((zone - 1) * 6 - 180 + 3)
    t = math.sinh(math.atanh(math.sin(phi)) - e * math.atanh(e * math.sin(phi)))
    xi_p = math.atan2(t, math.cos(dlam))
    eta_p = math.atanh(math.sin(dlam) / math.sqrt(1 + t * t))
    xi = xi_p + sum(alpha[j] * math.sin(2 * (j + 1) * xi_p) * math.cosh(2 * (j + 1) * eta_p) for j in range(3))
    eta = eta_p + sum(alpha[j] * math.cos(2 * (j + 1) * xi_p) * math.sinh(2 * (j + 1) * eta_p) for j in range(3))
    return 500_000 + _K0 * a_hat * eta, _K0 * a_hat * xi


class Grid:
    """Metres east / north of a centre point."""

    def __init__(self, lat0, lng0):
        self.lat0, self.lng0 = lat0, lng0
        self.kx = 111_320.0 * math.cos(math.radians(lat0))
        self.ky = 110_574.0

    def to_xy(self, lat, lng):
        return (lng - self.lng0) * self.kx, (lat - self.lat0) * self.ky

    def ring(self, lnglat_ring):
        return [self.to_xy(lat, lng) for lng, lat in lnglat_ring]


def signed_area(ring):
    return sum(ring[i][0] * ring[(i + 1) % len(ring)][1] - ring[(i + 1) % len(ring)][0] * ring[i][1] for i in range(len(ring))) / 2


def area(ring):
    return abs(signed_area(ring))


def centroid(ring):
    a = signed_area(ring)
    if abs(a) < 1e-9:
        return sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)
    cx = cy = 0.0
    for i, (x0, y0) in enumerate(ring):
        x1, y1 = ring[(i + 1) % len(ring)]
        cross = x0 * y1 - x1 * y0
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    return cx / (6 * a), cy / (6 * a)


def bbox(ring):
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


def contains(ring, x, y):
    inside = False
    j = len(ring) - 1
    for i, (xi, yi) in enumerate(ring):
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def edges(ring):
    """Edges with their length and the compass side they face: 'north' / 'east' / 'south' / 'west'."""
    ccw = signed_area(ring) > 0
    rows = []
    for i, (x0, y0) in enumerate(ring):
        x1, y1 = ring[(i + 1) % len(ring)]
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue
        nx, ny = (dy, -dx) if ccw else (-dy, dx)            # outward normal
        angle = math.degrees(math.atan2(nx, ny))          # 0 = north, clockwise
        side = 'north' if abs(angle) <= 45 else 'south' if abs(angle) >= 135 else 'east' if angle > 0 else 'west'
        rows.append({'a': (x0, y0), 'b': (x1, y1), 'length': length, 'side': side, 'normal': (nx / length, ny / length)})
    return rows
