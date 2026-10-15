# Village web-GIS (نقشه‌ی GIS روستا)

A map of one village's blocks and plots, with an archive per plot (building permit, owner, fee payments).
Open it from the technical expert's panel (**نقشه‌ی GIS روستای ...** in the sidebar) or at `/gis/<slug>/`, e.g. `/gis/dastgerd/`.

## Who sees it

Only the **technical expert of that village** (role `engineer`, profile village = the map's village) and admins.
Every other role, other villages' experts and anonymous visitors get 403/redirect. The map data, plot details and
archives are only served through these checks (`main/gis/access.py`, `gis.view` / `gis.edit` in `main/access.py`);
nothing about them is in `/static/`.

## What is on the map

* **Blocks** (272 for Dastgerd): outlined, numbered; the number shows from zoom 16.
* **Plots** (3 961): coloured by status, plot numbers shown from zoom 19. Grey = no archive yet, green = archive
  filled in, blue = has fee payments, red/dashed = boundary is approximate (see below).
* Search box: `69-12` selects that plot, `69` flies to block 69. Filters: all / filed / empty / approximate.
* Click a plot: side panel with the permit/owner form and the fee payments. On a phone it is a bottom sheet.
* "نقشه‌ی پایه" turns on OpenStreetMap tiles (needs internet; off by default so the map works offline).

## Renewal code (کد نوسازی)

The drawing numbers every block (`Block_No`) and numbers the plots again from 1 inside each block
(`Parcell_No`). The code is built as **block-plot**, e.g. `69-12` (`renewal_code()` in
`scripts/gis/build_village_map.py`). If the municipality's official code has another format (zone prefix, padding),
change that one function, rebuild, and run `load_village_map`. Archives stay attached (they are matched by code).

* 64 codes appear on more than one plot in the drawing; those plots are flagged and their uid gets `#2`, `#3`.
* 335 drawn plots carry no number (public land, ruins ...); they have no code but can still be opened.

## Approximate plots

In the newest part of the village the plots were numbered but their outlines were never drawn: only the block is.
For those, the block area not covered by drawn plots is divided between the numbers (Voronoi), and the plots are
marked `estimated` (dashed, red, with a warning in the panel). Replace them by redrawing the outlines in the
drawing and rebuilding.

## Data model

`VillageMap` → `MapBlock`, `MapParcel` (GeoJSON geometry, WGS84) → `ParcelArchive` (one per plot),
`ParcelFeePayment` (many per plot, whole rials). Migration `0054` loads Dastgerd from
`main/data/gis/dastgerd.geojson`, so a deploy only needs `migrate`.

Archives are empty until filled in. To load data you already have (permits, owners, payments), give it to the
developer as a table keyed by renewal code.

## Rebuilding from a new drawing

1. DWG → DXF with LibreDWG (free, `dwg2dxf.exe -y -o out.dxf drawing.dwg`) or AutoCAD (`SAVEAS` → DXF 2018).
2. `pip install -r scripts/gis/requirements.txt`
3. `python scripts/gis/build_village_map.py out.dxf main/data/gis/dastgerd.geojson --epsg 32640`
   (the drawing is in UTM zone 40N; the layers it reads are listed at the top of the script).
4. `python manage.py load_village_map dastgerd` — updates plots in place, keeps archives and payments,
   never deletes a plot that has either.

## Adding another village

Add an entry to `VILLAGES` in `main/gis/loader.py` and a migration (or run the command), build its GeoJSON, and the
sidebar link appears for that village's experts.
