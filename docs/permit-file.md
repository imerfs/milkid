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
