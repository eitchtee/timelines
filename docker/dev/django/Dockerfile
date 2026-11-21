FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ARG VERSION=dev
ENV APP_VERSION=$VERSION

WORKDIR /usr/src/app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    DJANGO_SETTINGS_MODULE=timelines.settings.dev

RUN apt-get update && \
    apt-get install --no-install-recommends -y gettext supervisor && \
    rm -rf /var/lib/apt/lists/*

# uv.lock is optional (the glob tolerates its absence) but committing one makes
# the build reproducible.
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-install-project

COPY ./docker/dev/django/start /start
COPY ./docker/dev/supervisord/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY ./docker/dev/supervisord/start /start-supervisor

# Strip CRLF so the scripts run when the repo was cloned on Windows.
RUN sed -i 's/\r$//g' /start* && chmod +x /start*

ENV PATH="/opt/venv/bin:$PATH"

COPY ./app .

CMD ["/start-supervisor"]
