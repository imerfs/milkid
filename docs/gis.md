# Village web-GIS (نقشه‌ی GIS روستا)

A map of one village with its blocks, plots, buildings, neighbourhoods, easements and land use, a timeline, and an
archive per plot (permit, owner, fee payments, locks). Open it from the technical expert's panel (**نقشه‌ی GIS روستای ...**
in the sidebar) or at `/gis/<slug>/`, e.g. `/gis/dastgerd/`.

## Who sees it

Only the **technical expert of that village** (role `engineer`, profile village = the map's village) and admins.
Every other role, other villages' experts and anonymous visitors get 403/redirect on the page and on every JSON endpoint
(`main/gis/access.py`, `gis.view` / `gis.edit` / `gis.lock` in `main/access.py`). Nothing about the map is in `/static/`.

## What is on the map

| Layer (tick box) | Source |
|---|---|
| **عرصه** (land): the plots | survey drawing (3 115 drawn + 846 estimated) and the housing plan (933) |
| **اعیان** (buildings): footprints, clickable | detail drawing `l.building`; 3 790 |
| **بلوک‌ها** + **شماره‌ی بلوک‌ها** (small, from zoom 16) | street rings of the survey (272) and the housing plan (32) |
| **محله‌ها** (حوزه‌بندی, the same thing) | the municipality's neighbourhood picture (5) + the housing area (6) |
| **حریم‌ها**: one tick box per type + a master box | detail drawing (see below) |
| Base maps: none (offline), OpenStreetMap, satellite, traffic | tile providers (see below) |

Colour the plots by **land use** (the default), **neighbourhood**, **easement compliance** or **filing status**;
filter (a list inside the layers panel) by filed / not filed / permit / locked / violating / approximate. The colour
legend is in the same panel. A thick red outline always means *locked*. Plot numbers appear from zoom 19. The
bottom-left readout shows the cursor in UTM and lat/lng.

### عرصه and اعیان

A property has two halves, and the map and the panel keep them apart: the **land** (عرصه, the plot, ticked
separately, with its own owner and area) and the **building** (اعیان, the footprints standing on it, ticked
separately, clickable, with its own owner, floors, floor area and the building permit). Clicking a building opens its
plot on the «اعیان و پروانه» tab. Land and building can have different owners, so the archive keeps both.

### Search box

* `0-0-12-69-3` the full renewal code; `12-69-3` plot-block-neighbourhood; `69-12` block-plot; `69` a block;
  `t432` the housing plan's subdivision lot 432.
* `714299 3644453` **UTM X Y** (zone 40N, any order, Persian digits fine) and `32.9173, 59.2916` lat/lng.
  The map flies there and opens the plot under the point.
* Opening a plot by search shows a banner when it breaks an easement or is locked.

## Renewal code (کد نوسازی)

`صنف - آپارتمان - ملک - بلوک - محله`, e.g. `0-0-12-69-3`: guild, apartment, plot, block, neighbourhood
(`renewal_code()` in `main/gis/uids.py`). The drawing has the last three; a plot (the land itself) has no guild or
apartment unit, so those are 0 for now. Shown beside it: عرصه area, اعیان area (footprints standing on it), land use,
neighbourhood.

* 64 codes repeat on more than one plot in the drawing and 335 drawn plots carry no number; both are flagged.
* A plot's identity in the database is `uid` (`block-plot`, `#2` for repeats), stable across rebuilds.

## Neighbourhoods (محله / حوزه‌بندی)

Read off the municipality's coloured picture: `scripts/gis/georef_zones.py` registers the picture on the plots
(cross-correlation of its coloured pixels with the drawn plots, scale checked against the 400 m scale bar) and gives every
block the colour under most of its plots. 99.5 % of a block's plots agree. Blocks in the newest area, which the picture
does not colour, copy the nearest coloured block (≤150 m). The picture is kept in `main/data/gis/source/`.

## The plans' legacy Persian text

The plans' legends and notes use SHX fonts (`naskhd.shx`) that AutoCAD does not ship, so they show as `???`. They
are decoded by `scripts/gis/shx_text.py` (the ASCII letters follow the Persian keyboard, the high bytes are joined
forms, digits are stored reversed; the table was built from the legend itself and unknown bytes print as `<xx>`).
A TrueType font collection does not help here: this is not Unicode text.

## Land use (کاربری)

Each plot takes the colour of the most specific solid fill under it in the drawing (25 colours). The master plan's
legend numbers its land uses (1 مسکونی, 2 تجاری, 5 دبستان, 6-7 متوسطه, 10 فرهنگی, 12 مذهبی, 14 اداری, 16 تأسیسات,
19-20 درمانی, 27 جهانگردی و پذیرایی, 28 ورزشی-تفریحی, 31-32 فضای سبز) and the hatch layers carry that number (`27hp`
is use 27), so a colour is named after its layer: 14 colours are named. The others (the orange of layer `50 p`, 176
plots, and 10 smaller ones) are not in the legend and show as «کاربری N (نام ثبت نشده)». Name a colour in the Django
admin (*انواع کاربری*) and the name appears everywhere; names survive a reload.

## Easements (حریم)

Six types from the detail drawing's layers, named as in the plan's legend: حریم, حریم کیفی مسیل, حریم کمی قنات,
حریم کیفی قنات, حریم ۵۰ متر پدافند, حریم ۱۵۰ متر پدافند. The plan's notes are shown with a violation and as a tooltip
(`main/gis/rules.py`): the quantity easement of a qanat is 6 m and mandatory; no polluting units, land-use change,
absorption wells, effluent, waste or farmland drainage in a qanat's quality easement; no building or change of
terrain in a stream's quality easement; the 50 m / 150 m defence zones allow at most 2 / 3 floors on pilotis. Not
written in the plan: which layer is which defence zone (told apart by size, 3 ha against 12 ha) and what the plain
`Harim` layer is.
Hatches and closed outlines are areas; two long open lines running side by side (the two edges of a corridor) are
joined into the area between them; the rest stay lines. A plot **violates** an easement if ≥ 1 m² of it lies inside an
area, or an easement line crosses it. The panel lists each type and the overlap; 11 plots currently do (qanat).

## The housing area (neighbourhood 6)

The new housing plan (`نهضت ملی`) is neighbourhood 6: 933 plots in 32 blocks. Its drawing has no plot outlines, so
plots are the faces the subdivision and street-edge lines enclose (`scripts/gis/housing_area.py`). Block numbers
restart at 1 there, so uids carry the neighbourhood (`6:17-5`) and a block is told apart by (neighbourhood, number).
From the drawing: the plot's number inside its block (the renewal code's plot, 574 plots), the subdivision lot number
1-1008 (`t432`, 927 plots), land use, and a **permit mark on 184 plots** («طبق نقشه پروانه صادر شده»; the permit's
number and date are not in the drawing). 359 plots carry no in-block number, so they have no renewal code yet; they
can still be opened by clicking or by lot number.

## Timeline

The slider (1400 → this year) shows the map as of a year. What changes with it comes from dates that exist:
a plot's first/last survey year (the 1404 and 1405 drawings differ by 25 plots and 4 buildings), permit year, payment
dates and lock periods. **Only two surveys exist, so before permits/payments/locks are entered most years look the same.**
Archive data without a permit date counts as filed from this year on.

## Locks (قفل ملک)

The expert can lock a plot for **debt**, **neighbour's complaint** or **street occupation**; one active lock per
reason, history kept (who, when, why, who released and why). A locked plot is drawn with a thick red outline and:

* a new request whose `parcel_number` (شماره پلاک) is its renewal code is refused (user dashboard form, request form,
  construction-permit form) with the reason;
* a request naming it cannot be approved or set to approved/completed, and the inspector's approval is refused
  (`main/lifecycle.py`); rejecting is always allowed.

The user dashboard's new-request form has an optional «کد نوسازی ملک» field for this. Other entry points (the service
wizard's steps) do not ask for the plot yet.

## Base maps and traffic

Settings in `django_project/settings.py`, overridable by environment: `GIS_OSM_TILE_URL`, `GIS_SATELLITE_TILE_URL`
(default Esri imagery), `GIS_TRAFFIC_TILE_URL` (empty = the traffic tick box is disabled). **Esri and Google refuse
requests from Iran**, and live traffic always needs a provider key, so for villages inside Iran set these to an Iranian
provider's tile URLs. The map works without any of them.

## Data model

`VillageMap` → `MapBlock`, `MapZone`, `LandUseClass`, `MapEasement`, `MapBuilding`, `MapParcel` (GeoJSON geometry, WGS84)
→ `ParcelArchive` (one per plot), `ParcelFeePayment`, `ParcelLock`. Migration `0056` loads Dastgerd from
`main/data/gis/dastgerd.geojson`, so a deploy only needs `migrate`. `main/data/gis/dastgerd_zones.json` records the
neighbourhoods.

## Rebuilding from new drawings

1. DWG → DXF with LibreDWG (free: `dwg2dxf.exe -y -o out.dxf drawing.dwg`) or AutoCAD (`SAVEAS` → DXF 2018), for the
   survey and the detail drawing. Both are in UTM zone 40N.
2. `pip install -r scripts/gis/requirements.txt` (adds numpy/Pillow/pyproj/shapely/ezdxf; never needed on the server).
3. First pass without zones, then register the neighbourhood picture, then the real build:
   ```
   python scripts/gis/build_village_map.py survey.dxf pass1.geojson --detail-dxf detail.dxf --housing-dxf housing.dxf
   python scripts/gis/georef_zones.py zones.jpg pass1.geojson main/data/gis/dastgerd_zones.json
   python scripts/gis/build_village_map.py survey.dxf main/data/gis/dastgerd.geojson --detail-dxf detail.dxf \
       --housing-dxf housing.dxf --zones main/data/gis/dastgerd_zones.json
   ```
4. `python manage.py load_village_map dastgerd`: updates plots in place and keeps archives, payments, locks, and the
   names given to colours and neighbourhoods. A plot that has any of them is never deleted.

## Adding another village

Add an entry to `VILLAGES` in `main/gis/loader.py`, build its GeoJSON, and run `load_village_map`; the sidebar link
appears for that village's experts.
