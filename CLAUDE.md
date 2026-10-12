# MelkID working memory

- Stack: Django (decided, see docs/adr/0001-stack-and-hosting.md). Persian UI (RTL, Jalali dates, Persian digits); code, comments and docs in English.
- Layout: all code lives in the `main` app (main/models, main/views, main/templates, main/tests). New modules are separate files/subpackages inside it. Do not restructure into `src/modules/...`.
- Hosting: single Ubuntu 24 VPS at /opt/milkid (gunicorn behind nginx, Let's Encrypt, domain amirl.ir). Deploys are done by the user; cloud sessions cannot SSH.
- Tests: `python manage.py test`. Tests come first for money logic, access control and validation.
- Skills: committed under .claude/skills/. obsidian-cli is not installed (needs the Obsidian desktop app); docs live in docs/.
