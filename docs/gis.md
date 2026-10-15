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
| **عرصه** (land): the plots | survey drawing; 3 115 drawn + 846 estimated |
| **اعیان** (buildings): footprints | detail drawing `l.building`; 3 790 |
| **بلوک‌ها** + **شماره‌ی بلوک‌ها** (small, from zoom 16) | street rings of the survey; 272 |
| **محله‌ها** (حوزه‌بندی, the same thing) | the municipality's neighbourhood picture; 5 |
| **حریم‌ها**: one tick box per type + a master box | detail drawing (see below) |
| Base maps: none (offline), OpenStreetMap, satellite, traffic | tile providers (see below) |

Colour the plots by **filing status**, **land use**, **neighbourhood** or **easement compliance**; filter by
filed / not filed / locked / violating / approximate. A thick red outline always means *locked*.
Plot numbers appear from zoom 19. The bottom-left readout shows the cursor in UTM and lat/lng.

### Search box

* `0-0-12-69-3` the full renewal code; `12-69-3` plot-block-neighbourhood; `69-12` block-plot; `69` a block.
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

## Land use (کاربری)

Each plot takes the colour of the most specific solid fill under it in the detail drawing (24 colours). **Yellow is the
residential fill (مسکونی)**; the other colours are shown as «کاربری N (نام ثبت نشده)» until the drawing's legend is
read: its text is in an old Persian CAD font that does not decode. Name a colour in the Django admin
(*انواع کاربری*) and the name appears everywhere; names survive a reload.

## Easements (حریم)

Six types from the detail drawing's layers: حریم, حریم کیفی, حریم قنات, حریم کیفی قنات, حریم پدافند غیرعامل ۱ و ۲.
Hatches and closed outlines are areas; two long open lines running side by side (the two edges of a corridor) are
joined into the area between them; the rest stay lines. A plot **violates** an easement if ≥ 1 m² of it lies inside an
area, or an easement line crosses it. The panel lists each type and the overlap; 11 plots currently do (qanat).

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
   python scripts/gis/build_village_map.py survey.dxf pass1.geojson --detail-dxf detail.dxf
   python scripts/gis/georef_zones.py zones.jpg pass1.geojson main/data/gis/dastgerd_zones.json
   python scripts/gis/build_village_map.py survey.dxf main/data/gis/dastgerd.geojson --detail-dxf detail.dxf --zones main/data/gis/dastgerd_zones.json
   ```
4. `python manage.py load_village_map dastgerd`: updates plots in place and keeps archives, payments, locks, and the
   names given to colours and neighbourhoods. A plot that has any of them is never deleted.

## Adding another village

Add an entry to `VILLAGES` in `main/gis/loader.py`, build its GeoJSON, and run `load_village_map`; the sidebar link
appears for that village's experts.
