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

## Step 3: the Bonyad's answer
The Bonyad-e Maskan answers on paper (form الف۲-۱ with a tracking code and a QR); it has no access to the system, so the owner
brings the answer back.
- **Owner** (file page, step 3): uploads the scan (pdf/jpg/png) and types the figures from it (`main/office/permit_step3.py: clean`):
  letter number, tracking code, date, the request number the letter names, allowed / denied, validity, floors, occupancy, allowed
  floor area, heights, and optionally the plot centre's UTM X/Y.
- **Staff** (clerk, expert or dehyari): see the scan beside the system's own comparison (`checks`): the request number against form 1's,
  the area against the file's, dates (after form 1, not expired), a tracking code already used in another file, and the distance between
  the letter's plot centre and the plot on the map. They check the code on the Bonyad's site, may correct a figure, tick «صحت را بررسی
  کردم» and confirm, or send the file back with a reason (the owner uploads again).
- A confirmed «مجاز» answer moves the file to step 4 and is written in the map plot's permit notes; a confirmed «غیرمجاز» ends the file.

## Step 4: engineers, plans, forms 04-07 and the dehyari's signature
After the Bonyad's answer the Bonyad introduces the owner to the drawing offices and a supervising engineer (outside this system).
- **Forms** (`permits/<id>/design/`, `static/js/permit-design-forms.js`): 04 دستور تهیه‌ی نقشه (from the Bonyad's answer and form 1:
  allowed floors and area, the four sides, passage widths), 05 تعهد معماری, 06 تعهد محاسبات سازه, 07 تعهد نظارت. Filled from the file
  and the engineers the owner enters; drawn in the browser (04 and 07 over their blank forms, 05 and 06 typeset on the dehyari's
  letterhead), downloaded as PDF or printed. The engineers and the dehyari sign them on paper.
- **Plans:** the owner uploads every sheet except the signed forms (architecture, structure, other; pdf/jpg/png/dwg/dxf), can delete
  until sending, and sends the set. Each sheet's SHA-256 is kept on arrival.
- **Review:** clerk / expert / dehyari tick that the signed forms 05-07 reached the office and confirm, or send the set back with a
  reason. **Signature:** only the dehyari (`permit.sign`) signs, from «reviewed» (or in one go from «submitted» by ticking the forms):
  the file records who, when and a fingerprint over all sheets; sheets changed afterwards are flagged. Signing moves the file to step 5.

## Step 5: the fees (the financial officer)
After the dehyari signs the plans, the village's financial officer (`accountant`, or the dehyari: action `permit.fees`) is notified and
opens `permits/<id>/fees/` (also listed on the accountant dashboard, `permits.fee_rows_for`).
- The page lists the **31 rows** of the «فرم محاسبه عوارض و بهای خدمات» (`permit_step5.ROWS`: residential, commercial, service/workshop,
  industrial building fees by floor, fence, annexed land, added value, expert / fire-service / file / yearly fees) plus three free rows
  (e.g. تفکیک عرصه). The officer ticks the rows that apply and sets each amount in rials; no formula is enforced (the dehyari has none).
  Each row can keep the form's factors (area, built area, council factor B, value P, factor P, height, floors, expert price difference);
  the page only offers their product as a suggestion (120 × 220000 × 1.3 × 5 × 0.5 = 85,800,000 as in the sample).
- «Save» keeps the draft; «Save and send» (`fees_state` `offered`) tells the owner. The owner sees only the chosen rows and the total,
  can print the sheet, and **approves** (the file moves to step 6) or **objects** with a note (`objected`: the officer revises and resends).

## Step 6: payment and the introduction to the Social Security Organisation
- The owner pays at the dehyari's bank account and records each slip (number, Jalali date, amount, optional scan kept privately as
  `fee_receipt`); clerk / expert / dehyari / the officer confirm it. A slip the staff record is confirmed at once. When the confirmed
  total covers the approved total the file is «paid up» (`PermitFile.paid_up`).
- Then clerk / expert / dehyari **issue the letter** (number, date, branch, the building fees the insurance share is taken from — default
  the sum of rows 1-5, 7-11, 13-17, 18-22 —, built area, street width, optional «this dehyari has no fee formula» sentence). The letter
  is drawn in the browser on the dehyari letterhead (`static/js/permit-insurance-letter.js`) and downloaded or printed; the dehyari
  stamps and signs it on paper. Issuing freezes the payments (`insurance_state` `introduced`).

## On paper at every step
The forms are still signed and handed to the dehyari by hand. `main/templates/main/permits/_paper.html` tells the owner, at each step,
what to print, who signs it and what to bring.

## Step 6 (end): the Social Security certificate
After the introduction letter (`insurance_state` `introduced`) the owner pays the insurance share at the Social Security branch and
uploads the certificate with the hologram (`permit_step6.py`: scan + number, date, workshop number, area, the fees it names, the
premium, the payment slip). The original goes to the dehyari. Clerk / expert / dehyari see the system's comparison (fees and area against
the introduction letter, date after the letter, duplicate certificate number, owner name), tick that the original's hologram was seen,
may correct a figure and confirm (`verified`, the file moves to step 7) or send it back with a reason (`returned`).

## Step 7: the building permit form (پروانه ساختمان)
`permits/<id>/licence/` (`permit_step7.py`, `static/js/permit-licence-form.js`). The three pages of the permit (permit and fee slip
numbers, owner, plot, engineers, existing state, the four sides, areas and density, usage, structure, floors table, parking, notes,
signature names) are drawn in the browser, prefilled from the file: owner, plot, Bonyad's allowed figures and Bonyad permit number,
the sides from form 1 / step 4, the engineers of step 4, the fee slip and the insurance slip, the next registration number. The
clerk / expert / dehyari change any field, save, download or print. The dehyari and the supervising engineer sign and stamp the printed
form **by hand**; the staff then tick «signed and handed to the owner» and issue (`licence_state` `issued`), which freezes the form
and tells the owner. The plot sketch is not drawn: the plot map printed from the step-2 forms page is glued on page 2.

## Renewal of the permit's term (تمدید مهلت پروانه)
A permit is valid **one year** from its issue date (`permit_extension.expiry`: valid / soon (≤30 days) / expired), renewable at most twice
(«نوبت اول / دوم»); the next term starts where the previous one ended. `permits/<id>/extension/` (linked from the file page):
- The owner (or the clerk / expert / dehyari for a walk-in owner) opens a request once the permit is in its last 30 days or past it.
- The page prefills the owner's «فرم درخواست» and the renewal form from the file and the permit form; the staff change, save, download
  or print them. The owner **signs and puts a fingerprint** on the request; the **dehyari and the technical manager (technical expert)
  sign and stamp** the renewal, all by hand. The staff tick both and record the renewal.
- `python manage.py permit_expiry_notices` (run daily, e.g. cron) tells owners once per term when a permit is about to end or has ended.
- The file's status line and the panels show «N days left» / «renewal needed» / «renewal request waiting».
