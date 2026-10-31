"""Pull chosen layers (closed polylines with their points, colours) out of a big DXF (streamed, so a 350 MB drawing is fine), plus the layer-table colour of each.

Usage: python scripts/gis/extract_dxf_layers.py <file.dxf> <out.json> layer1 layer2 ...
"""
import json
import sys

from ezdxf.addons import iterdxf


def layer_colours(path, wanted):
    """The TABLES/LAYER record colour (group 62, negative = off) and true colour (420) of the wanted layers."""
    found, name, record = {}, None, None
    with open(path, 'r', encoding='utf-8', errors='replace') as handle:
        lines = iter(handle)
        for code in lines:
            value = next(lines, '').rstrip('\n')
            code = code.strip()
            if code == '0' and value == 'ENDSEC' and found:
                break
            if code == '0' and value == 'LAYER':
                name, record = None, {}
            elif code == '2' and record is not None and name is None:
                name = value
                if name in wanted:
                    found[name] = record
                else:
                    record = None
            elif record is not None and code in ('62', '420', '6'):
                record[code] = value
    return found


def main(path, out, wanted):
    wanted = set(wanted)
    result = {'colours': layer_colours(path, wanted), 'entities': []}
    for entity in iterdxf.single_pass_modelspace(open(path, 'rb')):
        if entity.dxf.layer not in wanted:
            continue
        kind = entity.dxftype()
        item = {'layer': entity.dxf.layer, 'type': kind}
        if kind == 'LWPOLYLINE':
            item['closed'] = bool(entity.is_closed)
            item['points'] = [(round(p[0], 3), round(p[1], 3)) for p in entity.get_points('xy')]
        elif kind == 'LINE':
            item['points'] = [(round(entity.dxf.start.x, 3), round(entity.dxf.start.y, 3)), (round(entity.dxf.end.x, 3), round(entity.dxf.end.y, 3))]
        elif kind == 'HATCH':
            item['colour'] = entity.dxf.color if entity.dxf.hasattr('color') else None
            item['rgb'] = entity.dxf.true_color if entity.dxf.hasattr('true_color') else None
            item['paths'] = []
            for boundary in entity.paths:
                pts = getattr(boundary, 'vertices', None)
                if pts:
                    item['paths'].append([(round(v[0], 3), round(v[1], 3)) for v in pts])
        elif kind in ('TEXT', 'MTEXT'):
            item['text'] = (entity.dxf.text if kind == 'TEXT' else entity.text)[:60]
            item['at'] = (round(entity.dxf.insert.x, 2), round(entity.dxf.insert.y, 2))
        else:
            continue
        result['entities'].append(item)
    json.dump(result, open(out, 'w', encoding='utf-8'), ensure_ascii=False)
    counts = {}
    for item in result['entities']:
        counts[(item['layer'], item['type'])] = counts.get((item['layer'], item['type']), 0) + 1
    print(result['colours'])
    print(counts)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
