# Agent Guide - IoT-Management (Backend)

Purpose: give coding agents enough repository context to start making correct edits without repeating discovery each run.

## Repo Identity

- Stack: Django 4, DRF, Channels, Celery, Redis, MongoDB (Djongo), optional ClickHouse.
- Main app root: `src/`
- Docker is the default execution environment for this repo; use the container workflow unless a task explicitly requires a local-only setup.
- Docker service entrypoint: `docker-compose.yaml` -> service `app`.
- Public API/docs (default docker): `http://localhost:8113/swagger/`

## High-Value Paths

- `src/manage.py`: Django command entrypoint.
- `src/iot_server/`: project settings, ASGI/WSGI, URLs.
- `src/api/`: API-layer modules (permissions, throttling, websocket consumers, serializers, viewsets).
- `src/device/`, `src/event/`, `src/notification/`, `src/dashboard/`: domain apps.
- `docker-compose.yaml`: local service topology.
- `src/start-services.sh`: container startup sequence.
- `src/requirements.txt`: Python dependency lock list.

## Runbook

### Default workflow: Docker-first (required unless task says otherwise)

1. `docker-compose up --build`
2. `docker-compose exec app python manage.py migrate`
3. Optional admin user: `docker-compose exec app python manage.py createsuperuser`
4. For repo checks, tests, and Django commands, run them inside the container: `docker-compose exec app ...`

### Local workflow (only for explicit local debugging or when Docker is unavailable)

1. `cd src`
2. `pip install -r requirements.txt`
3. Configure env in `src/iot_server/.env`
4. `python manage.py migrate`
5. `python manage.py runserver 0.0.0.0:8000`

### Typical side processes

- Celery worker: `docker-compose exec app celery -A iot_server worker -l info`
- Celery beat: `docker-compose exec app celery -A iot_server beat -l info`
- MQTT listener: `docker-compose exec app python manage.py mqtt`

### Agent rule

- If a command can be run via Docker, prefer the container version for consistency with the production-like environment.
- Do not assume a host-local Python environment is the canonical runtime for this repo.

## Change Routing Rules

- New API endpoint behavior:
  - update or add serializers in `src/api/serializers/`
  - implement logic in `src/api/viewsets/` (or corresponding app viewset modules)
  - register routes in `src/api/urls.py` (or project URLs when needed)
- Permission/throttle concerns belong in `src/api/permissions.py` and `src/api/throttling.py`.
- WebSocket behavior belongs in `src/api/socket_consumers.py` and `src/api/websocket_routing.py`.
- Domain model changes should be localized to the matching app folder (`src/device/`, `src/event/`, etc.) and paired with migrations.

## Validation Checklist For Agents

- Run focused Django checks/tests for touched area before broad test runs.
- Prefer Docker-backed validation commands, such as `docker-compose exec app python manage.py test ...` or `docker-compose exec app python manage.py check`.
- If models changed: run `docker-compose exec app python manage.py makemigrations --check` and migrate flow validation.
- If API schema/serializer changed: quickly validate impacted endpoints via DRF tests or manual request examples inside the container.
- If websocket logic changed: validate route registration and consumer import paths.
- If a local command is suggested in docs or prior context but a Docker equivalent exists, prefer the Docker equivalent.

## Guardrails

- Prefer minimal edits; avoid broad refactors unless explicitly requested.
- Do not modify infra files (`Dockerfile`, `docker-compose.yaml`, supervisor config) unless the task requires it.
- Preserve API contracts unless the task explicitly asks for a breaking change.
- Keep secrets out of code and docs; use environment variables.

## Fast Discovery Hints

- To find endpoint implementation quickly, start from `src/api/urls.py` and follow imports.
- To trace async behavior, inspect `src/api/socket_consumers.py` and project ASGI wiring in `src/iot_server/`.
- To debug startup issues, inspect `docker-compose.yaml`, `src/start-services.sh`, and `supervisord.conf`.

## Frontend Integration Contract

- Frontend repo expects backend API base similar to `http://localhost:8113` in local mode.
- Keep CORS and CSRF settings aligned with frontend host/port when changing auth or origin policy.
