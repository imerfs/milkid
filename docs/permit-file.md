# Building-permit file (پرونده‌ی پروانه ساختمان)

The permit process has nine steps (the pages in `main/templates/main/services/building-permits/`, titles in
`main/models_permit.py: STAGES`). **Step 1, «افتتاح پرونده», works end to end; steps 2-9 are still static pages.**

## Step 1
1. **The applicant** (a citizen) fills `services/building-permit/` (`main/views/permit_views.py: building_permit_form`):
   the owner (prefilled from the profile), the property, the other owners with their own identity papers (optional),
   the ownership paper (deed / agreement / Bonyad-e Maskan lease contract), identity papers and the shamim file.
   What was typed is kept in the profile (`father_name`, `id_number`, `birth_date`, `birth_place`) for the next time.
2. `main/office/permit_form.py` reads and checks the post; `main/office/permits.py: submit` creates the `ServiceRequest`
   (through `lifecycle.submit`), the `PermitFile`, the `PermitPerson`s and the `PermitDocument`s, and tells the village's
   clerk, expert and dehyari.
3. **The staff** (clerk, expert or dehyari, policy `permit.open`) open `permits/<id>/` (inside the panel's drawer):
   give the **renewal code** from the shamim file (the lot number suggests plots of the map), or send the file back for
   missing papers, or refuse it. Opening moves the file to step 2, sets the request `in_review` and writes the owner and the
   permit onto the plot of the village map (blank fields only).
4. The map's plot card lists everything filed for the plot (`permits.parcel_requests`).

## Where it shows
- Clerk desk: tab «پرونده‌های پروانه»; expert panel: section «پرونده‌های پروانه ساختمان»; dehyari panel: tab «پرونده‌های پروانه».
- Identity papers live in `PRIVATE_MEDIA_ROOT/permit_files/` (never `/media/`), served only to the applicant and the village's
  staff through `permits/documents/<id>/` (`nosniff`, shamim files as downloads).
- The site-wide upload guard (`main/upload_guard.py`) allows zip / geojson / kml only on the permit form and its supplement URL.

## Step 2: forms 1 and 2 and the plot map
Our system is for the dehyaris only; the Bonyad-e Maskan has no access, so step 2 saves trips instead: the owner downloads
filled forms, gets the dehyari's stamp and signature, and takes them to the Bonyad.

- **The shamim file is an AutoCAD file.** On arrival `main/office/shamim.py` reads it (DXF; also GeoJSON, KML, or a zip of
  one; a DWG is explained, not guessed): the closed outline closest to the declared area is the plot, its UTM zone-40 (or
  lat/lng) coordinates are laid on the village map, and the plot under it is suggested to the clerk with its renewal code
  (file page, «بررسی خودکار فایل شمیم»). Area differences over 5 % are pointed out.
- **Form 1** (`استعلام ضوابط ساخت‌وساز`): filled by the clerk / expert / dehyari from the file; the four limits (length and
  neighbour lot or «معبر») are measured on the map outline (`main/office/plotmap.py`). Its second page is the plot map
  drawn from the village map. Form 1's registration number continues the village's own pattern.
- **Form 2** (`تقاضای صدور پروانه ساختمان روستایی`): filled by the owner, prefilled from the file (deed box or lease box by the
  ownership paper, purpose, attachments). Its registration number is given by the staff on form 1's editor.
- **Download:** `permits/<id>/forms/` draws the data over the blank forms (`static/forms/permit/`) in the browser, so Persian
  is shaped by the browser, and saves PDF (form 1 + map; form 2) or prints. Field positions are in `static/js/permit-forms.js`.
- **Handing over** (`permit_deliver`): when both forms are saved and the signed copies are given to the owner, the staff mark it
  and the file moves to step 3 (the Bonyad's answer).
