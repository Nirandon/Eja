# Cash Me Crying
*Track your spending. Try not to cry.*

Local Thai/English finance website. Python standard library + SQLite + Ollama, with no paid AI API. Run the Python server on the same Mac as Ollama. Code is not automatically uploaded to GitHub.

## Instructor quick start (no model needed for the first UI check)
The course slides say projects may be selected from GitHub and run. This repository contains the application source; the reference PDFs alone are not the app.

```sh
git clone https://github.com/Nirandon/Eja.git
cd Eja
python3 server.py
```
Open **http://localhost:8000**, choose **Demo parser**, enter `Lunch 120, coffee 80 from KBank`, analyze, review, and confirm. Demo parser is a limited rule-based fallback, not Generative AI. To test actual AI text/image understanding, follow the Ollama model setup below. The runtime uses only Python's standard library; no `pip install` step is needed.

The host only needs Ollama for AI inference; models are downloaded separately and are not stored in Git. Browser speech recognition may need internet and microphone permission. The app starts with an empty local ledger and creates its own `data/cash.db`.

## Start
```sh
python3 server.py
```
Open **http://localhost:8000** in Chrome. Leave this terminal open. Data persists in `data/cash.db`. Stop with Control+C. `PORT` changes the listening port; `CMC_DATABASE` selects another database file.

Requires Python 3.10+ (3.12 recommended), and a recent [Ollama for Mac](https://ollama.com/download/mac). Install and open Ollama, then in another Terminal:
```sh
ollama pull qwen3:1.7b
ollama pull qwen2.5vl:3b
```
The first model handles text; the second reads images. Downloads require internet and several GB of disk. Vision inference can be slow on a MacBook Air and may need a smaller crop. Text and image extraction run through `127.0.0.1:11434`, without an API key. Models do not inherit this development chat. Change models with `OLLAMA_MODEL` and `OLLAMA_VISION_MODEL` before starting the server; the vision replacement must support image inputs. Allow up to four minutes for the vision response.

## v5: editorial design and workspace covers
This update includes all v4 changes and can be installed directly over v3. The interface now uses a restrained editorial grid, large typography, sharp corners, and an image panel on Overview. Default palette: Matcha `#575d41`, Lavender Rose `#efd4dd`, Mocha `#332e2e`, Shell `#e5e0da`. The original default green is migrated once to Matcha; other saved colors remain. Custom workspace colors are still available.

Use **Add your image** on Overview, or **Categories & theme → Landing image**, to choose a JPG/PNG/WebP under 8 MB. The browser converts/resizes it to a JPEG before saving it in the local SQLite database, separately per workspace. Cover images are not analyzed or sent to AI. Remove or replace them any time. Unlike Import image, a chosen landing cover is intentionally persisted; database backups include it.

## v4: defaults and better extraction
In **My accounts**, click **Use as workspace default**, or choose the default in **Categories & theme**. This preference is stored separately per workspace. Missing payment accounts in new income/expense text, voice and image proposals use the default. Explicit accounts override it; unknown explicit banks remain unresolved. Internal transfers never guess their endpoints. Corrections preserve existing accounts unless changed explicitly. Review still happens before saving.

Category editing includes comma-separated **Keywords** (for example GF → แฟน, เดต). Prompts receive these hints and recent confirmed examples in THB. Deterministic checks recognize explicit categories, unique keyword matches, exact previously classified descriptions, common merchants, relative days, Thai/English month names and Thai Buddhist dates. This does not fine-tune a model and does not guarantee every ambiguous phrase is understood. Conflicts should be reviewed. Image dates are never inferred from the current date merely because an image date is unreadable.

Ollama requests now explicitly use `num_ctx=8192` for both models, and errors include the actual Ollama error rather than only HTTP 400. Larger context uses more RAM. Workspace themes also tint buttons, icons, charts, tip illustration, focus rings, selected month and report accents; red remains for errors/overspending.

## What is included
- **Workspaces:** Personal and named projects each have their own ledger, bank/cash allocations, categories, plans, reminders, and saved theme. These are single-user workspaces, not authenticated user accounts. A bank name repeated across workspaces is a separate allocation; do not duplicate the same starting funds across projects.
- **Dashboard:** Monthly income, expenses, net, closing balance, category/account spending breakdowns, year selection, and all-time available funds. Transfers are excluded from income and expenses.
- **Transactions:** Add/edit/delete, Thai/English Ollama proposals and natural-language corrections, editable confirmation. A deliberately limited Demo parser is labeled as rules, not AI. No extraction saves automatically.
- **Date/amount guards:** New text transactions without date words default to today in Asia/Bangkok. Single relative-day references use deterministic dates. A bare numeric purchase amount such as `ซื้อสกุชชี่30` is treated as THB, not a day count. Corrections retain the existing date unless a date is specified. Complex dates still require review.
- **Budget & plans:** Select any month, including future months; set an overall spending limit, optional limits per category, planned expenses, and plan notes. Blank means no limit; zero is an explicit zero budget. Plans persist in SQLite and never create transactions. Category limits are parts of the overall budget. Planned and actual spending are separate.
- **Categories & theme:** Add/rename categories such as Party/GF. Rename updates previous records and saved plan entries in that workspace. Other remains the fallback category. Colors save per workspace; choose Rose for a pink project. Custom categories are included in AI prompts.
- **Notes & reminders:** Add notes, optional due dates, edit, mark done/reopen, delete. Overdue status is shown in the app. No OS notifications, email, or alerts while the website is closed.
- **PDF report:** Select a month on Overview, click Export PDF, then Print / Save as PDF. In Chrome select Destination → Save as PDF; on macOS a print dialog may also offer PDF → Save as PDF. Includes totals, closing balances, category spending, budget/plan, reconciliation adjustments and transactions for the selected workspace/month. Rendering is done by the browser to preserve Thai text. This is not a one-click server-generated PDF download.
- **Voice:** Browser SpeechRecognition in Chrome/Edge. Browser speech may send audio to an online speech service and is not guaranteed offline. Review transcription before analysis. No extra paid API is configured.

## Import image
Choose **Import image** or the Image button in the composer. Upload PNG/JPG/WebP (maximum 8 MB). The browser resizes it to at most 2200 pixels on its longest side and sends it to local Ollama. The application does not persist images; extracted proposals/confirmed records are separate.

Supported workflows:
1. **Receipt:** propose one total purchase, not individual items plus total.
2. **Payment slip:** propose income/expense/internal transfer using visible direction and owned accounts; ambiguous ownership requires review.
3. **Screenshot of Google Sheets or another tracker:** propose rows. This is image reading, not a live Google Sheets connection or CSV/XLSX importer. Crop large tables into clear sections (maximum 30 transactions per image).
4. **Bank balance screenshot:** propose an observed amount/account/date. Confirm through the separate balance dialog. This creates a reconciliation adjustment, not income or expense. If a date is not visible, choose it yourself. It is not silently replaced with today.

Before saving, review every row, date, year, amount, payment account and category. Thai Buddhist years are normalized by subtracting 543. Unreadable fields stay empty. Image model accuracy varies and the app cannot verify the contents of a slip against a bank. Matching date/amount/account/description produces a duplicate warning; this does not catch all duplicates.

### Balance snapshot rules
Snapshots reconcile the account at the **end of the selected date**. Import that day's transactions first. Adjustment = observed balance minus the ledger balance through that date. It is stored separately, visible/removable in My accounts, and excluded from income/expenses/budget spending. Closing balances and available funds include adjustments. Adding backdated transactions later can make a previous reconciliation differ from its observed balance; review or replace the adjustment if needed. Confirming a screenshot without changing a ledger balance records a zero adjustment.

## Data, backup and upgrading
Use only synthetic records in public repositories/demos. `.gitignore` excludes data, backups, uploads, and Python caches. Stop the server and copy `data/cash.db` for a backup. Upgrade scripts back up the database and old application code before replacing source. Schema migrations are idempotent. Existing records are preserved; single-workspace databases migrate to Personal. Code updates do not rewrite incorrectly saved historical dates automatically.

## Checks
```sh
python3 -m unittest discover -s tests -v
node --check static/app.js
```
The backend suite covers exact money accounting, transfers, date defaults, workspace isolation, upgrades, category renames, budgets, reminders, themes, balance reconciliation and report escaping. Image tests mock the model: they check validation and confirmation boundaries, not visual recognition accuracy. Browser visual/print QA and live vision-model testing were unavailable in the build environment; verify these on the demo laptop.

## Troubleshooting
- **Website unreachable:** rerun `python3 server.py` and keep the terminal open.
- **Old interface after upgrade:** restart server and hard-refresh Chrome with Command+Shift+R.
- **Text AI unavailable:** open Ollama and confirm `ollama pull qwen3:1.7b` succeeds.
- **Vision unavailable:** update Ollama and run `ollama pull qwen2.5vl:3b`.
- **Model slow or wrong:** use a sharper, smaller crop and give context such as the table month/year. Do not confirm incorrect proposals.
- **Voice denied:** check Chrome/macOS microphone permission; typing remains available.

## Remaining course scope
The five knowledge PDFs remain in the original repository root. Document RAG, a document assistant with citations, and public multi-user hosting are not implemented in this milestone. Real bank API connections are outside the MVP.
