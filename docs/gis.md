# Village web-GIS (نقشه‌ی GIS روستا)

A map of one village with its blocks, plots, buildings, neighbourhoods, easements and land use, a timeline, and an
archive per plot (permit, owner, fee payments, locks). Open it from the technical expert's panel (**نقشه‌ی GIS روستای ...**
in the sidebar) or at `/gis/<slug>/`, e.g. `/gis/dastgerd/`.

## Who sees it

The **three staff of that village**: the technical expert (`engineer`), the administrative expert (`clerk`) and the dehyari (`dehyari`), whose village is the
map's village (the profile's village, or for a dehyari without one the municipality they administer), and admins. The map link is in each of the three
panels. They all open the map and edit plots; locking a plot stays with the technical expert and the dehyari. Every other role, other villages' staff and
anonymous visitors get 403/redirect on the page and on every JSON endpoint (`main/gis/access.py`, `gis.view` / `gis.edit` / `gis.lock` in `main/access.py`).
Nothing about the map is in `/static/`. Dastgerd is the first map; every later village works the same way with no code change.

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

## The plan as AutoCAD shows it (نقشه‌ی طرح)

The default base layer of the map (first radio box under «نقشه‌ی پایه») is the detail drawing itself: every filled and
pattern-hatched area (land-use zones, roads, parks, building hatches), line, curb, channel and text of the plan, with the
drawing's own colours, line weights, line types and hatch patterns. The plots, blocks and neighbourhoods are drawn over it
as a light, clickable skin (the building footprints stay off until ticked, because the plan already draws buildings).
Choose «بدون پس‌زمینه» or a street/satellite map for the plain view.

* Built by `scripts/gis/build_cad_layer.py` into `main/data/gis/dastgerd_cad.json` (4.6 MB, about 1.2 MB gzipped): 7 735
  hatches, 13 024 lines, ~1 000 readable texts. Layers that are off or frozen in the drawing, and the title block and legend
  outside the village, are left out.
* Served by `/gis/<slug>/cad/` with the map's access rules; drawn on one canvas tile layer (`static/js/village-cad.js`) over
  a spatial index, so it stays fast. Hatch spacing follows the drawing's scale; below 3 px it fades to a tint.
* The plan's legacy Persian text (SHX fonts) is decoded with `scripts/gis/shx_text.py`; a text that still has an unknown
  byte is dropped, never shown garbled. The `0xA0` byte of that font is the letter ن, so only plain blanks are collapsed.

```
python scripts/gis/build_cad_layer.py detail.dxf main/data/gis/dastgerd_cad.json --plots main/data/gis/dastgerd.geojson
```

### The plan's legend in the sidebar, the sheet frame, X / Y search

* The sheet's left column (logo and name of the sponsoring organization, consultants, plan title, scale, legend) is not drawn:
  everything left of UTM x 713 165 is cut. The legend is read from that column instead (`legend_rows()` in
  `build_cad_layer.py`: each label row is matched to the swatches at the same y) and shown in the layers panel as
  **«راهنمای نقشه‌ی طرح»**: one tick box per row with its existing / proposed swatch; unticking a row hides the hatches of the
  layers (and, where two rows share a layer, of the colour) that row stands for. Rows drawn with line symbols only
  (e.g. حریم کیفی مسیل) are listed but disabled; use the easement boxes for them.
* The drawing is no longer cut 600 m around the blocks: the whole plan (river, roads, the housing area) is in, only the stray
  items far outside are dropped.
* **Search by X / Y**: the crosshair button in the search box opens two fields, X and Y (UTM zone 40 N, as in AutoCAD, Persian
  digits fine); Enter or «برو» flies there and opens the plot under the point. Typing `714299 3644453` in the search box works too.

### Background maps, the timeline and the archive panel

* **Timeline**: 1370 (1991/92) to this year, ticks every five years.
* **ماهواره‌ای** (first in the list): the newest Esri World Imagery (real pictures to z18 here; beyond that the tile is stretched, because z19 is a grey placeholder).
  Move the timeline back and the picture follows it: the release of Esri's *Wayback* archive that was current at the end of that
  Persian year (releases from 2014-02-20 on; a note on the map says which one; before 2014 there is no usable picture, the oldest one is shown and
  the note says so). Releases older than a few years have real pictures to z17 only, so zoomed in they are blurrier. Set `GIS_WAYBACK_CONFIG_URL=` (empty)
  to turn dated imagery off, or `GIS_SATELLITE_TILE_URL` to use another provider (then Wayback is off).
* **نقشه‌ی خیابانی روشن (CARTO Voyager)** and OpenStreetMap; `GIS_STREET_TILE_URL` / `GIS_OSM_TILE_URL` replace them, `GIS_EXTRA_BASEMAPS`
  (a JSON list) adds more, e.g. an Iranian provider with a key.
* The plots are a faint, clickable skin over every background map (not only the plan), so the picture stays visible.
* If no satellite tile arrives (12 failed requests, none loaded) the page says the provider is probably blocked on that network
  (Esri usually is in Iran): use «نقشه‌ی طرح» or a street map, or a VPN.
* The **sheet frame and its coordinate grid** (layer `58-0`: the 400 m grid, its numbers) are not drawn.
* The crosshair-free toggle at the top (columns icon) hides the archive panel so the map gets the whole width; the choice is remembered.

## Details around the plots (جزئیات نقشه)

One tick box per group in the layers panel (and a master box). They come from the detail drawing (1405) and are served
by `/gis/<slug>/context/` (same access as the rest of the map; read from `main/data/gis/<slug>_context.geojson`).

| Group | Layers of the drawing |
|---|---|
| معابر | راه آسفالته, راه شوسه, راه جیپ‌رو, `ax road` (street axes) |
| آب و مسیل | کانال آبی (1 036), آبریز, بستر / `bastar`, لوله‌ی آب, مخزن آب, آب‌انبار, شیر آب, رشته قنات - چاه آب |
| برق و تأسیسات | تیر برق - چراغ روشنایی (939), تیر تلفن, ترانس, خط فشار قوی, منهول |
| درختان | تک درخت (1 803) |
| حدود و دام‌داری | `limit-final` and حد (village limit), دیوار, سیم خاردار, دام و طیور |
| تابلوها | تابلو |
| نام معابر | text of layer `0txt` / `dim` that is readable Persian (from zoom 17) |

A layer is used only when its name says what it is; the others are not guessed. Rebuild after a new drawing:

```
python scripts/gis/build_context_layers.py detail.dxf main/data/gis/dastgerd_context.geojson --plots main/data/gis/dastgerd.geojson
python scripts/gis/refresh_buildings.py detail.dxf main/data/gis/dastgerd.geojson      # buildings and per-plot counts only
python manage.py load_village_map dastgerd                                              # on the server, after the pull
```

`refresh_buildings.py` replaces the footprints with the drawing's `l.building` layer and recomputes every plot's
building count and area; plots, blocks, neighbourhoods and easements are untouched. Checked against the 1405 drawing:
the plots match (3 093 outlines, 1 poorly aligned, 2 not on the map); the other plots on the map are the 846 estimated ones and
the housing area's (the drawing has neither); 49 old footprints were no longer in the drawing and were removed.

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
appears in the panels of that village's technical expert, administrative expert and dehyari.

## Property inquiry (citizen panel, «استعلام خرید ملک»)

A lighter map for buyers: the citizen sees plot number, block, renewal code, land use, area, whether the plot is
inside the plan («داخل طرح») and whether it is exempt («مستثنیات»), and nothing private (no owner, permit, lock,
payment or archive data). Every card carries a disclaimer that the answer is guidance, not the official inquiry.

- Routes: `inquiry/`, `inquiry/<slug>/` (page), `…/data/` (light GeoJSON, cached), `…/search/?q=`, `…/parcels/<id>/`.
  Action `inquiry.view` in `main/access.py`; light per-user throttling (HTTP 429) in `main/views/inquiry_views.py`.
- Search accepts a renewal code (`0-0-12-69-3`), a plot number, plot-block in either order, or plot-block-zone;
  Persian digits are normalised.
- Flags live on `MapParcel.in_plan` / `MapParcel.exempt` (migration 0090) and are applied by `load_village_map` from
  `main/data/gis/<slug>_flags.json`.
- Flags are derived from the Technical-unit drawing: layer `mostsniat` (phosphor-green boxes) → exempt when ≥ 50 % of
  the plot lies inside; layer `l.karbari.p` (proposed public land use) → in the plan when ≥ 30 % does. Both thresholds
  are constants in `scripts/gis/build_plan_flags.py`; the definition of «داخل طرح» is an assumption to be confirmed
  by the dehyari.

Rebuilding the flags (DWG → DXF with AutoCAD batch mode, then):

```
python scripts/gis/extract_dxf_layers.py technical.dxf layers.json mostsniat l.karbari.p
python scripts/gis/build_plan_flags.py layers.json dastgerd
```

Deploy: `python manage.py migrate` then `python manage.py load_village_map dastgerd` (keeps archives, locks, payments).
Map icons are Keyline Icons (MIT).

### How the inquiry map is drawn

- **Street map without a tile server.** The ground is a plain light colour; streets are the gaps between plots, street names come from the
  drawing's text (`<slug>_context.geojson`, shown from zoom 16) and each plot's number is written inside it (from zoom 18). Nothing is fetched from
  CARTO/OSM, which refuse or key-gate requests from Iran.
- **Land use by colour.** Each plot is filled with the colour of its land-use class and the legend lists the classes with the names the staff gave
  them on the staff map (an unnamed colour is shown as «کاربری N (نام ثبت نشده)»); clicking a legend row shows only that land use. «داخل طرح» and
  «مستثنیات» are outlines, so both can be read at once.
- The number written inside a plot in the drawing is the *plot number* (شماره قطعه); the card shows it as such.

### Satellite imagery served by this site

Esri and Google refuse requests from Iran (the server and the visitors' browsers), so the village's picture is stored with the code:
`main/data/gis/tiles/<slug>/satellite/<z>/<x>/<y>.jpg`, served by `gis/<slug>/tiles/satellite/{z}/{x}/{y}.jpg` (login required, `main/gis/tiles.py`).
Both the staff map and the inquiry map use it; the staff map's dated-imagery timeline (Wayback, hosted abroad) is off while stored tiles exist.

```
python scripts/gis/cache_tiles.py dastgerd                      # Esri World Imagery, zoom 13-18, run once from a machine that can reach it
python scripts/gis/cache_tiles.py dastgerd --url 'https://…/{z}/{x}/{y}.jpg' --max-zoom 19   # another provider (mind its terms)
```

Only the village's own area is fetched (about 600 tiles, a few MB). Esri has no real picture beyond zoom 18, so deeper zoom stretches it; the
attribution is shown on the map. Setting `GIS_SATELLITE_TILE_URL` (an Iranian provider) makes the site use that instead of the stored tiles.

## Plot-number series (دسته‌ی شماره‌ی قطعه)

Besides the village's own block-and-plot numbering, a village may have **series**: subdivisions whose plots are numbered 1, 2, 3 ... on their own (the first is the
«بیست هکتاری», 533 plots, numbers 1 to 539). A bare plot number is therefore ambiguous, so every search takes the series with it.

- A series plot is an ordinary `MapParcel` with `series = '<key>'` (empty for the village's own plots), no block, no neighbourhood and no renewal code. The registry
  is `main/gis/series.py` (`SERIES[slug][key]`: name, search aliases, outline file); a second and third series are one more entry and one more file.
- The outlines and numbers come from a drawing with `scripts/gis/build_plot_series.py <file.dxf> <slug> <key> --layer … --box xmin ymin xmax ymax`: the lines of one
  layer inside the box (a drawing may hold the same plan several times side by side) are closed into outlines, and every outline holding exactly one number text is a
  plot. The «بیست هکتاری» came from `اصلاحات93.dwg` (layer `tafkek`, the copy at x 713400-714300). Numbers whose outline could not be closed are left out (11 here: 49, 105,
  358, 380, 383, 407, 413, 419, 430, 522, 527); a number written on two plots keeps both (517, 518, 529, one more).
- `load_village_map` loads the series after the village (`series.load`), never deletes a series plot that has an archive, payments or a lock, and never touches the
  village's own plots when a series file changes (migration 0092 loaded the first one).
- Search (citizen inquiry map and the staff map): name the series («بیست هکتاری ۱۲» or «۲۰ هکتاری-۱۲») or choose it in the inquiry map's menu
  (`همه‌ی دسته‌ها / روستا (قطعه و بلوک) / بیست هکتاری`, `?series=` on the search URL). A number alone lists the series' plot first, then the village's plots. Choosing a series also
  shows only its plots on the inquiry map and zooms to them.
- Cards and lists say «قطعه‌ی شماره‌ی N» with the series name instead of block and neighbourhood; the staff map's plot labels and archive panel show the same.

Deploy: `git pull`, `python manage.py migrate` (adds the column and loads the series), restart.
