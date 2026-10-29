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

## Supervision: forms 8-13, the technical supervisor, the Article 99 commission
`permits/<id>/supervision/` (`permit_supervision.py`, `static/js/permit-supervision-form.js`, blanks `static/forms/permit/form08..13_blank.jpg`).
After the permit is issued the owner takes six forms to the supervising engineer one at a time: 8 start of work, 9 after the foundation
concrete, 10 columns and beams, 11 roof and partitions, 12 final report, 13 the progress report with the request for the end-of-work
certificate. Each is filled from the file (permit, owner, engineer, pledge number of form 07, floors, structure, area) and drawn over the blank.
- The owner prints it, the engineer inspects and **signs and stamps by hand**, the owner signs, uploads the scan; one of the clerk /
  technical expert / dehyari confirms (or returns it with a reason), which opens the next form. Form 13 closes the supervision and moves the
  file to stage 9 (the end-of-work request).
- **Technical supervisor (inspector):** the staff link one of the village's inspectors to the file (`PermitFile.supervisor`). His dashboard
  lists his files; he sees the file (not the identity papers), fills the inspection ticks of forms 9-12 and the result, and talks with the
  owner and the staff in the file's message thread (notifications go both ways). An inspector sees only the files linked to him.
- **Violation:** a result «وقوع تخلف» (notes required) stops the form (`violation`), tells the owner and staff; the dehyari refers it to the
  Article 99 commission (`commission`), later records the vote number, date and decision, and the stage is inspected again. The votes are kept
  (`supervision.commission`); the last vote number is prefilled on form 13.
- The forms 9-12 cannot be uploaded until the inspection result without violation is recorded.

## Amendments sheet (اصلاحات و تغییرات پروانه)
On the permit page (staff, after issue) a fourth sheet is prefilled from the permit (dates, slips, sides, areas, floors) for changes the owner
makes after the permit was issued; saved under `licence.amend`, downloaded or printed, signed and stamped by the dehyari and the technical
manager by hand.

## Services: letters for electricity, gas and water (step 10)
`permits/<id>/services/` (`permit_services.py`, `static/js/permit-service-letter.js`), available after the permit is issued. Letter kinds
(from the dehyari's samples): electricity and gas **status inquiry** (form 2: the owner's request with a plot sketch box + the dehyari's reply
with areas, limits, street width, basis and UTM coordinates), **introduction for a connection** (electricity with the permit, electricity with the
end-of-work certificate, water with the permit), **gas meter placement** and the **dig permission** after the asphalt-cutting fee slip (needs the gas
company's letter number and the slip). The letter is typeset on the dehyari letterhead from the file.
- The owner (or the staff for a walk-in owner) asks; the clerk / technical expert / dehyari edit the fields, **approve** (number and date,
  which lets the owner print) or reject with a reason; the owner prints, the dehyari **signs and stamps by hand**; the staff record the handover.
- Requests waiting for approval count in the staff panels (`needs_staff`); the owner may cancel a waiting request.

## The last step: the end-of-work certificate (گواهی پایان ساخت)
`permits/<id>/endwork/` (`permit_endwork.py`, `static/js/permit-endwork-form.js`), open once forms 8-13 are confirmed (file at stage 9).
- The owner (or the staff for a walk-in owner) requests it (`endwork_state` `requested`). **Any of the clerk / technical expert / dehyari answers**:
  reject with a reason, or approve (number and date) which makes the certificate printable. The certificate is filled from the file: owner,
  plot, permit number and date, the supervising engineer and his signature number, the number and date of the last supervision report, use, limits,
  floors, total built area.
- The owner / staff print it; the **dehyari and the technical manager (technical expert) sign and stamp by hand**; the staff tick the handover
  and issue (`issued`), which ends the file (step 9 is shown done) and tells the owner. The certificate number and date are then prefilled in the
  «electricity with end-of-work» service letter.

## Non-violation certificates (گواهی عدم خلاف)
Three certificates (kinds `nov_1`..`nov_3` of the services page) follow the supervision stages: after supervision form 9 / 10 / 11 is confirmed the
owner (or the staff) may ask for the certificate of that stage, which says the building built so far (per the supervising engineer's report of
that date) has no violation and the work may go on. Same flow as the other letters: the clerk / technical expert / dehyari edit and approve it
(number and date), the owner prints it, the **dehyari and the technical manager sign and stamp it by hand**, the staff record the handover.

## Construction without a permit (ساخت‌وساز بدون پروانه): step 1
A second track on the same `PermitFile` (`track = 'unlicensed'`, the request type is `no_permit`; `models_permit.UNLICENSED_STAGES` lists its six
steps: initial file, ownership and location papers, Article 99 commission request and visit, undertaking / structural check / ruling and fine,
services, end of work). **Only step 1 is built; steps 2-6 are still the static pages under `services/construction-without-permit/`.**
- **The owner** files `services/construction-without-permit/` (`permit_views._application`, the same template and parser as the permit form with
  `track='unlicensed'`): identity, the plot, the ownership paper (deed or agreement; the Bonyad lease is not offered), the other owners, the shamim
  file, and, instead of the permit kind, the **building that stands**: built area, floors, year (optional), a note (kept in `details`).
- **The staff** (clerk, technical expert or dehyari, `permit.open`) check the papers and the shamim reading exactly as for a permit file and
  **confirm step 1** (`permits.open_file`: renewal code, plot of the village map, owner written on the plot) or send it back / refuse it. The file
  then rests at step 2 and the page says the next steps are not set up yet.
- Everything of the permit track after step 1 (forms, plans, fees, permit, supervision, services, end of work) is closed to this track:
  `permits.find` returns nothing for an unlicensed file unless the caller passes `any_track=True` (the file page, its papers, step-1 decisions and the
  shamim re-read). The staff lists show these files with their own label; the owner's notification and the history say «ساخت‌وساز بدون پروانه».

## Construction without a permit: step 2 (the request form and the undertaking)
`permits/<id>/commission/` (`permit_commission.py`, `static/js/permit-commission-forms.js`, `permits/commission.html`), open once step 1 is confirmed
(file at stage 2). Two papers for the Article 99 commission file, from the dehyari's samples:
- **«فرم درخواست»**: asks the dehyari to form the commission file and take the village's fees and the commission's fine in instalments (owner, father,
  ID-card number, street, phone, date). **«تعهدنامه»**: the owner's ten undertakings (sewage, animals in the street, pavement, facade, parking,
  neighbours' consent, missed fees, materials left in the street, occupation fee, safety). Both are filled from the file, typeset in the browser on a
  plain bordered page, downloaded as PDF or printed; the owner may correct the values (`commission.form`) and the preview follows.
- The owner **signs and leaves a fingerprint by hand** and uploads the scan of each paper (`comm_request` / `comm_undertake`, private storage), ticking
  that both are signed; a new scan replaces the one the staff sent back. `commission_state`: '' → `uploaded` → `verified` (or `returned`).
- **Any of the clerk / technical expert / dehyari** (`permit.open`) ticks that both signed papers arrived and confirms (the file moves to step 3,
  who and when are kept in `commission.checked`), or sends them back with a reason. Waiting files count in the three panels (`needs_staff`).
  Step 3 onwards is not built yet.

## Construction without a permit: step 3 (the warning notice and the technical expert's visit)
`permits/<id>/notice/` (`permit_notice.py`, `permits/notice.html`, `static/js/permit-notice-form.js`), open once step 2 is confirmed (file at stage 3).
The dehyari's warning notice to the owner (form 14, «اخطاریه به مالک») comes first, then the visit; any of the clerk / technical expert / dehyari
(`permit.open`) confirms each part.
- **Owner has the notice:** uploads the scan and types its figures (number, date not in the future, the name on it, inside / outside the master plan,
  handed over / posted). **Owner has none:** asks (`notice_state` `requested`) and goes to the dehyari in person.
- **The staff fill the notice** (`issue`, also for a walk-in owner without a request): form 14 is drawn over its blank (`static/forms/permit/form14_blank.jpg`)
  from the file: the owner's name, the address, the five breach ticks (no permit and no approved plans ticked by default, «extra built area» when the
  defence form says over a permit), inside the master plan when the plot is on the village map; the staff change anything, print or download it. The dehyari
  stamps and signs, the owner signs in person, and the owner **or the staff** upload the signed scan (`issued` → `uploaded`).
- **Checking:** the staff see the scan beside the figures and the system's comparison (the name against the file's owner, a number used in another file),
  may correct a figure, tick that it was compared with the original and confirm (`verified`; who and when in `notice.checked`) or send it back with a reason.
- **The visit:** after the confirmation the owner asks for the technical expert's visit (a future Jalali date and morning / afternoon,
  `visit_state` `requested`); any of the three staff may set the day (`scheduled`, the owner is told) and record that the visit was made (`done`, with a
  short report), which moves the file to **step 4**. Waiting items count in the three panels (`needs_staff`). Step 4 onwards is not built yet.

## Construction without a permit: step 1 reworked (defence form, shamim sketch)
Step 1 of the unlicensed track now carries everything the village needs before it opens the Article 99 file:
- **Papers:** identity papers and the ownership paper (deed, agreement / مبایعه‌نامه, or the assignment contract). For an **agreement** the owner must
  tick that it was returned to the first owner (`details.agreement_returned`).
- **Shamim file or sketch:** the owner uploads the shamim file, or ticks «فایل شمیم ندارم» (`shamim_request`) and asks the technical expert for a **sketch**
  (`permit_sketch.py`, page `permits/<id>/sketch/`, `sketch_state`): the technical expert (or the dehyari, policy `permit.sketch`) sets the fee →
  the owner pays at the dehyari's bank account and records the slip (number, Jalali date, exact amount, optional scan `sketch_slip`) → the technical expert
  / dehyari confirm the payment and deliver the file, which becomes the file's shamim file (read like any other: the map plot is suggested). The fee is not
  posted to the books here.
- **Defence form** (`permit_defence.py`, `static/js/permit-defence-form.js`, page `permits/<id>/defence/`): «فرم ارائه دفاعیات و توضیحات ذینفع یا نماینده
  قانونی متخلف ساختمانی», filled from the file (owner, father, phone, village, district, county, the built area from the filing, without a permit / over a
  permit, the dehyari's name), editable, with a free explanation (max 450 characters, two suggested sentences from the dehyari's sample). The owner prints it,
  signs and leaves a fingerprint, takes it to the dehyari for the confirmation box at the bottom, and uploads the scan (`defence_form`).
- **Confirming step 1** (any of the clerk / technical expert / dehyari, `permits.open_file`) now needs the signed defence form **and** a shamim file
  (uploaded or delivered as a sketch); otherwise the staff see what is missing. The file list says what it waits for (`PermitFile.step1_text`).
- Steps 2 (request form and undertaking) and 3 (the warning notice) follow as before.

### Step 2 forms follow the dehyari's templates (folder «2»)
The request form's subject («تقاضای ... را دارم») and its addressee are fields: the subject defaults to «تشکیل پرونده کمیسیون و تقسیط هزینه‌های دهیاری و جریمه
کمیسیون»; the addressee defaults to «شورای اسلامی روستا» as in the template and can be switched to «دهیار روستا» as on the earlier signed sample. The
undertaking is unchanged (its monthly occupation rate stays a dotted blank for the dehyari: the template shows an unreadable rate).

