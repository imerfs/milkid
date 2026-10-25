# Office system: letters, appointments, role grants

Scope agreed from the request; assumptions are marked **(A)** so they can be corrected.

## 1. Role grants (دهیار نقش می‌دهد)
- The dehyari can give a user of **their own village** one of: accountant, engineer, inspector, council — and take it back (user returns to citizen).
- **(A)** "Own village" = `UserProfile.city_village` equals the dehyari's `Municipality.city_village`. An admin may do it anywhere.
- Only those four roles are grantable. `admin`, `dehyari` and the dehyari's own account can never be changed through this feature.
- Every change is kept in `RoleGrant` (who, whom, old → new role, when). Granting the role someone already has does nothing (idempotent).
- Fixes a hole in the older staff screens: they accepted any `role` value from the form (a dehyari could create admins).

## 2. Official letters (مکاتبات اداری)
- A letter has: number (`year/sequence`, per municipality), subject, body, priority (normal / urgent / immediate), confidentiality, recipients (to / cc), attachments, optional parent (reply), status draft / sent.
- Views: inbox, sent, drafts, archive, compose, read, reply, archive/unarchive. Opening a letter marks it read for that recipient only.
- **(A)** Recipients must belong to the sender's village. Citizens may write to staff roles only (not to other citizens). Admin is unrestricted.
- Sending twice (double click / retry) creates one letter (idempotency token). A user may send at most 30 letters per hour.
- Only sender and recipients can open a letter; confidential letters are never listed to anyone else, not even in counts.

## 3. Appointments (وقت‌دهی)
- **Who:** only citizens (citizen / owner / resident) book. They book the technical staff (engineer = the dehyari/shahrdari expert, inspector) and the council members of their home village or of the dehyari/shahrdari they switched to. Nobody else books, and the dehyari, accountant and clerk neither receive nor book.
- Those three roles set weekly availability (weekday, from, to, slot length).
- **Where:** inside each panel, never on a page of its own (`main/office/visits.py` + `partials/visits_panel.html`): a "گرفتن وقت ملاقات" tab in the citizen panel, a "وقت‌های ملاقات" tab in the inspector and council panels, a collapsible block in the expert panel. The actions in `appointment_views.py` redirect back to the panel; the old page URLs redirect there too.
- Two bookings can never share a slot (database constraint). Booking the same slot again by the same user returns the existing booking.
- Provider confirms / rejects / completes; either side cancels. Every change notifies the other person.
- Limits: 5 open appointments per user, slots start at least 1 hour from now, bookable 14 days ahead.

## Definition of done (from the standards sheet, translated)
| Standard | What it means here |
|---|---|
| Frontend | every new page has loading, empty, error and success states and works at 375 px |
| API/logic | input validated at the boundary, errors are typed (403/404/409/429), repeat requests are safe |
| Database | explicit constraints, forward-only migrations, no business logic in triggers |
| Permissions | enforced in the query/service layer (not only hidden buttons); one policy table |
| Security | uploads checked by type and size; all text escaped; no secrets |
| Spending cap | per-user hourly cap on letters and open appointments |
| Not in code | hosting, cloud cost, CDN, scaling, alerting, backups: see below |

## Status against the 14-layer sheet
| # | Layer (plain words) | Status |
|---|---|---|
| 01 | Every page has loading / empty / error / success, works at 375 px | Done for the new pages; checked in a browser at 375 px |
| 02 | Input checked at the door, typed errors, safe to repeat | Done (400/403/404/409/429, idempotency token, repeat-safe actions) |
| 03 | Explicit DB rules, forward-only migrations, no hidden logic | Done (migrations 0031-0033, constraints, no triggers) |
| 04 | Permissions enforced in the data layer | Done in the service/query layer. The database itself (SQLite) has no row-level security; moving to PostgreSQL would allow it |
| 05 | One-command repeatable release with a used rollback | **Not done**: no hosting chosen. Proposal: Docker image + one deploy command, rollback = previous image, rehearsed once |
| 06 | Every paid resource has a unit cost, monthly cap, alert | **Not applicable yet** (nothing paid is used). Decide with the hosting choice |
| 07 | Main branch always releasable, checks before merge | CI workflow added (`.github/workflows/ci.yml`): tests, migrations check, CSS build check. Not yet run on GitHub. No staging environment |
| 08 | No secrets in code, every input hostile | Done: escaping, upload checks (a validator that never rejected anything was fixed), no secrets added |
| 09 | A spending ceiling nobody can blow overnight | Partly: per-user caps (30 letters/hour, 5 open appointments). **Not done**: per-IP limits and a global kill-switch |
| 10 | Cache / CDN | **Not done**. Proposal: WhiteNoise or a CDN for static files with long cache headers |
| 11 | Known bottleneck, plan for 10x traffic | **Not measured.** Likely first limits: SQLite and two small count queries per page. Proposal: measure with realistic data, move to PostgreSQL |
| 12 | Errors reach a channel with a trace id; clean logs | **Not done**. Proposal: Sentry + JSON logs |
| 13 | Backups tested by a real restore | **Not done**. Proposal: nightly dump + a monthly restore drill with the time written down |
| 14 | The one number that proves the customer got the result | Added: `python manage.py office_metrics` (median hours until a letter is read; share of appointments that actually happened) |
