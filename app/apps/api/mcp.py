"""Model Context Protocol (MCP) Streamable HTTP endpoint for Timelines.

Exposes agentic tools at ``/mcp/`` using JSON-RPC 2.0 over HTTP, authenticated
with the same ``APIToken`` personal access tokens used by the REST API
(``Authorization: Token <key>`` or ``Authorization: Bearer <key>``).
"""

import json

from apps.api.authentication import APITokenAuthentication
from apps.events.models import Event, Tag
from apps.events.search import search_events
from apps.events.services import (
    create_event,
    get_suggested_fields,
    get_tag_stats,
    get_tag_combo_lanes,
    update_event,
)
from apps.users.models import APIToken
from django.conf import settings
from django.db.models import Count, Max
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

MCP_PROTOCOL_VERSION = "2025-03-26"

TOOLS = [
    {
        "name": "log_event",
        "description": (
            "Log a new life event on Timelines (point-in-time, ongoing span, or "
            "completed span) with tags, Markdown notes, and key-value data points."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short summary of the event.",
                },
                "notes": {"type": "string", "description": "Optional Markdown notes."},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Tag names (created automatically), e.g. ['dog', 'puke']."
                    ),
                },
                "started_at": {
                    "type": "string",
                    "description": "ISO 8601 timestamp (defaults to now).",
                },
                "ended_at": {
                    "type": "string",
                    "description": "Optional ISO 8601 end timestamp for spans.",
                },
                "is_ongoing": {
                    "type": "boolean",
                    "description": "True for active spans like starting a medication.",
                },
                "all_day": {
                    "type": "boolean",
                    "description": "True when only the day matters, not the time.",
                },
                "data_points": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string"},
                            "value": {"type": "string"},
                            "unit": {"type": "string"},
                        },
                        "required": ["key", "value"],
                    },
                    "description": (
                        "Optional measurements, e.g. "
                        "[{'key': 'battery', 'value': '14%'}]."
                    ),
                },
                "parent_id": {
                    "type": "integer",
                    "description": "Optional ongoing parent event ID to link to.",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "stop_event",
        "description": "End an ongoing span (sets ended_at and is_ongoing=false).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "integer"},
                "ended_at": {
                    "type": "string",
                    "description": "Optional ISO 8601 timestamp (defaults to now).",
                },
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "update_event",
        "description": "Update an existing event or append a timestamped note to it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "integer"},
                "title": {"type": "string"},
                "notes": {"type": "string"},
                "append_note": {
                    "type": "string",
                    "description": "Append a timestamped entry to notes.",
                },
                "tags": {"type": "array", "items": {"type": "string"}},
                "data_points": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string"},
                            "value": {"type": "string"},
                            "unit": {"type": "string"},
                        },
                        "required": ["key", "value"],
                    },
                },
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "search_events",
        "description": (
            "Search events using structured + full-text syntax (#tag, -#tag, "
            "key:value, battery:<20, has:key, is:ongoing|span|point, last:30d)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "Search query string."},
                "tags": {"type": "array", "items": {"type": "string"}},
                "tag_mode": {"type": "string", "enum": ["and", "or"]},
                "limit": {"type": "integer", "default": 50},
            },
        },
    },
    {
        "name": "list_tags",
        "description": (
            "List user tags with event counts, last occurrence, and suggested fields."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 50},
            },
        },
    },
    {
        "name": "get_tag_stats",
        "description": (
            "Get count, days since last event, interval stats, and numeric trends."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "tag": {"type": "string", "description": "Tag name or slug."},
            },
            "required": ["tag"],
        },
    },
    {
        "name": "get_timeline_overlay",
        "description": (
            "Return events on a shared time range, one lane per exact tag "
            "combination (events tagged #dog and #dog #puke land in separate lanes). "
            "Each lane has its tags, events, count, average gap in days and the "
            "number series of its fields, for spotting patterns and correlations."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Only events that have all of these tags (so ['dog'] "
                        "returns the dog lane and every combination with dog)."
                    ),
                },
                "q": {
                    "type": "string",
                    "description": "Search query, same syntax as search_events.",
                },
            },
        },
    },
]


def _authenticate_mcp_request(request):
    """Authenticate via APIToken (Token or Bearer header) or logged-in session."""
    if getattr(request, "user", None) and request.user.is_authenticated:
        return request.user

    auth_header = request.META.get("HTTP_AUTHORIZATION", "").strip()
    if not auth_header:
        return None

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() not in {"token", "bearer"}:
        return None

    raw_token = parts[1]
    if not raw_token.startswith(APIToken.TOKEN_PREFIX):
        return None

    try:
        token_key, token_secret = APIToken.parse_raw_token(raw_token)
    except ValueError:
        return None

    token = APIToken.objects.select_related("user").filter(token_key=token_key).first()
    if (
        token is None
        or not token.check_secret(token_secret)
        or token.revoked_at is not None
        or token.is_expired()
        or not token.user.is_active
    ):
        return None

    APITokenAuthentication._touch_last_used(token)
    return token.user


def _parse_dt(raw: str | None):
    if not raw:
        return None
    dt = parse_datetime(raw)
    if dt is not None and timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _serialize_event(ev: Event) -> dict:
    return {
        "id": ev.id,
        "title": ev.title,
        "notes": ev.notes,
        "shape": ev.shape,
        "started_at": ev.started_at.isoformat(),
        "ended_at": ev.ended_at.isoformat() if ev.ended_at else None,
        "is_ongoing": ev.is_ongoing,
        "all_day": ev.all_day,
        "parent_id": ev.parent_id,
        "tags": [t.name for t in ev.tags.all()],
        "data_points": [
            {
                "key": dp.key,
                "value": dp.value_text,
                "value_num": dp.value_num,
                "unit": dp.unit,
            }
            for dp in ev.data_points.all()
        ],
    }


def _dispatch_tool(user, name: str, args: dict) -> dict:
    if name == "log_event":
        parent = None
        if args.get("parent_id"):
            parent = Event._base_manager.filter(
                owner=user, pk=int(args["parent_id"])
            ).first()
        ev = create_event(
            user,
            title=args["title"],
            notes=args.get("notes", ""),
            started_at=_parse_dt(args.get("started_at")),
            ended_at=_parse_dt(args.get("ended_at")),
            is_ongoing=bool(args.get("is_ongoing", False)),
            all_day=bool(args.get("all_day", False)),
            tag_names=args.get("tags", []),
            data_points=args.get("data_points", []),
            parent=parent,
        )
        return _serialize_event(ev)

    if name == "stop_event":
        ev = Event._base_manager.filter(owner=user, pk=int(args["event_id"])).first()
        if ev is None:
            raise ValueError(f"Event {args['event_id']} not found.")
        ev.stop(at=_parse_dt(args.get("ended_at")))
        return _serialize_event(ev)

    if name == "update_event":
        ev = Event._base_manager.filter(owner=user, pk=int(args["event_id"])).first()
        if ev is None:
            raise ValueError(f"Event {args['event_id']} not found.")
        update_event(
            ev,
            title=args.get("title"),
            notes=args.get("notes"),
            append_note=args.get("append_note"),
            tag_names=args.get("tags"),
            data_points=args.get("data_points"),
        )
        return _serialize_event(ev)

    if name == "search_events":
        qs = Event._base_manager.filter(owner=user).prefetch_related(
            "tags", "data_points"
        )
        limit = min(int(args.get("limit", 50)), 200)
        results = search_events(
            qs,
            q=args.get("q", ""),
            extra_tags=args.get("tags"),
            tag_mode=args.get("tag_mode", "and"),
        )[:limit]
        items = [_serialize_event(ev) for ev in results]
        return {"count": len(items), "events": items}

    if name == "list_tags":
        limit = min(int(args.get("limit", 50)), 200)
        tags = (
            Tag._base_manager.filter(owner=user)
            .annotate(event_count=Count("events"), last_used=Max("events__started_at"))
            .order_by("-event_count", "name")[:limit]
        )
        return {
            "tags": [
                {
                    "name": t.name,
                    "slug": t.slug,
                    "color": t.color,
                    "event_count": t.event_count,
                    "last_used": t.last_used.isoformat() if t.last_used else None,
                    "suggested_fields": get_suggested_fields(user, [t.slug], limit=5),
                }
                for t in tags
            ]
        }

    if name == "get_tag_stats":
        stats = get_tag_stats(user, args["tag"])
        if stats is None:
            raise ValueError(f"Tag '{args['tag']}' not found.")
        return stats

    if name == "get_timeline_overlay":
        return get_tag_combo_lanes(
            user, tags=args.get("tags", []), q=args.get("q", ""), archived=True
        )

    raise KeyError(f"Unknown tool: {name}")


def _rpc_error(req_id, code: int, message: str, status: int = 200) -> JsonResponse:
    return JsonResponse(
        {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}},
        status=status,
    )


@csrf_exempt
@require_http_methods(["POST"])
def mcp_endpoint(request):
    user = _authenticate_mcp_request(request)
    if user is None:
        return JsonResponse(
            {"detail": "Authentication credentials were not provided or are invalid."},
            status=401,
        )

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _rpc_error(None, -32700, "Parse error", status=400)

    req_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}

    if method == "initialize":
        return JsonResponse(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "timelines",
                        "version": settings.APP_VERSION,
                    },
                },
            }
        )

    if method == "notifications/initialized":
        return HttpResponse(status=202)

    if method == "ping":
        return JsonResponse({"jsonrpc": "2.0", "id": req_id, "result": {}})

    if method == "tools/list":
        return JsonResponse(
            {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
        )

    if method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments") or {}
        try:
            result = _dispatch_tool(user, tool_name, tool_args)
        except KeyError as exc:
            return _rpc_error(req_id, -32601, str(exc))
        except (ValueError, TypeError) as exc:
            return JsonResponse(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "isError": True,
                        "content": [{"type": "text", "text": str(exc)}],
                    },
                }
            )
        return JsonResponse(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, ensure_ascii=False),
                        }
                    ],
                },
            }
        )

    return _rpc_error(req_id, -32601, f"Method not found: {method}")
