FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS python-build-stage

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# uv.lock is optional (the glob tolerates its absence) but committing one makes
# the build reproducible.
COPY pyproject.toml uv.lock* ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project --no-dev


FROM node:lts-alpine AS vite-build-stage

WORKDIR /usr/src/frontend

COPY ./frontend/package.json ./frontend/package-lock.json* ./

RUN --mount=type=cache,target=/root/.npm \
    npm ci || npm install

COPY ./frontend .
# Tailwind scans the Django templates for class names, so they must be present
# at build time even though nothing else in this stage uses them.
COPY ./app/templates /usr/src/app/templates

RUN npm run build


FROM python:3.13-slim-bookworm AS python-run-stage

ARG VERSION=dev
ENV APP_VERSION=$VERSION

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=timelines.settings.prod

COPY --from=vite-build-stage /usr/src/frontend/build /usr/src/frontend/build
COPY --from=python-build-stage /app/.venv /app/.venv

WORKDIR /usr/src/app

RUN addgroup --system app && \
    adduser --system --ingroup app app

RUN apt-get update && \
    apt-get install --no-install-recommends -y gettext supervisor libpq5 && \
    rm -rf /var/lib/apt/lists/*

COPY --chown=app:app ./docker/prod/django/start /start
COPY --chown=app:app ./docker/prod/supervisord/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY --chown=app:app ./docker/prod/supervisord/start /start-supervisor

# Strip CRLF so the scripts run when the repo was cloned on Windows.
RUN sed -i 's/\r$//g' /start* && chmod +x /start*

COPY --chown=app:app ./app .

RUN chown -R app:app /usr/src/app /usr/src/frontend && \
    mkdir -p /var/tmp/django_cache /usr/src/app/data && \
    chown -R app:app /var/tmp/django_cache /usr/src/app/data

USER app

# SECRET_KEY is only needed to import settings here; the real one comes from the
# environment at runtime.
RUN SECRET_KEY=build SQL_DATABASE=build python manage.py compilemessages && \
    SECRET_KEY=build SQL_DATABASE=build python manage.py collectstatic --noinput

CMD ["/start-supervisor"]
