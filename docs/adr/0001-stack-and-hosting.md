# ADR 0001: Stack, layout and hosting

Status: accepted

## Decisions
- Django, with all code in the existing `main` app. The generic `src/modules/...` layout from the original brief does not apply.
- Hosting stays on the current Ubuntu 24 VPS (gunicorn + nginx, domain amirl.ir). The brief's "no physical server" is read as "no hardware we own or maintain": the VPS is rented. Layers 5, 6, 11 and 13 are satisfied on the VPS (Docker/PostgreSQL path proven in CI, nightly backups, health check) and a managed-platform migration only happens if the owner asks.

## Consequences
- Scaling path: stateless gunicorn workers, PostgreSQL, then a second VPS behind a load balancer.
