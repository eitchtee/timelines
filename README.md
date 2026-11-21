<p align="center">
  <img alt="Timelines" title="Timelines" src="./app/static/img/favicon.svg" width="96" />
</p>
<h1 align="center">Timelines</h1>
<p align="center">
  <a href="#why-timelines">Why</a> •
  <a href="#key-features">Features</a> •
  <a href="#how-to-use">Usage</a> •
  <a href="#quick-log-syntax">Syntax</a> •
  <a href="#api-and-mcp">API</a> •
  <a href="#help-translate">Translate</a> •
  <a href="#caveats-and-warnings">Caveats</a> •
  <a href="#built-with">Built with</a>
</p>

**Timelines** is a self-hosted log for the small things that happen in your life: the
dog throwing up, charging your watch, starting a new medication, a headache that
lasted two days. Type one line, and it lands on a timeline next to everything else
with the same tags, so patterns show up on their own.

# Why Timelines?

Most of life's minor events aren't worth a spreadsheet, but you still end up asking
"when was the last time…?" or "how often does this happen?". Notes apps can't answer
that, and habit trackers want you to decide upfront what to track.

Timelines takes the opposite approach: log anything, whenever, with as much or as
little detail as you have. Tags group events into lanes, and each lane works out on
its own how often things happen, when the next one is due, and what time of day they
tend to fall on.

# Key Features

- **One-line logging**: `Dog puked #dog #puke ate:chicken @20/10` becomes an
  event with tags, a field and a date. Autocomplete suggests tags, fields and dates
  ("Now", "Yesterday", "This morning"…) as you type.
- **Points, spans and all-day events**: log a moment, something that lasted (a
  cold, a trip), something still going on, or just a day when the time doesn't matter.
- **Three views of the same data**:
  - **Feed**: everything, newest first, grouped by day.
  - **Lanes**: an editor-style timeline with one lane per tag combination, so
    `#dog` and `#dog #puke` sit side by side. Zoom, drag, and click any day to log on it.
  - **Calendar**: a month grid with multi-day events drawn as bars.
- **Lane pages**: click a lane to see how often it happens, when the next one is
  due, the gaps between events, which weekdays and hours they fall on, and charts
  for any number fields.
- **Archiving**: finished lanes can be archived out of the way. Log to one again
  and it comes back.
- **Fields**: attach `key:value` data to events. Numbers get charted
  (`battery:14`, `dose:400`), text gets counted (`ate:"chicken and rice"`).
- **Nesting**: mark an event as part of another, like doses under a course of medication.
- **Search**: full-text plus filters for tags, fields, numeric ranges and date
  windows.
- **REST API and MCP server**: log and query from scripts, automations, or an AI
  assistant.
- **Built for daily use**: installable as a PWA, dark and light themes, and
  per-user language, time zone and date formats.
- **Single sign-on** through any OpenID Connect provider.

# How To Use

You'll need Docker and Docker Compose.

```bash
mkdir timelines && cd timelines
curl -o docker-compose.yml https://raw.githubusercontent.com/eitchtee/timelines/main/docker-compose.prod.yml
curl -o .env https://raw.githubusercontent.com/eitchtee/timelines/main/.env.example
# edit .env: at least SECRET_KEY, URL and DJANGO_ALLOWED_HOSTS
docker compose up -d
```

Timelines will be at `http://localhost:8000` (or whatever `OUTBOUND_PORT` says).
Set `ADMIN_EMAIL` and `ADMIN_PASSWORD` before the first start to get an account;
remove them once you've logged in.

By default everything is stored in a single SQLite file in the `timelines_data`
volume, and uploads go in `./media`. Back both up.

### Using PostgreSQL

SQLite is plenty for a person or a household. If you'd rather run PostgreSQL,
uncomment the `SQL_*` variables in `.env` and start with the `postgres` profile:

```bash
docker compose --profile postgres up -d
```

Timelines uses PostgreSQL whenever `SQL_HOST` is set. Search works the same way
on both (word forms, partial words, best matches first); PostgreSQL also forgives
typos. There's no built-in migration between the two.

## Running locally (development)

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up --build
```

This runs Django's dev server plus a Vite server on port 5173 for hot-reloaded
assets. Tests run inside the container:

```bash
docker exec timelines_dev_server python -m pytest -q apps
```

## Environment Variables

| Variable | Type | Default | Explanation |
| --- | --- | --- | --- |
| `SECRET_KEY` | string | *(required)* | Django's signing key. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(64))"`. |
| `URL` | string | `http://localhost:8000` | Space-separated origins allowed to submit forms (CSRF). |
| `DJANGO_ALLOWED_HOSTS` | string | `localhost 127.0.0.1` | Space-separated hostnames Timelines answers to. |
| `HTTPS_ENABLED` | bool | `false` | Secure cookies, and HSTS when `SECURE_HSTS_SECONDS` is set. Turn on behind HTTPS. |
| `DEBUG` | bool | `false` | Never enable in production. |
| `TZ` | string | `UTC` | Server time zone. Each user can pick their own in Settings. |
| `LOG_LEVEL` | string | `INFO` | |
| `OUTBOUND_PORT` | int | `8000` | Port published on the host. |
| `INTERNAL_PORT` | int | `8000` | Port the app binds inside the container. |
| `SERVER_NAME` | string | `timelines_server` | App container name. |
| `DB_NAME` | string | `timelines_db` | Database container name. |
| `SQLITE_PATH` | string | `/usr/src/app/data/db.sqlite3` | Where the SQLite database lives when `SQL_HOST` is unset. |
| `SQL_HOST` | string | *(unset)* | PostgreSQL host. Setting it switches from SQLite to PostgreSQL. |
| `SQL_DATABASE` | string | | PostgreSQL database. |
| `SQL_USER` | string | | PostgreSQL user. |
| `SQL_PASSWORD` | string | | PostgreSQL password. |
| `SQL_PORT` | int | `5432` | PostgreSQL port. |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | string | | Creates this account on start if it doesn't exist. |
| `WEB_CONCURRENCY` | int | `4` | Gunicorn workers. |
| `GUNICORN_THREADS` | int | `1` | Threads per worker. |
| `SESSION_EXPIRY_TIME` | int | `2678400` | Seconds a login lasts (31 days). |
| `API_TOKEN_LAST_USED_UPDATE_INTERVAL` | int | `600` | How often, in seconds, a token's "last used" time is updated. |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | | | SMTP settings for outgoing mail. |

## OIDC Configuration

Timelines can log users in through any OpenID Connect provider (Authentik,
Keycloak, Authelia, Google…). Set all three of `OIDC_CLIENT_ID`,
`OIDC_CLIENT_SECRET` and `OIDC_SERVER_URL`; without them the login page only
shows the password form.

| Variable | Explanation |
| --- | --- |
| `OIDC_CLIENT_NAME` | Name on the login button. Defaults to "OpenID Connect". |
| `OIDC_CLIENT_ID` | Client ID from your provider. |
| `OIDC_CLIENT_SECRET` | Client secret from your provider. |
| `OIDC_SERVER_URL` | The provider's discovery base URL, e.g. `https://auth.example.com/application/o/timelines/`. |
| `OIDC_ALLOW_SIGNUP` | Lets new users sign up through the provider. Defaults to `true`. |

Use `https://<your-domain>/auth/oidc/<slug of OIDC_CLIENT_NAME>/login/callback/` as the
redirect URI.

# Quick Log Syntax

Everything except the title is optional, and order doesn't matter.

| You type | It means |
| --- | --- |
| `#dog` | A tag. Events with the same set of tags share a lane. |
| `battery:14` | A field. Use quotes for spaces: `ate:"chicken and rice"`. |
| `@20/10` | On that day, all day. |
| `@20/10,14:30` or `@14:30` | At that time (today when there's no date). |
| `@20/10~22/10` | A span across those days. |
| `@20/10~` or `!ongoing` | Started then and still going. |
| `>` | Pick an event this one is part of. |

Search understands the same tags and fields, plus a few filters:

```
#dog -#walk             tagged dog, not walk
is:ongoing              also is:span and is:point
has:battery             any event with that field
battery:<20             numeric comparisons: < <= > >= =
last:30d                also 12h, 2w, 6m, 1y
after:2026-10-01        and before:
```

# API and MCP

Create a personal access token in **Settings → API tokens** (or with
`manage.py create_api_token`) and send it as `Authorization: Token <token>`.

- **REST**: `/api/events/` and `/api/tags/`. Schema at `/api/schema/`, interactive
  docs at `/api/docs/`.
- **MCP**: point an MCP client at `/mcp/` with the same token. It can
  `log_event`, `stop_event`, `update_event`, `search_events`, `list_tags`,
  `get_tag_stats` and `get_timeline_overlay`.

# Help Translate

Timelines follows each user's language setting when a translation exists.
To start a new one:

```bash
cd app && uv run python manage.py makemessages --locale pt_BR
```

Then translate `app/locale/<locale>/LC_MESSAGES/django.po`. Once a catalogue exists,
the `translations.yml` workflow keeps it in sync with the code.

# Caveats and Warnings

- Timelines is young (0.1). Expect rough edges, and back up your data.
- It's built for one person or a household, not for big multi-tenant installs.
- Events logged before all-day support stay timed. Edit one and clear its time to make it all-day.

# Built with

- [Django](https://www.djangoproject.com/) and [Django REST Framework](https://www.django-rest-framework.org/)
- [SQLite](https://sqlite.org/) or [PostgreSQL](https://www.postgresql.org/)
- [htmx](https://htmx.org/), [Alpine.js](https://alpinejs.dev/) and [_hyperscript](https://hyperscript.org/)
- [Tailwind CSS](https://tailwindcss.com/) and [Basecoat](https://basecoatui.com/)
- [Chart.js](https://www.chartjs.org/), [Tom Select](https://tom-select.js.org/) and [Air Datepicker](https://air-datepicker.com/)
- [django-allauth](https://allauth.org/) for OIDC
- [Vite](https://vite.dev/) and [Docker](https://www.docker.com/)
