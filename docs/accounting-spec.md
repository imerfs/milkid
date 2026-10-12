# Accounting section: spec, data model and rules

Source: ~126 screenshots of the reference product "حسابداری دهیاری" (Pars Rayaneh Shaparak), which is three
programs sharing one menu style: **Accounting** (`DbAccounting`), **Income** (`DbIncome`, cash bills and
installments) and **Payroll** (`DbPayRoll`). About 50 screens were read in detail; the rest repeat the same
dialogs (menus, empty forms, report variants). UI labels stay Persian, code and docs are English.

Defaults I picked where the screenshots are ambiguous are marked **Default**.

## 1. What the reference product does

### Accounting program (sidebar «ورود اطلاعات / بازبینی / گزارشات»)
| Screen (Persian) | Meaning | Fields seen |
|---|---|---|
| عملیات ابتدای سال مالی | Opening operation: creates the opening voucher (سند افتتاحیه) of a fiscal year | org, date (1403/01/01), operation type |
| عملیات انتهای سال مالی | Year end: closing voucher that closes temporary (income/expense) accounts, plus an error check (بررسی خطا) | org, closing date (1403/12/29), type: «سند بستن حساب‌های موقت (درآمد - هزینه)» or «سند اختتامیه» |
| ثبت اسناد | Voucher entry | number (شماره), id (شناسه), date, type, org, description, lines |
| پیش نویس سند | Draft voucher (same form, "confirm" button) | as above |
| تغییر وضعیت اسناد | Bulk status change temporary ⇄ final over a number or id range | from/to number, from/to id, direction radio, counts of final/temporary |
| تصاویر اسناد | Voucher attachments (scans) | file per voucher |
| طرف حساب‌ها | Counterparty master data | id, file no., kind (real/legal), national id, name, father name, nationality, citizenship, province, city, phone, postal code, economic code, address, goods/service type, group; bank name, account no., card no., IBAN, occupation, shop name, mobile, fax |
| تامین اعتبار | Credit provision: reserves budget for a planned expense | number, date, allocation no./date, expiry date, org, description; lines: expense account, project/service, source account, amount, note; budget table below (budget amount, credit provided, remaining) |
| خزانه اسناد پرداختنی | Treasury of payable documents (cheques) | not opened in detail |
| قراردادها | Contracts | year, number, date, type, cost center, amount, start/end date, duration, status, subject, materials, amendment flag; employer, contractor (with representative and position), supervisor; deductions %: VAT, employer insurance, contractor insurance, good-performance, tax |
| ضمانت نامه ها | Guarantees (bonds) | not opened in detail |
| تعاریف حساب‌ها | Chart of accounts (tree) | code, title, account type, party-required flag, nature (debit/credit), group, contract flag, document flag |
| تعاریف بودجه‌ای: بودجه اقتصادی | Economic budget tree, per code | account type filter: resources / uses / operational; budget code, amount, credit type, cost type, source; «کنترل بودجه» switches for resources and uses |
| تعاریف بودجه‌ای: بودجه عملیاتی | Operational budget: classification by **project** or **service**, with missions (ماموریت) as level 1 | classification code, title, budget amount, credit type |
| تعاریف اطلاعات | Lookup tables: voucher descriptions, account descriptions, signatories, banks, bank accounts, voucher images, cost centers, account groups | code + title |
| بازبینی | Review (read-only lists): vouchers, account turnover, receivable/payable documents, cost-center turnover, trade statement, counterparties, counterparty turnover, service/project turnover, voucher images, credit provision, contracts, guarantees; each with print, print preview, export to Excel |
| گزارشات | Reports: vouchers, ledgers (دفاتر), budget, trial balance (ترازنامه), receivable/payable documents, counterparties, itemized budget (بودجه تفکیکی), guarantees |
| امکانات | Bank reconciliation (مغایرت‌گیری بانکی), send trade statement, voucher renumbering, change fiscal year, change password |

Voucher types seen in the dropdown: **انبار، انتقالی، بستن حساب‌های موقت، تهاتر، درآمد، عمومی، هزینه** (+ افتتاحیه, اختتامیه).
Voucher status: **موقت** (temporary, editable) and **قطعی** (final, locked). Balance indicator: «بی‌حساب» (unbalanced) vs balanced.
Voucher numbering restarts each fiscal year; the **id (شناسه)** is a global counter that never repeats (the opening voucher is
number 1 and id 1728 of 1220 vouchers in the sample year).

Chart of accounts in the sample (3-digit groups, deeper levels shown as `6010101001`-style codes):
`111 افتتاحیه, 112 بانک‌ها, 113 بدهکاران, 114 علی‌الحساب‌ها, 116 اسناد دریافتنی, 118 سایر حساب‌ها و اسناد دریافتنی,
311 بستانکاران, 312 بیمه پرداختنی, 313 مالیات پرداختنی, 314 سپرده‌های پرداختنی, 315 بستانکاران کارکنان, 318 سایر,
410 مازاد/کسری, 411 اختتامیه`, then budget accounts: **501 منابع درآمدی, 502 منابع حاصل از واگذاری دارایی‌های سرمایه‌ای,
503 منابع حاصل از واگذاری دارایی‌های مالی, 601 مصارف هزینه‌ای, 602 تملک دارایی‌های سرمایه‌ای, 603 تملک دارایی‌های مالی.**
Sample leaf accounts: `5010101001 عوارض بر کالا و خدمات`, `6010101001 حقوق دهیار`, `1120101 بانک ملی`.
Cost centers in the sample: `1 امور مالی`, `2 امور اداری`. Voucher lines are posted against the **budget account**
(501.. for income, 601.. for expense) and a bank/payable account, so actual-vs-budget falls out of the ledger.

### Income program (sidebar «فیش نقدی، پرداختی‌ها، درآمد حمل و نقل، تقسیط، تغییر وضعیت، خزانه»)
- **فیش نقدی** (cash bill / receipt): number (auto, e.g. 124490), date, account no. (the municipality bank account),
  file no., bill type (with / without payer data), contract no., payer branch code, notes; **payer**: national id, name, payer
  type, economic code, group, postal code, phone, address; **income lines**: income type (code, title, group), quantity, unit,
  unit amount, total, discount, tax, final amount; footer: bill amount, payable, settlement method (cash, cheque...), payment
  method, payment no., payment date; status of voucher (سند), of payer data sent to the tax system (مودیان), record kind (income).
- **پرداختی‌ها** (payments): list of bills with paid / remaining amount per bill; payment tab with date, method, amount, cheque
  no./date, income account.
- **تقسیط** (installments): installment file per bill with images.
- **اسناد دریافتنی** (received cheques) and **اسناد ضمانت** (guarantee documents).
- Utilities: change fiscal year, carry data from the previous year, send to the taxpayer system, import from Excel.

### Payroll program (حقوق و دستمزد)
Main/benefits/deductions, attendance, missions, special benefits and deductions, misc payments, day workers, Eidi, personal
calculation method; groups: retired, official, contract, social-security staff, medical-insurance staff. **Out of scope for now**
(see §6).

## 2. Mapping to MelkID modules

| MelkID module | Reference feature |
|---|---|
| Levies & revenue (3) | Income program: bills (فیش), payments, installments; existing `Payment` model is the resident-facing bill |
| Expenses & budget (4) | Accounting program: vouchers, chart of accounts, budget, credit provision, reports |

## 3. Data model (all in `main/models_accounting.py`, additive migration)

All rows belong to a `Municipality` (tenant). Money is `DecimalField(max_digits=16, decimal_places=0)` in **rial** (**Default**;
the existing `Payment` stores toman, the future bridge multiplies by 10).

- `FiscalYear(municipality, year, start_date, end_date, is_closed, next_voucher_number, next_voucher_ref)` unique `(municipality, year)`.
- `AccountGroup` is not a table: the account `kind` covers it.
- `Account(municipality, code, title, parent, kind, nature, requires_party, is_postable)` unique `(municipality, code)`.
  `kind`: `asset, liability, equity, budget_resource, budget_use, closing`. `nature`: debit / credit.
  Only `is_postable` leaves take voucher lines.
- `Party(municipality, kind real/legal, national_id, name, father_name, economic_code, phone, mobile, postal_code, address, bank_name,
  account_no, iban)` unique `(municipality, national_id)` when national id is present. Real persons need a valid 10-digit
  Iranian national id (checksum), legal entities an 11-digit id.
- `CostCenter(municipality, code, title)`.
- `Voucher(municipality, fiscal_year, number, ref, date, kind, description, status temporary/final, created_by, finalized_by,
  finalized_at, deleted_at)` unique `(fiscal_year, number)`, unique `(municipality, ref)`.
- `VoucherLine(voucher, row, account, party, cost_center, description, debit, credit)`; check constraints:
  amounts `>= 0`, exactly one side positive.
- `BudgetLine(fiscal_year, account, amount)` unique `(fiscal_year, account)`; account must be `budget_resource` or `budget_use`.
  Built: `main/accounting/budget.py`, page `accounting/<year>/budget/` and Excel export. Budget is **not enforced**
  (**Default**): the report flags accounts over budget instead of blocking vouchers. Credit provision (تامین اعتبار) is not built.

## 4. Business rules (tests first)

1. A voucher line has either a debit or a credit, never both, never zero, never negative. Whole rials only.
2. A voucher can be **finalized** only if it has at least two lines and total debit == total credit. Unbalanced drafts may be saved (the
   reference shows «بی‌حساب»).
3. Final vouchers are immutable: no edit, no delete, no line change. Reverting to temporary is a separate permissioned action
   (**Default**: dehyari only) and is logged; a closed fiscal year blocks it.
4. Voucher date must fall inside its fiscal year; a closed year accepts no new or changed vouchers.
5. Voucher number is the next integer in the fiscal year, assigned inside a transaction with a row lock so two users never get the same
   number; `ref` is the municipality-wide counter. Numbers are never reused after a draft is deleted (soft delete).
6. Posting only to postable accounts; an account with `requires_party` needs a party; party and account must belong to the
   voucher's municipality (IDOR guard).
7. Opening voucher (`kind=opening`) is created by the year-start operation; closing vouchers close budget accounts against
   `410/411` (phase 3).
8. Access: `staff.accountant` (accountant, dehyari, admin). Every query is scoped to the actor's municipality; other municipalities'
   ids answer 404.
9. Reports read only; trial balance = per account sum of debit, credit and the balance, and always satisfies
   `sum(debit) == sum(credit)` over final + temporary vouchers (filter selectable).

## 5. Screens (Persian RTL, same Bootstrap base as the office module)

Phase 2: chart of accounts (tree + add/edit), parties, voucher list (filters from the reference: number range, date range, type,
status, text, amount) with status badge, voucher form (header + lines table with live debit/credit totals and balance badge),
finalize / revert, trial balance, account ledger. Reached from the accountant dashboard sidebar (replacing the dead «ثبت اسناد»,
«طرف حسابها» links).
Phase 3: budget and budget-vs-actual, credit provision, Excel export. Phase 4: bills, payments, installments tied to `Payment`.

## 6. Not built (and why)

Payroll, contracts, guarantees, treasury cheques, bank reconciliation, tax-system submission, voucher images: each is a module of
its own and none is needed to answer «what came in, what went out, what is left of the budget». They stay documented above so the
data model can grow into them without changing vouchers.
