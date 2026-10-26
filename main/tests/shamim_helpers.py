"""A shamim DXF built from a plot of the village map, for tests and local demos (UTM zone 40, like the real AutoCAD files)."""
import io

import ezdxf

from main.office import geo


def shamim_dxf(parcel, name_text=None, scale=1.0):
    """DXF bytes: the plot's outline as a closed polyline in UTM metres plus its lot number as text."""
    ring = [geo.latlng_to_utm(lat, lng) for lng, lat in parcel.geometry['coordinates'][0]]
    doc = ezdxf.new('R2010')
    msp = doc.modelspace()
    pts = [(x * scale, y * scale) for x, y in ring]
    msp.add_lwpolyline(pts[:-1] if pts[0] == pts[-1] else pts, close=True)
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    msp.add_text(name_text or (parcel.lot_no or parcel.number or '1'), dxfattribs={'insert': (cx, cy), 'height': 1.0})
    msp.add_lwpolyline([(pts[0][0] - 500, pts[0][1] - 500), (pts[0][0] - 300, pts[0][1] - 500), (pts[0][0] - 300, pts[0][1] - 300)], close=True)   # something else on the sheet
    buffer = io.StringIO()
    doc.write(buffer)
    return buffer.getvalue().encode('utf-8')
