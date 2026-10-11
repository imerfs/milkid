"""Copy the front-end libraries and fonts the pages need from node_modules into static/vendor/.

Pages load them from our own server instead of Google Fonts / jsDelivr / cdnjs, which are slow or blocked
in Iran. The copies are committed, so the server never needs npm.

Usage:  npm ci && python scripts/vendor_assets.py
"""
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NM = ROOT / 'node_modules'
OUT = ROOT / 'static' / 'vendor'


def copy(src, dest, strip_map=False):
    dest = OUT / dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    if strip_map:                     # drop the trailing sourceMappingURL comment: the map is not shipped
        text = Path(src).read_text(encoding='utf-8')
        text = re.sub(r'\n?(/\*|//)# sourceMappingURL=[^\n]*?(\*/)?\s*$', '\n', text)
        dest.write_text(text, encoding='utf-8', newline='\n')
    else:
        shutil.copyfile(src, dest)


def main():
    if OUT.exists():
        shutil.rmtree(OUT)

    # Vazirmatn: the variable font covers every weight in one file
    copy(NM / 'vazirmatn/fonts/webfonts/Vazirmatn[wght].woff2', 'vazirmatn/Vazirmatn-variable.woff2')
    shutil.copyfile(NM / 'vazirmatn/OFL.txt', (OUT / 'vazirmatn' / 'OFL.txt'))

    # Font Awesome 6.4.0 free: woff2 only (every browser we support has it), so drop the .ttf fallbacks
    fa = NM / '@fortawesome/fontawesome-free'
    css = (fa / 'css/all.min.css').read_text(encoding='utf-8')
    css = re.sub(r',url\(\.\./webfonts/[^)]*\.ttf\)\s*format\("truetype"\)', '', css)
    css = re.sub(r'/\*# sourceMappingURL=[^*]*\*/', '', css)
    (OUT / 'fontawesome/css').mkdir(parents=True, exist_ok=True)
    (OUT / 'fontawesome/css/all.min.css').write_text(css, encoding='utf-8', newline='\n')
    for name in ('fa-solid-900', 'fa-regular-400', 'fa-brands-400', 'fa-v4compatibility'):
        copy(fa / f'webfonts/{name}.woff2', f'fontawesome/webfonts/{name}.woff2')

    # Bootstrap 5.3.0
    bs = NM / 'bootstrap/dist'
    copy(bs / 'css/bootstrap.rtl.min.css', 'bootstrap/bootstrap.rtl.min.css', strip_map=True)
    copy(bs / 'css/bootstrap.min.css', 'bootstrap/bootstrap.min.css', strip_map=True)
    copy(bs / 'js/bootstrap.bundle.min.js', 'bootstrap/bootstrap.bundle.min.js', strip_map=True)

    # Chart.js and SortableJS
    copy(NM / 'chart.js/dist/chart.umd.min.js', 'chartjs/chart.umd.min.js', strip_map=True)
    copy(NM / 'sortablejs/Sortable.min.js', 'sortablejs/Sortable.min.js')

    # HTMX (dependent dropdowns and partial page updates)
    copy(NM / 'htmx.org/dist/htmx.min.js', 'htmx/htmx.min.js')

    # Material Icons (one dashboard still uses the ligature font)
    mi = NM / 'material-icons/iconfont'
    copy(mi / 'material-icons.woff2', 'material-icons/material-icons.woff2')
    css = (mi / 'material-icons.css').read_text(encoding='utf-8')
    css = re.sub(r',\s*url\("\./material-icons\.woff"\)\s*format\("woff"\)', '', css)
    (OUT / 'material-icons/material-icons.css').write_text(css, encoding='utf-8', newline='\n')

    print('vendored into', OUT)


if __name__ == '__main__':
    main()
