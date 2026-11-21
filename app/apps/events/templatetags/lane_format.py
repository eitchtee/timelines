from django import template
from django.template.defaultfilters import floatformat

register = template.Library()


@register.filter
def days_span(days: float | None) -> str:
    """Days, one decimal only while it matters: 0.46 -> "0,5d", 3.0 -> "3d", 12.7 -> "13d"."""
    if days is None:
        return ""
    return f"{floatformat(round(days, 1) if days < 10 else round(days), -1)}d"


@register.filter
def hours_span(hours: float | None) -> str:
    """Under an hour in minutes, under two days in hours, then in days."""
    if hours is None:
        return ""
    if hours < 1:
        return f"{round(hours * 60)}m"
    if hours < 48:
        return f"{floatformat(round(hours, 1) if hours < 10 else round(hours), -1)}h"
    return days_span(hours / 24)


@register.filter
def duration_span(td) -> str:
    """An Event.duration (a timedelta) as "45m", "13h" or "3d"."""
    return "" if td is None else hours_span(td.total_seconds() / 3600)
